"""Synthetic, in-memory broker case workflow; NOT an API or production CRM.

No personal data, persistence, network traffic, login or partner integrations.
Caller must pass an Actor verified by a trusted authentication layer; case
assignments are held INSIDE this service, not taken from Actor.case_ids.
All mutations are optimistic-concurrency guarded and case/tenant scoped.
"""
from dataclasses import dataclass, replace
from datetime import date
from threading import RLock
from uuid import uuid4
from access_policy import Actor, Resource, allowed
from offer_comparison import Scenario, Offer, Comparison, compare_offers

TRANSITIONS = {
    "draft": frozenset(("collecting",)),
    "collecting": frozenset(("comparing",)),
    "comparing": frozenset(("closed",)),
    "closed": frozenset(),
}


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    tenant_id: str
    scenario: Scenario
    stage: str
    version: int
    assigned_user_ids: frozenset[str]
    offer_ids: tuple[str, ...] = ()


class CaseDesk:
    """Reference state machine; never instantiate as real customer storage."""

    def __init__(self):
        self._lock = RLock()
        self._cases: dict[str, CaseRecord] = {}
        self._offers: dict[str, dict[str, Offer]] = {}

    @staticmethod
    def _trusted_actor(actor: Actor) -> None:
        if not isinstance(actor, Actor) or not actor.user_id or not actor.tenant_id:
            raise PermissionError("access_denied")

    def create(self, actor: Actor, scenario: Scenario) -> CaseRecord:
        self._trusted_actor(actor)
        if actor.role not in ("broker", "supervisor"):
            raise PermissionError("access_denied")
        if not isinstance(scenario, Scenario):
            raise ValueError("scenario required")
        case_id = str(uuid4())
        record = CaseRecord(case_id, actor.tenant_id, scenario, "draft", 1,
                            frozenset((actor.user_id,)))
        with self._lock:
            self._cases[case_id] = record
            self._offers[case_id] = {}
        return record

    def _read(self, actor: Actor, case_id: str, action: str, kind: str = "case") -> CaseRecord:
        self._trusted_actor(actor)
        record = self._cases.get(case_id)
        # Unknown and unauthorized case IDs have identical response.
        if record is None or record.tenant_id != actor.tenant_id:
            raise PermissionError("access_denied")
        # Ignore any caller-supplied case_ids: compute from the service's own grant.
        trusted = replace(actor, case_ids=frozenset((case_id,))
                          if actor.user_id in record.assigned_user_ids else frozenset())
        if not allowed(trusted, Resource(record.tenant_id, kind, case_id), action):
            raise PermissionError("access_denied")
        return record

    def get(self, actor: Actor, case_id: str) -> CaseRecord:
        with self._lock:
            return self._read(actor, case_id, "read")

    def assign(self, supervisor: Actor, case_id: str, user_id: str,
               expected_version: int) -> CaseRecord:
        if not isinstance(user_id, str) or not user_id or len(user_id) > 128:
            raise ValueError("invalid assignee")
        if supervisor.role != "supervisor":
            raise PermissionError("access_denied")
        with self._lock:
            record = self._read(supervisor, case_id, "update")
            self._check_version(record, expected_version)
            changed = replace(record, assigned_user_ids=record.assigned_user_ids | {user_id},
                              version=record.version + 1)
            self._cases[case_id] = changed
            return changed

    @staticmethod
    def _check_version(record: CaseRecord, expected: int) -> None:
        if type(expected) is not int or record.version != expected:
            raise ValueError("version_conflict")

    def move(self, actor: Actor, case_id: str, target: str,
             expected_version: int) -> CaseRecord:
        with self._lock:
            record = self._read(actor, case_id, "update")
            self._check_version(record, expected_version)
            if target not in TRANSITIONS[record.stage]:
                raise ValueError("invalid_transition")
            if target == "comparing" and len(record.offer_ids) < 2:
                raise ValueError("two_offers_required")
            if target == "closed" and actor.role != "supervisor":
                raise PermissionError("access_denied")
            changed = replace(record, stage=target, version=record.version + 1)
            self._cases[case_id] = changed
            return changed

    def add_offer(self, actor: Actor, case_id: str, offer: Offer,
                  expected_version: int) -> CaseRecord:
        with self._lock:
            record = self._read(actor, case_id, "create", "offer")
            self._check_version(record, expected_version)
            if record.stage not in ("draft", "collecting"):
                raise ValueError("offers_locked")
            if not isinstance(offer, Offer) or offer.scenario != record.scenario:
                raise ValueError("offer_scenario_mismatch")
            if offer.offer_id in self._offers[case_id]:
                raise ValueError("duplicate_offer")
            if len(record.offer_ids) >= 20:
                raise ValueError("offer_limit")
            # Store only verified provenance metadata/terms, never original documents.
            self._offers[case_id][offer.offer_id] = offer
            changed = replace(record, offer_ids=record.offer_ids + (offer.offer_id,),
                              version=record.version + 1)
            self._cases[case_id] = changed
            return changed

    def compare(self, actor: Actor, case_id: str, as_of: date) -> Comparison:
        with self._lock:
            record = self._read(actor, case_id, "read", "offer")
            if record.stage not in ("collecting", "comparing"):
                raise ValueError("wrong_stage")
            sources = tuple(self._offers[case_id][key] for key in record.offer_ids)
            return compare_offers(record.scenario, sources, as_of=as_of)
