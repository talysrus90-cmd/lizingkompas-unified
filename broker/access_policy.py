"""Broker authorization policy prototype: no network, storage or authentication.

This is a pure decision function for a future server-side backend.
The caller MUST authenticate actors and load tenant/case assignments from its trusted DB.
Never trust browser-supplied actor roles or ownership for production decisions.
Python >=3.11, no third-party libraries.
"""
from dataclasses import dataclass
from typing import Literal, FrozenSet

Role = Literal["broker", "supervisor", "document_reviewer", "auditor", "admin"]
Kind = Literal["case", "document", "offer", "audit", "settings"]
Action = Literal["read", "create", "update", "delete", "approve", "configure"]

# Explicit operations; omissions mean DENY, including all delete operations.
_ALLOWED = {
    "broker": {
        "case": frozenset(("read", "create", "update")),
        "document": frozenset(("read", "create")),
        "offer": frozenset(("read", "create", "update")),
    },
    "supervisor": {
        "case": frozenset(("read", "create", "update")),
        "document": frozenset(("read", "create", "approve")),
        "offer": frozenset(("read", "create", "update", "approve")),
    },
    "document_reviewer": {
        "document": frozenset(("read", "approve")),
        "offer": frozenset(("read",)),
    },
    "auditor": {"audit": frozenset(("read",))},
    "admin": {"settings": frozenset(("read", "configure")), "audit": frozenset(("read",))},
}
_CASE_KINDS = frozenset(("case", "document", "offer"))


@dataclass(frozen=True)
class Actor:
    user_id: str
    tenant_id: str
    role: Role
    # Trusted server-side assignments (for supervisor, team cases are explicitly assigned).
    case_ids: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class Resource:
    tenant_id: str
    kind: Kind
    case_id: str = ""


def allowed(actor: Actor | None, resource: Resource | None, action: str) -> bool:
    """Return True only for explicitly granted role + tenant + case + action.

    Designed to fail closed. The resource must come from a trusted database;
    empty/forged scope and unknown operations are always denied.
    """
    if actor is None or resource is None:
        return False
    if not actor.user_id or not actor.tenant_id or not resource.tenant_id:
        return False
    if actor.tenant_id != resource.tenant_id:
        return False
    by_kind = _ALLOWED.get(actor.role, {})
    if action not in by_kind.get(resource.kind, frozenset()):
        return False
    if resource.kind in _CASE_KINDS:
        return bool(resource.case_id and resource.case_id in actor.case_ids)
    return not resource.case_id


def require_access(actor: Actor | None, resource: Resource | None, action: str) -> None:
    """Raise PermissionError for a denied operation; do not reveal object existence."""
    if not allowed(actor, resource, action):
        raise PermissionError("access_denied")
