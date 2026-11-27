"""Persistent synthetic case desk using SQLite. NOT a production backend.

Python 3.11+; standard library only. No HTTP, secrets, customer information
or external calls. Actor values MUST originate from trusted server-side
authentication in any future integration, never from a browser payload.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sqlite3
import uuid
from dataclasses import dataclass
from contextlib import contextmanager
from decimal import Decimal

from access_policy import Actor, Resource, allowed
from case_workflow import CaseRecord, TRANSITIONS
from offer_comparison import COST_FIELDS, Offer, Scenario, Comparison, compare_offers

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$")


def _scenario_payload(s: Scenario) -> dict:
    return {
        "asset_price": str(s.asset_price), "advance": str(s.advance),
        "term_months": s.term_months, "vat_basis": s.vat_basis,
        "currency": s.currency,
    }


def _scenario_from(data: dict) -> Scenario:
    return Scenario(
        Decimal(data["asset_price"]), Decimal(data["advance"]),
        data["term_months"], data["vat_basis"], data["currency"]
    )


def _offer_payload(o: Offer) -> dict:
    fields = {
        "offer_id": o.offer_id, "lessor": o.lessor,
        "source_document_id": o.source_document_id,
        "received_on": o.received_on.isoformat(),
        "valid_until": o.valid_until.isoformat(),
        "scenario": _scenario_payload(o.scenario),
        "verified_by_broker": o.verified_by_broker,
    }
    fields.update({name: str(getattr(o, name)) if getattr(o, name) is not None else None
                   for name in COST_FIELDS})
    return fields


def _offer_from(d: dict) -> Offer:
    values = {k: Decimal(d[k]) if d[k] is not None else None for k in COST_FIELDS}
    return Offer(
        offer_id=d["offer_id"], lessor=d["lessor"],
        source_document_id=d["source_document_id"],
        received_on=dt.date.fromisoformat(d["received_on"]),
        valid_until=dt.date.fromisoformat(d["valid_until"]),
        scenario=_scenario_from(d["scenario"]),
        verified_by_broker=d["verified_by_broker"], **values
    )


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    case_id: str
    actor_id: str
    action: str
    version: int
    created_at: str


class SqliteCaseDesk:
    """Transactional local prototype; do not use for real personal data.

    Audit records are only append-only at this application layer; SQLite files
    are not tamper-evident. For production add authenticated identity, a secure
    audit destination, backups, migrations, real operator UI and policy.
    """

    def __init__(self, db_path: str | os.PathLike[str]):
        path = pathlib.Path(db_path)
        if not path.is_absolute():
            raise ValueError("database path must be absolute")
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise ValueError("database path must be a regular private file")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        with self._db() as c:
            c.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS cases(
                    case_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    scenario TEXT NOT NULL, stage TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version > 0),
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assignments(
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    user_id TEXT NOT NULL, PRIMARY KEY(case_id, user_id));
                CREATE TABLE IF NOT EXISTS offers(
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    offer_id TEXT NOT NULL, source_document_id TEXT NOT NULL,
                    body TEXT NOT NULL, position INTEGER NOT NULL,
                    PRIMARY KEY(case_id,offer_id),
                    UNIQUE(case_id,source_document_id),
                    UNIQUE(case_id,position));
                CREATE TABLE IF NOT EXISTS audit(
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL, version INTEGER NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_case_tenant ON cases(tenant_id);
                CREATE INDEX IF NOT EXISTS ix_assignee ON assignments(user_id,case_id);
            """)
        if os.name != "nt":
            os.chmod(path, 0o600)

    @contextmanager
    def _db(self):
        c = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        try:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=5000")
            yield c
        finally:
            c.close()

    @staticmethod
    def _check_actor(actor: Actor) -> None:
        if not isinstance(actor, Actor) or not actor.user_id or not actor.tenant_id:
            raise PermissionError("access_denied")

    @staticmethod
    def _version(expected: int, actual: int) -> None:
        if type(expected) is not int or expected != actual:
            raise ValueError("version_conflict")

    @staticmethod
    def _audit(c: sqlite3.Connection, case_id: str, actor: Actor, action: str, version: int) -> None:
        c.execute("INSERT INTO audit VALUES(?,?,?,?,?,?)", (
            str(uuid.uuid4()), case_id, actor.user_id, action, version,
            dt.datetime.now(dt.timezone.utc).isoformat()
        ))

    def _read(self, c: sqlite3.Connection, actor: Actor, case_id: str,
              action: str, kind: str = "case") -> tuple[CaseRecord, sqlite3.Row]:
        self._check_actor(actor)
        if not isinstance(case_id, str):
            raise PermissionError("access_denied")
        row = c.execute(
            "SELECT * FROM cases WHERE case_id=? AND tenant_id=?",
            (case_id, actor.tenant_id)
        ).fetchone()
        if row is None:
            raise PermissionError("access_denied")
        users = frozenset(r["user_id"] for r in c.execute(
            "SELECT user_id FROM assignments WHERE case_id=?", (case_id,)
        ))
        # No caller-supplied case_ids are trusted.
        scope = Actor(actor.user_id, actor.tenant_id, actor.role,
                      frozenset((case_id,)) if actor.user_id in users else frozenset())
        if not allowed(scope, Resource(actor.tenant_id, kind, case_id), action):
            raise PermissionError("access_denied")
        offers = tuple(r["offer_id"] for r in c.execute(
            "SELECT offer_id FROM offers WHERE case_id=? ORDER BY position", (case_id,)
        ))
        record = CaseRecord(case_id, row["tenant_id"],
                            _scenario_from(json.loads(row["scenario"])),
                            row["stage"], row["version"], users, offers)
        return record, row

    def create(self, actor: Actor, scenario: Scenario) -> CaseRecord:
        self._check_actor(actor)
        if actor.role not in ("broker", "supervisor"):
            raise PermissionError("access_denied")
        if not isinstance(scenario, Scenario):
            raise ValueError("scenario required")
        case_id = str(uuid.uuid4())
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)", (
                    case_id, actor.tenant_id,
                    json.dumps(_scenario_payload(scenario), sort_keys=True),
                    "draft", 1, dt.datetime.now(dt.timezone.utc).isoformat()
                ))
                c.execute("INSERT INTO assignments VALUES(?,?)", (case_id, actor.user_id))
                self._audit(c, case_id, actor, "case.created", 1)
                c.commit()
            except Exception:
                c.rollback()
                raise
        return CaseRecord(case_id, actor.tenant_id, scenario, "draft", 1,
                          frozenset((actor.user_id,)))

    def get(self, actor: Actor, case_id: str) -> CaseRecord:
        with self._db() as c:
            return self._read(c, actor, case_id, "read")[0]

    def assign(self, actor: Actor, case_id: str, user_id: str,
               expected_version: int) -> CaseRecord:
        # Membership of assignee in tenant must be checked by a future identity service.
        if not isinstance(actor, Actor) or actor.role != "supervisor":
            raise PermissionError("access_denied")
        if not isinstance(user_id, str) or not ID.fullmatch(user_id):
            raise ValueError("invalid_assignee")
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                case, _ = self._read(c, actor, case_id, "update")
                self._version(expected_version, case.version)
                if user_id in case.assigned_user_ids:
                    raise ValueError("already_assigned")
                c.execute("INSERT INTO assignments VALUES(?,?)", (case_id, user_id))
                v = case.version + 1
                c.execute("UPDATE cases SET version=? WHERE case_id=?", (v, case_id))
                self._audit(c, case_id, actor, "case.assigned", v)
                c.commit()
                return self.get(actor, case_id)
            except Exception:
                c.rollback()
                raise

    def add_offer(self, actor: Actor, case_id: str, offer: Offer,
                  expected_version: int) -> CaseRecord:
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                case, _ = self._read(c, actor, case_id, "create", "offer")
                self._version(expected_version, case.version)
                if case.stage not in ("draft", "collecting"):
                    raise ValueError("offers_locked")
                if not isinstance(offer, Offer) or offer.scenario != case.scenario:
                    raise ValueError("offer_scenario_mismatch")
                if len(case.offer_ids) >= 20:
                    raise ValueError("offer_limit")
                if c.execute("SELECT 1 FROM offers WHERE case_id=? AND (offer_id=? OR source_document_id=?)",
                             (case_id, offer.offer_id, offer.source_document_id)).fetchone():
                    raise ValueError("duplicate_offer_or_source")
                c.execute("INSERT INTO offers VALUES(?,?,?,?,?)", (
                    case_id, offer.offer_id, offer.source_document_id,
                    json.dumps(_offer_payload(offer), ensure_ascii=False, sort_keys=True),
                    len(case.offer_ids)
                ))
                v = case.version + 1
                c.execute("UPDATE cases SET version=? WHERE case_id=?", (v, case_id))
                self._audit(c, case_id, actor, "offer.added", v)
                c.commit()
                return self.get(actor, case_id)
            except Exception:
                c.rollback()
                raise

    def move(self, actor: Actor, case_id: str, target: str,
             expected_version: int) -> CaseRecord:
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                case, _ = self._read(c, actor, case_id, "update")
                self._version(expected_version, case.version)
                if target not in TRANSITIONS.get(case.stage, frozenset()):
                    raise ValueError("invalid_transition")
                if target == "comparing" and len(case.offer_ids) < 2:
                    raise ValueError("two_offers_required")
                if target == "closed" and actor.role != "supervisor":
                    raise PermissionError("access_denied")
                v = case.version + 1
                c.execute("UPDATE cases SET stage=?, version=? WHERE case_id=?",
                          (target, v, case_id))
                self._audit(c, case_id, actor, "case.stage_changed", v)
                c.commit()
                return self.get(actor, case_id)
            except Exception:
                c.rollback()
                raise

    def compare(self, actor: Actor, case_id: str, as_of: dt.date) -> Comparison:
        with self._db() as c:
            case, _ = self._read(c, actor, case_id, "read", "offer")
            if case.stage not in ("collecting", "comparing"):
                raise ValueError("wrong_stage")
            rows = c.execute(
                "SELECT body FROM offers WHERE case_id=? ORDER BY position", (case_id,)
            ).fetchall()
            return compare_offers(case.scenario, [_offer_from(json.loads(r["body"])) for r in rows],
                                  as_of=as_of)

    def audit(self, actor: Actor, case_id: str) -> tuple[AuditEvent, ...]:
        # Prototype: assigned supervisor can review limited metadata for own case.
        if not isinstance(actor, Actor) or actor.role != "supervisor":
            raise PermissionError("access_denied")
        with self._db() as c:
            self._read(c, actor, case_id, "read")
            return tuple(AuditEvent(**dict(r)) for r in c.execute(
                "SELECT event_id,case_id,actor_id,action,version,created_at FROM audit "
                "WHERE case_id=? ORDER BY version, rowid", (case_id,)
            ))
