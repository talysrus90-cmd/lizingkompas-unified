#!/usr/bin/env python3
"""Leasing Compass launch preflight. No secrets or personal data are printed.

This is a CHECK, not a deployment, purchase or legal approval.
Usage on approved Russian VPS:
  python production/ops/preflight.py \
      --env production/.env.production \
      --site /srv/leasingcompass/site-public \
      --domain leasingcompass.ru
Add --require-live only for the actual go-live control meeting.

Python 3.12, standard library, does not mutate source, DB, DNS or registry.
"""
import argparse
import base64
import json
import pathlib
import re
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

BANNED_STATIC_FILES = [
    "broker-preview.html", "broker-preview.js", "broker-local-ui.js",
    "cabinet.html", "platform.html", "self-service.html", ".env.production",
    "production", "broker", ".git"
]
LEGAL_DRAFT_TEXT = (
    "Проект для согласования с оператором",
    "Планируемый оператор",
    "Адрес оператора для юридически значимых обращений будет уточнён",
    "окончательная редакция утверждается",
)
DOMAIN = "leasingcompass.ru"


def valid_fernet_key(key):
    """Fernet uses a 32-byte key encoded as 44 URL-safe base64 chars."""
    if not isinstance(key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}=",key):
        return False
    try:
        return len(base64.urlsafe_b64decode(key.encode("ascii")))==32
    except (ValueError,TypeError):
        return False


def env_read(path):
    # No shell execution; never print values; only exact KEY=VALUE records.
    if not path.is_file():
        return {}
    output={}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped=line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key,value=stripped.split("=",1)
        key=key.strip()
        if re.fullmatch(r"[A-Z0-9_]+",key):
            output[key]=value.strip().strip("\"'")
    return output


def secure_response(url):
    request=urllib.request.Request(url,headers={"User-Agent":"CompassPreflight/1.0"})
    try:
        with urllib.request.urlopen(request,timeout=8,context=ssl.create_default_context()) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError,ValueError):
        return None


def inspect_settings(env,site,domain,network=False):
    checks={}
    checks["primary_domain"]=domain==DOMAIN
    checks["operator_identity"]=(
        env.get("COMPASS_OPERATOR_NAME","").startswith("ИП Гасанов")
        and re.fullmatch(r"\d{10}|\d{12}",env.get("COMPASS_OPERATOR_INN","")) is not None
    )
    checks["production_mode"]=env.get("COMPASS_PRODUCTION")=="1"
    checks["approved_policy"]=env.get("COMPASS_POLICY_APPROVED")=="yes"
    checks["rkn_scope_confirmed"]=env.get("COMPASS_RKN_SCOPE_CONFIRMED")=="yes"
    checks["restore_test_passed"]=env.get("COMPASS_RESTORE_TEST_PASSED")=="yes"
    checks["fernet_keys_configured"]=bool(env.get("COMPASS_FERNET_KEYS")) and all(
        valid_fernet_key(key.strip())
        for key in env.get("COMPASS_FERNET_KEYS","").split(",")
    )
    checks["database_configured"]=env.get("DATABASE_URL","").startswith("postgresql://") and (
        "REPLACE" not in env.get("DATABASE_URL","")
    )
    checks["secret_key_configured"]=len(env.get("DJANGO_SECRET_KEY",""))>=50 and (
        "REPLACE" not in env.get("DJANGO_SECRET_KEY","")
    )
    checks["throttle_key_configured"]=len(env.get("COMPASS_THROTTLE_SECRET",""))>=32 and (
        "REPLACE" not in env.get("COMPASS_THROTTLE_SECRET","")
    )
    checks["consent_version"]=bool(env.get("COMPASS_CONSENT_VERSION")) and (
        "REPLACE" not in env.get("COMPASS_CONSENT_VERSION","")
    )
    checks["site_index"]=site.joinpath("index.html").is_file()
    checks["site_no_private"]=all(not site.joinpath(f).exists() for f in BANNED_STATIC_FILES)
    if checks["site_index"]:
        html=site.joinpath("index.html").read_text(encoding="utf-8")
        checks["production_v5"]=(
            "Лизинг Компас" in html
            and '<meta name="robots" content="index,follow">' in html
            and 'href="/apply/"' in html
            and 'href="/callback/"' in html
            and "broker-preview.html" not in html
        )
    else:
        checks["production_v5"]=False
    legal_files=[site.joinpath(name) for name in ("privacy.html","consent.html")]
    checks["legal_pages_exist"]=all(f.is_file() for f in legal_files)
    checks["no_legal_drafts"]=checks["legal_pages_exist"] and all(
        not any(x.lower() in f.read_text(encoding="utf-8").lower()
                for x in LEGAL_DRAFT_TEXT) for f in legal_files
    )
    if network:
        checks["public_https_home"]=secure_response("https://"+domain+"/")==200
        checks["public_admin_blocked"]=secure_response("https://"+domain+"/admin/")==404
        checks["public_apply_online"]=secure_response("https://"+domain+"/apply/")==200
        checks["public_callback_online"]=secure_response("https://"+domain+"/callback/")==200
    return checks


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--env",required=True)
    parser.add_argument("--site",required=True)
    parser.add_argument("--domain",default=DOMAIN)
    parser.add_argument("--require-live",action="store_true")
    args=parser.parse_args()
    env=env_read(pathlib.Path(args.env))
    checks=inspect_settings(env,pathlib.Path(args.site),args.domain,args.require_live)
    checks["intake_enabled"]=env.get("COMPASS_LIVE_INTAKE")=="yes"
    ready=all(checks.values())
    print(json.dumps({
        "ready_for_live":ready,
        "checks":checks,
        "failed":[key for key,passed in checks.items() if not passed],
        "message":"No credentials, customer details, files or database records are emitted."
    },indent=2,ensure_ascii=False))
    if args.require_live and not ready:
        sys.exit(2)


if __name__=="__main__":
    main()
