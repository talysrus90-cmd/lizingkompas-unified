"""Offline, synthetic-only document exchange laboratory.

No network, real electronic signature, private keys, certificates, external
operator, production documents or legal effect. States and receipts explicitly
belong to the simulator. Hashes identify bytes, not signatures.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
import secrets

MAX_BYTES = 5 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
PARTIES = ("QA-BROKER", "QA-LESSOR", "QA-CLIENT")

TRANSITIONS = {
    "draft": {"submit_review": "review"},
    "review": {"approve": "ready", "request_revision": "draft"},
    "ready": {"simulate_send": "sent", "request_revision": "draft"},
    "sent": {"receipt_delivery": "delivered", "receipt_failure": "failed"},
    "failed": {"retry_review": "review"},
    "delivered": {"receipt_accept": "accepted_test", "receipt_reject": "rejected"},
    "rejected": {"retry_review": "review"},
    "accepted_test": {},
}
RECEIPTS = {"receipt_delivery", "receipt_failure", "receipt_accept", "receipt_reject"}
OPERATORS = {"submit_review": "author", "approve": "reviewer",
             "request_revision": "reviewer", "simulate_send": "dispatcher",
             "retry_review": "author"}

def digest(data):
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_BYTES:
        raise ValueError("Bounded non-empty synthetic bytes required")
    return hashlib.sha256(data).hexdigest()

@dataclass(frozen=True)
class Event:
    sequence: int
    event_id: str
    action: str
    actor: str
    from_state: str
    to_state: str
    version: int
    sha256: str
    at: str
    dispatch_id: str | None
    environment: str = "LOCAL_SIMULATOR"

@dataclass
class Envelope:
    """In-memory QA envelope. All content must be synthetic."""
    recipient: str
    content: bytes = field(repr=False)
    enabled: bool = False
    envelope_id: str = field(default_factory=lambda: secrets.token_hex(16), init=False)
    version: int = field(default=1, init=False)
    state: str = field(default="draft", init=False)
    _events: list = field(default_factory=list, init=False, repr=False)
    _keys: dict = field(default_factory=dict, init=False, repr=False)
    _sha256: str = field(init=False, repr=False)
    dispatch_id: str | None = field(default=None, init=False)

    def __post_init__(self):
        if self.recipient not in PARTIES:
            raise ValueError("Only synthetic QA recipients permitted")
        self._sha256 = digest(self.content)

    @property
    def sha256(self):
        return self._sha256

    @property
    def events(self):
        return tuple(self._events)

    def _check(self, version, expected_hash):
        if not self.enabled:
            raise PermissionError("Simulator switch OFF")
        if version != self.version or expected_hash != self._sha256:
            raise ValueError("Stale document revision")
        if digest(self.content) != self._sha256:
            raise ValueError("Document bytes changed")

    def _record(self, key, action, actor, target):
        event = Event(len(self._events)+1, key, action, actor, self.state,
                      target, self.version, self._sha256,
                      datetime.now(timezone.utc).isoformat(), self.dispatch_id)
        self.state = target
        self._events.append(event)
        return event

    def transition(self, action, actor, key, version, expected_hash, dispatch_id=None):
        self._check(version, expected_hash)
        if not isinstance(key, str) or not ID.fullmatch(key):
            raise ValueError("Invalid idempotency key")
        if action not in OPERATORS and action not in RECEIPTS:
            raise ValueError("Unknown action")
        required = "local_simulator" if action in RECEIPTS else OPERATORS[action]
        if actor != required:
            raise PermissionError("Wrong simulator role")
        request = (action, actor, version, expected_hash, dispatch_id)
        if key in self._keys:
            previous, event = self._keys[key]
            if previous != request:
                raise ValueError("Idempotency key reused for different request")
            return event
        if action in RECEIPTS and (self.dispatch_id is None or dispatch_id != self.dispatch_id):
            raise ValueError("Receipt belongs to another dispatch attempt")
        if action not in RECEIPTS and dispatch_id is not None:
            raise ValueError("Only receipts carry a dispatch identifier")
        target = TRANSITIONS[self.state].get(action)
        if target is None:
            raise ValueError("Invalid state transition")
        if action == "simulate_send":
            self.dispatch_id = secrets.token_hex(16)
        event = self._record(key, action, actor, target)
        if action == "retry_review":
            self.dispatch_id = None
        self._keys[key] = (request, event)
        return event

    def replace_draft(self, data, version, expected_hash):
        self._check(version, expected_hash)
        if self.state != "draft":
            raise ValueError("Only a draft can be replaced")
        new_hash = digest(data)
        if new_hash == self._sha256:
            return
        self.content = data
        self._sha256 = new_hash
        self.version += 1
        self._record(secrets.token_hex(16), "replace_draft", "author", "draft")

def synthetic_demo():
    env = Envelope("QA-LESSOR", b"COMPASS SYNTHETIC QA DOCUMENT V1", enabled=True)
    for n,(action,actor) in enumerate([
        ("submit_review","author"),("approve","reviewer"),
        ("simulate_send","dispatcher"),("receipt_delivery","local_simulator"),
        ("receipt_accept","local_simulator"),
    ],1):
        env.transition(action,actor,f"qa-{n}",env.version,env.sha256,
                       env.dispatch_id if action in RECEIPTS else None)
    return env

if __name__ == "__main__":
    import json
    from dataclasses import asdict
    env = synthetic_demo()
    print(json.dumps({"environment":"LOCAL_SIMULATOR","legal_effect":False,
          "state":env.state,"events":[asdict(e) for e in env.events]},indent=2))
