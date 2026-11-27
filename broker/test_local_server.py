"""Loopback-only browser/API integration tests on synthetic monetary values.

No real personal data, no external internet. Python 3.12 standard library.
"""
import json
import pathlib
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_server import LocalApp, make_handler


class OperatorApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LocalApp(pathlib.Path(self.tmp.name) / "local.sqlite3",
                            "synthetic-local-only-password-2026")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])
        self.cookie = ""
        self.csrf = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def call(self, path, data=None, *, authenticated=True,
             origin=True, csrf=True, content_type="application/json"):
        headers = {}
        if data is not None:
            headers["Content-Type"] = content_type
            if origin:
                headers["Origin"] = self.base
            if authenticated and self.cookie:
                headers["Cookie"] = self.cookie
            if csrf and self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        elif authenticated and self.cookie:
            headers["Cookie"] = self.cookie
        request = Request(self.base + path,
                          data=json.dumps(data).encode("utf-8") if data is not None else None,
                          headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                return response.status, json.loads(raw) if response.headers.get_content_type() == "application/json" else raw, response.headers
        except HTTPError as exc:
            return exc.code, json.loads(exc.read()), exc.headers

    def login(self):
        code, payload, headers = self.call("/api/login",
            {"password": "synthetic-local-only-password-2026"}, authenticated=False)
        self.assertEqual(code, 200)
        self.assertTrue(payload["authenticated"])
        self.cookie = headers.get("Set-Cookie").split(";", 1)[0]
        self.csrf = payload["csrf"]

    def test_static_page_is_local_and_does_not_load_external_assets(self):
        for path in ["/", "/broker-preview.js"]:
            status, body, headers = self.call(path)
            self.assertEqual(status, 200)
            self.assertIn(b"Compass", body)
            self.assertIn("no-store", headers["Cache-Control"])
        self.assertEqual(self.call("/.env")[0], 404)
        self.assertEqual(self.call("/broker/sqlite_store.py")[0], 404)

    def test_login_required_for_read_and_write(self):
        self.assertEqual(self.call("/api/cases")[0], 401)
        self.assertEqual(self.call("/api/cases", {
            "asset_price": "4500000", "advance": "900000",
            "term_months": 36, "vat_basis": "included"})[0], 403)
        self.assertEqual(self.call("/api/session")[1]["authenticated"], False)
        code, body, _ = self.call("/api/login",
            {"password": "wrong-password"}, authenticated=False)
        self.assertEqual(code, 401)
        self.assertEqual(body["error"], "login_denied")

    def test_csrf_origin_and_unknown_personal_fields_denied(self):
        self.login()
        d = {"asset_price": "4500000", "advance": "900000",
             "term_months": 36, "vat_basis": "included"}
        self.assertEqual(self.call("/api/cases", d, origin=False)[0], 403)
        self.assertEqual(self.call("/api/cases", d, csrf=False)[0], 403)
        self.assertEqual(self.call("/api/cases", {**d, "phone": "+79990000000"})[0], 400)
        self.assertEqual(self.call("/api/cases", {**d, "name": "Test Person"})[0], 400)
        self.assertEqual(self.call("/api/cases", {**d, "term_months": True})[0], 400)
        self.assertEqual(self.call("/api/cases", {**d, "advance": "-1"})[0], 400)
        self.assertEqual(self.call("/api/cases", {**d, "asset_price": 4500000})[0], 400)
        self.assertEqual(self.call("/api/cases")[1]["cases"], [])

    def test_financial_case_persists_and_comparison_is_real(self):
        self.login()
        code, record, _ = self.call("/api/cases", {
            "asset_price": "4500000", "advance": "900000",
            "term_months": 36, "vat_basis": "included"})
        self.assertEqual(code, 201)
        self.assertEqual(record["version"], 1)
        cid = record["case_id"]
        self.assertEqual(len(self.call("/api/cases")[1]["cases"]), 1)
        code, record, _ = self.call(f"/api/cases/{cid}/stage", {
            "target": "collecting", "expected_version": 1})
        self.assertEqual(code, 200)
        self.assertEqual(record["version"], 2)
        from datetime import date, timedelta
        today = date.today()
        for number, amount in [(1, "120000"), (2, "110000")]:
            d = {
                "offer_id": f"off-{number:03d}",
                "lessor": f"Synthetic lessor {number}",
                "source_document_id": f"doc-{number:03d}",
                "received_on": today.isoformat(),
                "valid_until": (today + timedelta(days=14)).isoformat(),
                "verified_by_broker": True,
                "expected_version": record["version"],
                "monthly_payment": amount, "buyout": "1000",
                "upfront_fee": "5000", "recurring_monthly_fee": "500",
                "insurance_total": "30000", "other_costs": "0"
            }
            code, record, _ = self.call(f"/api/cases/{cid}/offers", d)
            self.assertEqual(code, 200)
        code, result, _ = self.call(f"/api/cases/{cid}/comparison")
        self.assertEqual(code, 200)  # comparison allowed in collecting stage
        self.assertEqual(result["comparable_count"], 2)
        code, rec, _ = self.call(f"/api/cases/{cid}/stage", {
            "target": "comparing", "expected_version": record["version"]})
        self.assertEqual(code, 200)
        code, result, _ = self.call(f"/api/cases/{cid}/comparison")
        self.assertEqual(code, 200)
        self.assertEqual(result["comparable_count"], 2)
        scores = {r["offer_id"]: r for r in result["rows"]}
        self.assertEqual(scores["off-002"]["rank"], 1)
        self.assertEqual(scores["off-001"]["rank"], 2)
        self.assertEqual(float(scores["off-002"]["total_cash_outflow"]), 4914000)
        self.assertEqual(len(self.call(f"/api/cases/{cid}/audit")[1]["events"]), rec["version"])
        self.assertEqual(self.call(f"/api/cases/{cid}/stage", {
            "target": "closed", "expected_version": rec["version"]})[0], 200)
        self.assertEqual(self.call("/api/logout", {})[0], 200)
        self.assertEqual(self.call("/api/cases")[0], 401)

    def test_traversal_and_unauthorized_case_are_hidden(self):
        self.login()
        self.assertEqual(self.call("/api/cases/00000000-0000-4000-8000-000000000000/audit")[0], 403)
        self.assertEqual(self.call("/../.env")[0], 404)


if __name__ == "__main__":
    unittest.main()
