"""Synthetic-only tests. Run: python -m unittest discover -s broker -p test_*.py -v"""
import unittest
from datetime import date, timedelta
from decimal import Decimal as D
from dataclasses import replace
from offer_comparison import Offer, Scenario, compare_offers

TODAY = date(2026, 11, 27)
SCENARIO = Scenario(D("4500000.00"), D("900000.00"), 36, "included")


def offer(oid: str, monthly: str = "120000.00", **changes) -> Offer:
    data = dict(
        offer_id=oid, lessor="Проверенный лизингодатель",
        source_document_id="doc-original-001", received_on=TODAY - timedelta(days=1),
        valid_until=TODAY + timedelta(days=30),
        scenario=SCENARIO, verified_by_broker=True,
        monthly_payment=D(monthly), buyout=D("1000.00"), upfront_fee=D("5000.00"),
        recurring_monthly_fee=D("500.00"), insurance_total=D("30000.00"),
        other_costs=D("0.00"),
    )
    data.update(changes)
    return Offer(**data)


class OfferComparisonTests(unittest.TestCase):
    def test_two_real_source_offers_rank_on_all_explicit_cashflows(self):
        result = compare_offers(SCENARIO, [offer("off-a", "125000"),
                                          offer("off-b", "120000")], as_of=TODAY)
        self.assertEqual(result.comparable_count, 2)
        by_id = {r.offer_id: r for r in result.rows}
        expected_b = D("900000") + D("120000")*36 + D("1000") + D("5000") + D("500")*36 + D("30000")
        self.assertEqual(by_id["off-b"].total_cash_outflow, expected_b)
        self.assertEqual(by_id["off-b"].rank, 1)
        self.assertEqual(by_id["off-a"].rank, 2)
        self.assertEqual(by_id["off-b"].blockers, ())

    def test_ties_have_shared_rank_and_stable_original_order(self):
        result = compare_offers(SCENARIO, [offer("off-b", "120000"), offer("off-a", "120000"),
                                         offer("off-c", "125000")], as_of=TODAY)
        self.assertEqual([r.offer_id for r in result.rows], ["off-b", "off-a", "off-c"])
        self.assertEqual([r.rank for r in result.rows], [1, 1, 3])

    def test_unknown_charge_is_not_guessed_or_ranked(self):
        result = compare_offers(SCENARIO, [offer("off-a", insurance_total=None),
                                         offer("off-b")], as_of=TODAY)
        self.assertIn("unknown_insurance_total", result.rows[0].blockers)
        self.assertIsNone(result.rows[0].total_cash_outflow)
        self.assertIsNone(result.rows[0].rank)
        self.assertIsNone(result.rows[1].rank)  # only one valid offer

    def test_unverified_expired_and_future_offers_blocked(self):
        result = compare_offers(SCENARIO,
            [offer("off-a", verified_by_broker=False),
             offer("off-b", valid_until=TODAY - timedelta(days=1)),
             offer("off-c", received_on=TODAY + timedelta(days=1),
                   valid_until=TODAY + timedelta(days=2))], as_of=TODAY)
        self.assertEqual(result.comparable_count, 0)
        self.assertEqual([r.blockers[0] for r in result.rows],
                         ["unverified_source", "expired", "future_received_date"])

    def test_different_term_price_advance_or_vat_blocked(self):
        variations = [
            replace(SCENARIO, term_months=48),
            replace(SCENARIO, asset_price=D("4600000")),
            replace(SCENARIO, advance=D("1200000")),
            replace(SCENARIO, vat_basis="excluded"),
        ]
        result = compare_offers(SCENARIO,
            [offer(f"off-{i}", scenario=s) for i, s in enumerate(variations)],
            as_of=TODAY)
        self.assertEqual(result.comparable_count, 0)
        self.assertTrue(all("different_scenario" in r.blockers for r in result.rows))

    def test_duplicate_identity_rejected_and_twenty_limit(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            compare_offers(SCENARIO, [offer("off-x"), offer("off-x")], as_of=TODAY)
        with self.assertRaisesRegex(ValueError, "2..20"):
            compare_offers(SCENARIO, [offer(f"off-{i}") for i in range(21)], as_of=TODAY)

    def test_float_negative_nan_and_subkopeck_rejected(self):
        for bad in [12.99, D("-1"), D("NaN"), D("Infinity"), D("1.001")]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    offer("off-x", other_costs=bad)
        with self.assertRaises(ValueError):
            Scenario(D("4500000"), D("4600000"), 36, "included")
        with self.assertRaises(ValueError):
            Scenario(D("4500000"), D("900000"), True, "included")

    def test_original_document_required_and_finite_sources(self):
        with self.assertRaisesRegex(ValueError, "opaque IDs"):
            offer("off-a", source_document_id="https://external.example/contract.pdf")
        with self.assertRaisesRegex(ValueError, "opaque IDs"):
            offer("off-a", source_document_id="")
        with self.assertRaisesRegex(ValueError, "lessor"):
            offer("off-a", lessor="")

    def test_no_tax_benefit_or_interest_derived(self):
        result = compare_offers(SCENARIO, [offer("off-a"), offer("off-b")], as_of=TODAY)
        self.assertIn("No inferred VAT", result.methodology)
        self.assertIn("not APR".lower(), ("not apr " + result.methodology).lower())


if __name__ == "__main__":
    unittest.main()
