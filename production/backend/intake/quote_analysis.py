"""Single comparison adapter for every private CRM interface.

A quote with missing historical source terms cannot be ranked. Different
scenarios may show their own undiscounted cash outflow, but never a common rank.
"""
from dataclasses import dataclass, replace
from decimal import Decimal
from broker.payment_schedule import checked_schedule
from broker.offer_comparison import Scenario, Offer, COST_FIELDS, cash_outflow


@dataclass(frozen=True)
class QuoteResult:
    offer_id: str
    lessor: str
    total_cash_outflow: Decimal | None
    rank: int | None
    blockers: tuple[str, ...]
    source_scenario: Scenario | None


def analyse_quotes(lead, quotes, as_of):
    scenario = Scenario(lead.asset_price, lead.advance, lead.term_months, lead.vat_basis)
    rows = []
    explicit_group = any(bool(q.payment_schedule) for q in quotes)
    for q in quotes:
        terms = None
        issues = []
        try:
            terms = q.source_scenario()
            if terms is None:
                issues.append("Условия оригинала не подтверждены")
            else:
                offer = Offer(
                    offer_id=q.offer_id, lessor=q.lessor_name,
                    source_document_id=q.source_document_id,
                    received_on=q.received_on, valid_until=q.valid_until,
                    scenario=terms, verified_by_broker=q.verified_by_broker,
                    **{field:getattr(q,field) for field in COST_FIELDS},
                )
        except (ValueError, TypeError):
            issues.append("Некорректные исходные данные")
        total = None
        if not issues:
            if not offer.verified_by_broker:
                issues.append("Оригинал не проверен")
            if offer.received_on > as_of:
                issues.append("Дата получения в будущем")
            if offer.valid_until < as_of:
                issues.append("Срок КП истёк")
            if q.payment_schedule:
                if not issues:
                    try:
                        total = checked_schedule(q)
                    except (ValueError, TypeError, KeyError):
                        issues.append("График требует повторной сверки")
            else:
                if any(getattr(offer,field) is None for field in COST_FIELDS):
                    issues.append("Не все расходы указаны")
                if not issues:
                    total = cash_outflow(offer)
                if explicit_group:
                    issues.append("Расчёт по равным платежам — без рейтинга с точными графиками")
            if terms != scenario:
                issues.append("Другие условия — без общего рейтинга")
        rows.append(QuoteResult(q.offer_id,q.lessor_name,total,None,tuple(issues),terms))
    # Rank only a verified like-for-like group, at most 20 offers.
    eligible = [r.total_cash_outflow for r in rows if r.total_cash_outflow is not None and not r.blockers]
    if 2 <= len(eligible) <= 20 and len(rows) <= 20:
        rows = [replace(r, rank=1+sum(t<r.total_cash_outflow for t in eligible))
                if not r.blockers and r.total_cash_outflow is not None else r for r in rows]
    return rows, len(eligible)
