"""Persistent broker workflow demonstration using synthetic quotes only.

Run from repository root:
    python broker/sqlite_demo.py

Creates a private temporary SQLite DB, verifies persistence across reopening,
and deletes the database when finished. No external network or real user data.
"""
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from access_policy import Actor
from offer_comparison import Offer, Scenario
from sqlite_store import SqliteCaseDesk


def main() -> None:
    as_of = date(2026, 11, 27)
    scenario = Scenario(D("4500000"), D("900000"), 36, "included")
    with TemporaryDirectory(prefix="lk-offerdesk-demo-") as temp:
        db = Path(temp) / "cases.sqlite3"
        desk = SqliteCaseDesk(db)
        manager = Actor("supervisor-demo", "tenant-demo", "supervisor")
        broker = Actor("broker-demo", "tenant-demo", "broker")
        case = desk.create(manager, scenario)
        case = desk.assign(manager, case.case_id, broker.user_id, case.version)
        case = desk.move(broker, case.case_id, "collecting", case.version)
        for index, monthly in enumerate(("125000", "121000", "119000"), start=1):
            quote = Offer(
                offer_id=f"offer-{index:03d}",
                lessor=f"Synthetic lessor #{index}",
                source_document_id=f"document-synthetic-{index}",
                received_on=date(2026, 11, 25),
                valid_until=date(2026, 12, 20),
                scenario=scenario, verified_by_broker=True,
                monthly_payment=D(monthly), buyout=D("1000"),
                upfront_fee=D("5000"), recurring_monthly_fee=D("500"),
                insurance_total=D("30000"), other_costs=D("0")
            )
            case = desk.add_offer(broker, case.case_id, quote, case.version)
        # Reopen the same DB to prove we are not relying on in-memory state.
        reopened = SqliteCaseDesk(db)
        assert reopened.get(broker, case.case_id).version == case.version
        case = reopened.move(broker, case.case_id, "comparing", case.version)
        comparison = reopened.compare(broker, case.case_id, as_of)
        events = reopened.audit(manager, case.case_id)
        payload = {
            "synthetic_only": True,
            "stored_across_restart": True,
            "stage": case.stage,
            "offers": [
                {"source": row.offer_id, "rank": row.rank,
                 "total_cash_outflow_rub": str(row.total_cash_outflow),
                 "blockers": list(row.blockers)}
                for row in comparison.rows
            ],
            "audit_event_count": len(events),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
