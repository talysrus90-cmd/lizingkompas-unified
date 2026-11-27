"""Synthetic workflow invariants; Python standard library only."""
import unittest
from datetime import date, timedelta
from decimal import Decimal as D
from access_policy import Actor
from case_workflow import CaseDesk
from offer_comparison import Offer, Scenario

NOW = date(2026, 11, 27)
S = Scenario(D("4500000"), D("900000"), 36, "included")


def quote(id: str, monthly: str = "120000") -> Offer:
    return Offer(id, "Лизингодатель (пример)", "doc-" + id, NOW - timedelta(days=2),
                 NOW + timedelta(days=30), S, True, D(monthly),
                 D("1000"), D("5000"), D("500"), D("30000"), D("0"))


class CaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.desk = CaseDesk()
        self.broker = Actor("broker-a", "tenant-a", "broker")
        self.case = self.desk.create(self.broker, S)

    def test_case_created_for_owner_only(self):
        self.assertEqual(self.case.stage, "draft")
        self.assertEqual(self.case.version, 1)
        self.assertEqual(self.desk.get(self.broker, self.case.case_id).case_id, self.case.case_id)

    def test_unknown_or_other_tenant_cannot_access_case(self):
        attackers = [
            Actor("other", "tenant-a", "broker", frozenset((self.case.case_id,))),
            Actor("broker-a", "tenant-b", "broker", frozenset((self.case.case_id,))),
            Actor("admin", "tenant-a", "admin", frozenset((self.case.case_id,))),
        ]
        for actor in attackers:
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionError):
                    self.desk.get(actor, self.case.case_id)
                with self.assertRaises(PermissionError):
                    self.desk.add_offer(actor, self.case.case_id, quote("off-2"), 1)
        with self.assertRaises(PermissionError):
            self.desk.get(self.broker, "not-a-real-case")

    def test_case_progresses_and_compares_two_verified_offers(self):
        first = self.desk.add_offer(self.broker, self.case.case_id, quote("off-1", "125000"), 1)
        second = self.desk.add_offer(self.broker, self.case.case_id, quote("off-2", "120000"), 2)
        self.assertEqual((first.version, second.version), (2, 3))
        stage = self.desk.move(self.broker, self.case.case_id, "collecting", 3)
        stage = self.desk.move(self.broker, self.case.case_id, "comparing", stage.version)
        result = self.desk.compare(self.broker, self.case.case_id, NOW)
        self.assertEqual(result.comparable_count, 2)
        self.assertEqual([r.rank for r in result.rows], [2, 1])

    def test_comparison_not_available_before_two_offers(self):
        x = self.desk.move(self.broker, self.case.case_id, "collecting", 1)
        with self.assertRaisesRegex(ValueError, "two_offers_required"):
            self.desk.move(self.broker, self.case.case_id, "comparing", x.version)
        with self.assertRaises(ValueError):
            self.desk.compare(self.broker, self.case.case_id, NOW)

    def test_concurrent_version_protection(self):
        self.desk.add_offer(self.broker, self.case.case_id, quote("off-1"), 1)
        with self.assertRaisesRegex(ValueError, "version_conflict"):
            self.desk.add_offer(self.broker, self.case.case_id, quote("off-2"), 1)
        self.assertEqual(len(self.desk.get(self.broker, self.case.case_id).offer_ids), 1)

    def test_duplicate_offer_and_incompatible_scenario_rejected(self):
        self.desk.add_offer(self.broker, self.case.case_id, quote("off-1"), 1)
        with self.assertRaisesRegex(ValueError, "duplicate_offer"):
            self.desk.add_offer(self.broker, self.case.case_id, quote("off-1"), 2)
        from dataclasses import replace
        with self.assertRaisesRegex(ValueError, "duplicate_original_document"):
            self.desk.add_offer(self.broker, self.case.case_id,
                                replace(quote("off-2"), source_document_id="doc-off-1"), 2)
        incompatible = Scenario(D("5000000"), D("900000"), 36, "included")
        o = quote("off-2")
        from dataclasses import replace
        with self.assertRaisesRegex(ValueError, "offer_scenario_mismatch"):
            self.desk.add_offer(self.broker, self.case.case_id,
                                replace(o, scenario=incompatible), 2)

    def test_closing_is_supervisor_only_and_requires_explicit_assignment(self):
        self.desk.add_offer(self.broker, self.case.case_id, quote("off-1"), 1)
        self.desk.add_offer(self.broker, self.case.case_id, quote("off-2"), 2)
        self.desk.move(self.broker, self.case.case_id, "collecting", 3)
        self.desk.move(self.broker, self.case.case_id, "comparing", 4)
        with self.assertRaises(PermissionError):
            self.desk.move(self.broker, self.case.case_id, "closed", 5)
        supervisor = Actor("supervisor-a", "tenant-a", "supervisor")
        with self.assertRaises(PermissionError):
            self.desk.move(supervisor, self.case.case_id, "closed", 5)
        # In the prototype, assignment must be issued by an already assigned
        # supervisor. Production assignment follows a separately approved policy.

    def test_supervisor_can_assign_team_and_close_after_comparison(self):
        supervisor = Actor("supervisor-a", "tenant-a", "supervisor")
        record = self.desk.create(supervisor, S)
        record = self.desk.assign(supervisor, record.case_id, self.broker.user_id, record.version)
        self.assertEqual(self.desk.get(self.broker, record.case_id).case_id, record.case_id)
        record = self.desk.move(self.broker, record.case_id, "collecting", record.version)
        record = self.desk.add_offer(self.broker, record.case_id, quote("off-1"), record.version)
        record = self.desk.add_offer(self.broker, record.case_id, quote("off-2"), record.version)
        record = self.desk.move(self.broker, record.case_id, "comparing", record.version)
        closed = self.desk.move(supervisor, record.case_id, "closed", record.version)
        self.assertEqual(closed.stage, "closed")
        with self.assertRaisesRegex(ValueError, "offers_locked"):
            self.desk.add_offer(self.broker, record.case_id, quote("off-3"), closed.version)

    def test_broker_cannot_create_with_admin_role(self):
        with self.assertRaises(PermissionError):
            self.desk.create(Actor("admin-1", "tenant-a", "admin"), S)


if __name__ == "__main__":
    unittest.main()
