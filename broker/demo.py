"""Run offline with Python 3.11+: python broker/demo.py

Synthetic amounts / lessors only. Nothing is transmitted or saved.
"""
import json
from datetime import date
from decimal import Decimal
from access_policy import Actor
from case_workflow import CaseDesk
from offer_comparison import Offer, Scenario


def main():
    today = date(2026, 11, 27)
    scenario = Scenario(Decimal("4500000"), Decimal("900000"), 36, "included")
    desk = CaseDesk()
    supervisor = Actor("synthetic-supervisor", "demo-tenant", "supervisor")
    broker = Actor("synthetic-broker", "demo-tenant", "broker")
    record = desk.create(supervisor, scenario)
    record = desk.assign(supervisor, record.case_id, broker.user_id, record.version)
    record = desk.move(broker, record.case_id, "collecting", record.version)
    for id_, lessor, payment in [
        ("offer-alpha", "Демонстрационный поставщик A", "125000"),
        ("offer-beta", "Демонстрационный поставщик B", "121000"),
        ("offer-gamma", "Демонстрационный поставщик C", "119000"),
    ]:
        quote = Offer(
            offer_id=id_, lessor=lessor, source_document_id="document-" + id_,
            received_on=date(2026, 11, 25), valid_until=date(2026, 12, 20),
            scenario=scenario, verified_by_broker=True,
            monthly_payment=Decimal(payment), buyout=Decimal("1000"),
            upfront_fee=Decimal("5000"),
            recurring_monthly_fee=Decimal("500"),
            insurance_total=Decimal("30000"), other_costs=Decimal("0"),
        )
        record = desk.add_offer(broker, record.case_id, quote, record.version)
    record = desk.move(broker, record.case_id, "comparing", record.version)
    comparison = desk.compare(broker, record.case_id, today)
    output = {
        "demo_only": True,
        "status": record.stage,
        "checked_at": today.isoformat(),
        "methodology": comparison.methodology,
        "offers": [{
            "offer_id": row.offer_id,
            "lessor": row.lessor,
            "rank": row.rank,
            "total_cash_outflow_rub": str(row.total_cash_outflow)
            if row.total_cash_outflow is not None else None,
            "blockers": list(row.blockers),
        } for row in comparison.rows],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
