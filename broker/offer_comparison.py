"""Deterministic leasing offer comparison (isolated, synthetic inputs only).

This module is not a lender integration, lending decision or contractual quote.
All money values are explicit ruble amounts (Decimal, never float). No inferred
interest rates, VAT refunds, tax advantages or missing charges. Comparing only
like-for-like and verified offers prevents false "cheapest" recommendations.

Python 3.11+, standard library only.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
import re

MAX_OFFERS = 20
MAX_MONEY = Decimal("1000000000000.00")
CENT = Decimal("0.01")
COST_FIELDS = ("monthly_payment", "buyout", "upfront_fee",
               "recurring_monthly_fee", "insurance_total", "other_costs")
VAT_BASIS = {"included", "excluded", "not_applicable"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")


def _money(value: Decimal | None, field: str, *, required: bool = True) -> None:
    if value is None and not required:
        return
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(field + ": must be finite Decimal (not float)")
    if value < 0 or value > MAX_MONEY or value.as_tuple().exponent < -2:
        raise ValueError(field + ": out of bounds / sub-kopeck precision")


@dataclass(frozen=True)
class Scenario:
    asset_price: Decimal
    advance: Decimal
    term_months: int
    vat_basis: Literal["included", "excluded", "not_applicable"]
    currency: Literal["RUB"] = "RUB"

    def __post_init__(self):
        _money(self.asset_price, "asset_price")
        _money(self.advance, "advance")
        if self.asset_price == 0 or self.advance >= self.asset_price:
            raise ValueError("advance must be below positive asset price")
        if type(self.term_months) is not int or not 12 <= self.term_months <= 84:
            raise ValueError("term_months: 12..84")
        if self.vat_basis not in VAT_BASIS or self.currency != "RUB":
            raise ValueError("unsupported VAT basis or currency")


@dataclass(frozen=True)
class Offer:
    offer_id: str
    lessor: str
    source_document_id: str  # opaque private document identifier, not a URL/path
    received_on: date
    valid_until: date
    scenario: Scenario
    verified_by_broker: bool
    monthly_payment: Decimal | None
    buyout: Decimal | None
    upfront_fee: Decimal | None
    recurring_monthly_fee: Decimal | None
    insurance_total: Decimal | None
    other_costs: Decimal | None

    def __post_init__(self):
        if not ID.fullmatch(self.offer_id) or not ID.fullmatch(self.source_document_id):
            raise ValueError("opaque IDs must contain 3..64 safe characters")
        if not isinstance(self.lessor, str) or not self.lessor.strip() or len(self.lessor) > 160:
            raise ValueError("lessor: missing or too long")
        if type(self.received_on) is not date or type(self.valid_until) is not date:
            raise ValueError("dates must be dates")
        if self.valid_until < self.received_on:
            raise ValueError("valid_until cannot precede received_on")
        if type(self.verified_by_broker) is not bool:
            raise ValueError("verified_by_broker must be boolean")
        if not isinstance(self.scenario, Scenario):
            raise ValueError("scenario is required")
        for field in COST_FIELDS:
            _money(getattr(self, field), field, required=False)


@dataclass(frozen=True)
class ComparisonRow:
    offer_id: str
    lessor: str
    total_cash_outflow: Decimal | None
    rank: int | None
    blockers: tuple[str, ...]
    # Identical total costs receive identical competition rank.
    # A value is an undiscounted total cash outflow, NOT APR or present value.


@dataclass(frozen=True)
class Comparison:
    scenario: Scenario
    rows: tuple[ComparisonRow, ...]
    as_of: date
    comparable_count: int
    methodology: str = (
        "Undiscounted RUB cash outflow: advance + monthly payment x months "
        "+ buyout + upfront fee + monthly fee x months + insurance + other costs. "
        "No inferred VAT, taxes, discounting, commissions or insurance; "
        "rank only offers verified by broker with complete comparable terms "
        "and original source reference. Not a lending approval or public offer."
    )


def compare_offers(scenario: Scenario, offers: list[Offer] | tuple[Offer, ...],
                   *, as_of: date) -> Comparison:
    """Compare 2–20 actual manually reviewed offers against ONE explicit scenario.

    Incomplete or mismatched offers remain visible with blockers but not ranked.
    If fewer than two valid offers remain, there is no ranking.
    """
    if not isinstance(scenario, Scenario) or type(as_of) is not date:
        raise ValueError("scenario and as_of required")
    if not isinstance(offers, (list, tuple)) or not 2 <= len(offers) <= MAX_OFFERS:
        raise ValueError("2..20 offers required")
    seen: set[str] = set()
    raw: list[tuple[Offer, Decimal | None, tuple[str, ...]]] = []
    for offer in offers:
        if not isinstance(offer, Offer):
            raise ValueError("not an Offer")
        if offer.offer_id in seen:
            raise ValueError("duplicate offer_id")
        seen.add(offer.offer_id)
        issues: list[str] = []
        if offer.scenario != scenario:
            issues.append("different_scenario")
        if not offer.verified_by_broker:
            issues.append("unverified_source")
        if offer.received_on > as_of:
            issues.append("future_received_date")
        if offer.valid_until < as_of:
            issues.append("expired")
        for name in COST_FIELDS:
            if getattr(offer, name) is None:
                issues.append("unknown_" + name)
        total = None
        if not issues:
            assert all(getattr(offer, name) is not None for name in COST_FIELDS)
            total = (
                scenario.advance
                + offer.monthly_payment * scenario.term_months
                + offer.buyout
                + offer.upfront_fee
                + offer.recurring_monthly_fee * scenario.term_months
                + offer.insurance_total
                + offer.other_costs
            ).quantize(CENT)
        raw.append((offer, total, tuple(issues)))
    valid_totals = sorted(set(total for _, total, _ in raw if total is not None))
    enough = sum(total is not None for _, total, _ in raw) >= 2
    ranks = {total: 1 + sum(t < total for _, total2, _ in raw
                            if total2 is not None for t in [total2])
             for total in valid_totals} if enough else {}
    rows = tuple(ComparisonRow(o.offer_id, o.lessor, cost,
                               ranks.get(cost) if cost is not None else None, issues)
                 for o, cost, issues in raw)
    return Comparison(scenario, rows, as_of, sum(total is not None for _, total, _ in raw))
