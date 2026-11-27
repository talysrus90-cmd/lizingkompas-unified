"""Compass Broker local operator service — financial scenarios only.

Run from repository root with Python 3.12+, no third-party packages:
    python broker/local_server.py
It prompts for a password (minimum 14 characters) and binds ONLY 127.0.0.1.
Open http://127.0.0.1:8765/ ON THE SAME PC. Database location defaults to a
dedicated folder under the current user's home directory, never the public repo.

This is a private *development workstation* tool, NOT a deployed website.
It deliberately REJECTS client names, phone numbers, INNs, contracts, uploads
and any unknown JSON fields. Never run this on a public interface or with
real personal data until production security, legal grounds and operations pass.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from getpass import getpass
from hashlib import sha256
from hmac import compare_digest
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit
from secrets import token_urlsafe
import json
import os
import re

from access_policy import Actor
from offer_comparison import COST_FIELDS, Offer, Scenario
from sqlite_store import SqliteCaseDesk

HOST = "127.0.0.1"
PORT = 8765
MAX_REQUEST = 12_288
SESSION_TTL = 30 * 60
ROOT = Path(__file__).resolve().parent.parent
JSON_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}
CSP = ("default-src 'none'; script-src 'self'; connect-src 'self'; "
       "style-src 'unsafe-inline'; img-src 'self' data:; "
       "base-uri 'none'; form-action 'none'; object-src 'none'; frame-ancestors 'none'")
PATHS = {
    "/": ("broker-preview.html", "text/html; charset=utf-8"),
    "/broker-preview.js": ("broker-preview.js", "text/javascript; charset=utf-8"),
    "/broker-local-ui.js": ("broker-local-ui.js", "text/javascript; charset=utf-8"),
}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")


def _strict_json(raw: bytes, expected_fields: set[str]) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    if type(data) is not dict or set(data) != expected_fields:
        raise ValueError("unexpected_fields")
    return data


def _number(value: object) -> Decimal:
    if type(value) is not str or len(value) > 25 or not re.fullmatch(r"[0-9]{1,13}(?:\.[0-9]{1,2})?", value):
        raise ValueError("invalid_money")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid_money") from exc


def _scenario(data: dict) -> Scenario:
    if type(data.get("term_months")) is not int:
        raise ValueError("invalid_term")
    return Scenario(
        _number(data["asset_price"]),
        _number(data["advance"]),
        data["term_months"], data["vat_basis"],
        "RUB"
    )


def _case_payload(record) -> dict:
    return {
        "case_id": record.case_id, "version": record.version,
        "stage": record.stage, "offer_count": len(record.offer_ids),
        "asset_price": str(record.scenario.asset_price),
        "advance": str(record.scenario.advance),
        "term_months": record.scenario.term_months,
        "vat_basis": record.scenario.vat_basis,
    }


class LocalApp:
    def __init__(self, db_path: str | os.PathLike, password: str):
        if not isinstance(password, str) or len(password) < 14:
            raise ValueError("local password must be at least 14 characters")
        self.password_digest = sha256(password.encode()).digest()
        self.desk = SqliteCaseDesk(db_path)
        self.sessions: dict[str, tuple[str, float]] = {}
        self.failed_attempts: list[float] = []
        self.lock = Lock()
        self.actor = Actor("local-operator", "local-tenant", "supervisor")

    def verify_login(self, supplied: object) -> tuple[str, str] | None:
        with self.lock:
            now = monotonic()
            self.failed_attempts = [at for at in self.failed_attempts if now - at < 60]
            if len(self.failed_attempts) >= 5:
                return None
            if type(supplied) is not str or not compare_digest(
                sha256(supplied.encode("utf-8")).digest(), self.password_digest
            ):
                self.failed_attempts.append(now)
                return None
            session, csrf = token_urlsafe(32), token_urlsafe(32)
            self.sessions[session] = (csrf, now + SESSION_TTL)
            return session, csrf

    def get_session(self, token: str) -> str | None:
        with self.lock:
            value = self.sessions.get(token)
            if not value:
                return None
            csrf, expiry = value
            if monotonic() >= expiry:
                self.sessions.pop(token, None)
                return None
            return csrf

    def forget_session(self, token: str):
        with self.lock:
            self.sessions.pop(token, None)

    def list_cases(self) -> list[dict]:
        return [_case_payload(x) for x in self.desk.list_assigned(self.actor)]


def make_handler(app: LocalApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CompassLocal/0.1"
        sys_version = ""
        def log_message(self, *args):  # Never log request paths, bodies or credentials
            pass

        @property
        def origin(self):
            return "http://127.0.0.1:" + str(self.server.server_address[1])

        def _send(self, code, payload, extra=None):
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            for k, v in JSON_HEADERS.items():
                self.send_header(k, v)
            self.send_header("Content-Security-Policy", CSP)
            if extra:
                for k, v in extra.items():
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _fail(self, code, reason):
            self._send(code, {"error": reason})

        def _same_origin(self):
            return (self.headers.get("Host") == "127.0.0.1:" + str(self.server.server_address[1])
                    and self.client_address[0] == "127.0.0.1")

        def _session_id(self):
            try:
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                value = cookie.get("compass_local_session")
                return value.value if value else ""
            except Exception:
                return ""

        def _auth(self, is_write=False):
            csrf = app.get_session(self._session_id())
            if not csrf:
                return False
            if is_write and not compare_digest(self.headers.get("X-CSRF-Token", ""), csrf):
                return False
            return True

        def do_GET(self):
            if not self._same_origin():
                return self._fail(HTTPStatus.FORBIDDEN, "local_only")
            path = urlsplit(self.path).path
            if path in PATHS:
                filename, mime = PATHS[path]
                source = (ROOT / filename).read_bytes()
                self.send_response(HTTPStatus.OK)
                for k, v in JSON_HEADERS.items():
                    if k != "Content-Type":
                        self.send_header(k, v)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Security-Policy", CSP)
                self.send_header("Content-Length", str(len(source)))
                self.end_headers()
                self.wfile.write(source)
                return
            if path == "/api/session":
                csrf = app.get_session(self._session_id())
                return self._send(HTTPStatus.OK,
                                  {"authenticated": bool(csrf), "csrf": csrf or None})
            if path == "/api/cases":
                if not self._auth():
                    return self._fail(HTTPStatus.UNAUTHORIZED, "login_required")
                return self._send(HTTPStatus.OK, {"cases": app.list_cases()})
            match = re.fullmatch(r"/api/cases/([0-9a-f-]{36})/(comparison|audit)", path)
            if match:
                if not self._auth():
                    return self._fail(HTTPStatus.UNAUTHORIZED, "login_required")
                case_id, action = match.groups()
                try:
                    if action == "audit":
                        events = app.desk.audit(app.actor, case_id)
                        return self._send(HTTPStatus.OK, {"events": [
                            {"action": e.action, "version": e.version, "at": e.created_at}
                            for e in events
                        ]})
                    result = app.desk.compare(app.actor, case_id, date.today())
                    return self._send(HTTPStatus.OK, {
                        "comparable_count": result.comparable_count,
                        "rows": [
                            {"offer_id": r.offer_id, "lessor": r.lessor,
                             "total_cash_outflow": str(r.total_cash_outflow) if r.total_cash_outflow is not None else None,
                             "rank": r.rank, "blockers": r.blockers}
                            for r in result.rows
                        ],
                    })
                except PermissionError:
                    return self._fail(HTTPStatus.FORBIDDEN, "access_denied")
                except ValueError:
                    return self._fail(HTTPStatus.CONFLICT, "not_comparable")
            return self._fail(HTTPStatus.NOT_FOUND, "not_found")

        def do_POST(self):
            if not self._same_origin() or self.headers.get("Origin") != self.origin:
                return self._fail(HTTPStatus.FORBIDDEN, "origin_denied")
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                return self._fail(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "json_required")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST:
                    return self._fail(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_limit")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("short_body")
            except (ValueError, OverflowError):
                return self._fail(HTTPStatus.BAD_REQUEST, "invalid_length")
            path = urlsplit(self.path).path
            if path == "/api/login":
                try:
                    payload = _strict_json(raw, {"password"})
                except (ValueError, UnicodeError, json.JSONDecodeError):
                    return self._fail(HTTPStatus.BAD_REQUEST, "invalid_login")
                identity = app.verify_login(payload["password"])
                if not identity:
                    return self._fail(HTTPStatus.UNAUTHORIZED, "login_denied")
                session, csrf = identity
                return self._send(HTTPStatus.OK, {"authenticated": True, "csrf": csrf},
                                  {"Set-Cookie": "compass_local_session=" + session +
                                   "; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800"})
            if not self._auth(is_write=True):
                return self._fail(HTTPStatus.FORBIDDEN, "csrf_or_session")
            if path == "/api/logout":
                app.forget_session(self._session_id())
                return self._send(HTTPStatus.OK, {"authenticated": False},
                                  {"Set-Cookie": "compass_local_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            if path == "/api/cases":
                try:
                    payload = _strict_json(raw, {"asset_price", "advance", "term_months", "vat_basis"})
                    record = app.desk.create(app.actor, _scenario(payload))
                    return self._send(HTTPStatus.CREATED, _case_payload(record))
                except (ValueError, KeyError, TypeError):
                    return self._fail(HTTPStatus.BAD_REQUEST, "invalid_financial_scenario")
            match = re.fullmatch(r"/api/cases/([0-9a-f-]{36})/(offers|stage)", path)
            if match:
                case_id, operation = match.groups()
                try:
                    if operation == "stage":
                        data = _strict_json(raw, {"target", "expected_version"})
                        result = app.desk.move(app.actor, case_id, data["target"], data["expected_version"])
                    else:
                        all_fields = {"offer_id", "lessor", "source_document_id", "received_on",
                                      "valid_until", "verified_by_broker", "expected_version"} | set(COST_FIELDS)
                        data = _strict_json(raw, all_fields)
                        record = app.desk.get(app.actor, case_id)
                        offer = Offer(
                            offer_id=data["offer_id"], lessor=data["lessor"],
                            source_document_id=data["source_document_id"],
                            received_on=date.fromisoformat(data["received_on"]),
                            valid_until=date.fromisoformat(data["valid_until"]),
                            scenario=record.scenario,
                            verified_by_broker=data["verified_by_broker"],
                            **{name: (_number(data[name]) if data[name] is not None else None)
                               for name in COST_FIELDS}
                        )
                        result = app.desk.add_offer(app.actor, case_id, offer, data["expected_version"])
                    return self._send(HTTPStatus.OK, _case_payload(result))
                except PermissionError:
                    return self._fail(HTTPStatus.FORBIDDEN, "access_denied")
                except (ValueError, TypeError, KeyError):
                    return self._fail(HTTPStatus.CONFLICT, "invalid_operation_or_version")
            return self._fail(HTTPStatus.NOT_FOUND, "not_found")

    return Handler


def serve():
    db = os.environ.get("LK_LOCAL_DB", "")
    location = Path(db).expanduser().resolve() if db else Path.home() / "CompassBrokerLocal" / "broker.sqlite3"
    password = os.environ.get("LK_LOCAL_PASSWORD") or getpass("Пароль локального брокера (14+ символов): ")
    app = LocalApp(location, password)
    with ThreadingHTTPServer((HOST, PORT), make_handler(app)) as server:
        print(f"Локальный брокер: http://{HOST}:{PORT}/")
        print("Только на этом ПК. Реальные персональные данные не вводить.")
        try:
            server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    serve()
