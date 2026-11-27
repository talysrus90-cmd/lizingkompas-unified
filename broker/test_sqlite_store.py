"""Synthetic-only SQLite case workflow tests. No network and no real clients.

Run: python -m unittest discover -s broker -p 'test_*.py' -v
"""
import os
import pathlib
import sqlite3
import tempfile
from contextlib import closing
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D

from access_policy import Actor
from offer_comparison import Scenario, Offer
from sqlite_store import SqliteCaseDesk

NOW = date(2026, 11, 27)
S = Scenario(D("4500000"), D("900000"), 36, "included")


def quote(oid: str, monthly: str = "120000") -> Offer:
    return Offer(oid, "Тестовый лизингодатель", "doc-" + oid,
                 NOW - timedelta(days=1), NOW + timedelta(days=15),
                 S, True, D(monthly), D("1000"), D("5000"), D("500"),
                 D("30000"), D("0"))


class SqliteStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="lk-synthetic-")
        self.path = pathlib.Path(self.folder.name) / "demo.sqlite3"
        self.broker = Actor("broker-1", "tenant-1", "broker")
        self.supervisor = Actor("supervisor-1", "tenant-1", "supervisor")
        self.desk = SqliteCaseDesk(self.path)

    def tearDown(self):
        self.folder.cleanup()

    def test_restart_persistence_and_comparison(self):
        rec = self.desk.create(self.supervisor, S)
        rec = self.desk.assign(self.supervisor, rec.case_id, self.broker.user_id,
                               rec.version)
        rec = self.desk.move(self.broker, rec.case_id, "collecting", rec.version)
        rec = self.desk.add_offer(self.broker, rec.case_id,
                                  quote("off-one", "130000"), rec.version)
        rec = self.desk.add_offer(self.broker, rec.case_id,
                                  quote("off-two", "120000"), rec.version)
        self.desk = SqliteCaseDesk(self.path)
        restored = self.desk.get(self.broker, rec.case_id)
        self.assertEqual(restored.stage, "collecting")
        self.assertEqual(restored.version, rec.version)
        self.assertEqual(restored.offer_ids, ("off-one", "off-two"))
        ranking = self.desk.compare(self.broker, rec.case_id, NOW)
        self.assertEqual([r.rank for r in ranking.rows], [2, 1])
        self.assertEqual(ranking.comparable_count, 2)
        rec = self.desk.move(self.broker, rec.case_id, "comparing",
                             restored.version)
        rec = self.desk.move(self.supervisor, rec.case_id, "closed", rec.version)
        self.assertEqual(rec.stage, "closed")
        self.assertEqual([e.action for e in self.desk.audit(self.supervisor, rec.case_id)],
                         ["case.created", "case.assigned", "case.stage_changed",
                          "offer.added", "offer.added", "case.stage_changed",
                          "case.stage_changed"])
        self.assertEqual(len(self.desk.audit(self.supervisor, rec.case_id)), rec.version)

    def test_cross_tenant_and_bogus_browser_scope_are_denied(self):
        rec = self.desk.create(self.broker, S)
        for intruder in [
            Actor("different", "tenant-1", "broker", frozenset((rec.case_id,))),
            Actor("broker-1", "tenant-2", "broker", frozenset((rec.case_id,))),
            Actor("admin-1", "tenant-1", "admin", frozenset((rec.case_id,))),
        ]:
            with self.subTest(intruder=intruder):
                with self.assertRaises(PermissionError):
                    self.desk.get(intruder, rec.case_id)
                with self.assertRaises(PermissionError):
                    self.desk.add_offer(intruder, rec.case_id,
                                        quote("off-attack"), rec.version)
        with self.assertRaises(PermissionError):
            self.desk.get(self.broker, "unknown-case")

    def test_concurrent_version_conflict_and_no_partial_write(self):
        rec = self.desk.create(self.broker, S)
        other_connection = SqliteCaseDesk(self.path)
        next_rec = other_connection.add_offer(self.broker, rec.case_id,
                                             quote("off-one"), rec.version)
        with self.assertRaisesRegex(ValueError, "version_conflict"):
            self.desk.add_offer(self.broker, rec.case_id,
                                quote("off-two"), rec.version)
        self.assertEqual(self.desk.get(self.broker, rec.case_id).offer_ids,
                         ("off-one",))
        self.assertEqual(next_rec.version, rec.version + 1)
        with closing(sqlite3.connect(self.path)) as connection:
            n = connection.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
            self.assertEqual(n, 2)

    def test_duplicate_document_and_offer_rejected(self):
        rec = self.desk.create(self.broker, S)
        rec = self.desk.add_offer(self.broker, rec.case_id, quote("off-one"),
                                  rec.version)
        with self.assertRaisesRegex(ValueError, "duplicate_offer_or_source"):
            self.desk.add_offer(self.broker, rec.case_id, quote("off-one"),
                                rec.version)
        with self.assertRaisesRegex(ValueError, "duplicate_offer_or_source"):
            self.desk.add_offer(self.broker, rec.case_id,
                                replace(quote("off-two"),
                                        source_document_id="doc-off-one"),
                                rec.version)
        self.assertEqual(self.desk.get(self.broker, rec.case_id).version,
                         rec.version)

    def test_workflow_guards_and_assignment(self):
        rec = self.desk.create(self.supervisor, S)
        with self.assertRaises(PermissionError):
            self.desk.assign(self.broker, rec.case_id, "broker-1", rec.version)
        with self.assertRaises(PermissionError):
            self.desk.get(self.broker, rec.case_id)
        rec = self.desk.assign(self.supervisor, rec.case_id, "broker-1",
                               rec.version)
        rec = self.desk.move(self.broker, rec.case_id, "collecting", rec.version)
        with self.assertRaisesRegex(ValueError, "two_offers_required"):
            self.desk.move(self.broker, rec.case_id, "comparing", rec.version)
        with self.assertRaises(PermissionError):
            self.desk.audit(self.broker, rec.case_id)
        with self.assertRaisesRegex(ValueError, "version_conflict"):
            self.desk.assign(self.supervisor, rec.case_id, "other-user", 1)

    def test_invalid_db_location_and_permissions(self):
        with self.assertRaises(ValueError):
            SqliteCaseDesk("relative.sqlite3")
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
