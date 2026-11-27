"""Local lead intake reference service. Runs on loopback; production requires approved HTTPS reverse proxy and legal configuration."""
import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import re
import sqlite3
import uuid
from wsgiref.simple_server import make_server, WSGIRequestHandler

MAX_BODY = 8192
KINDS = {"callback", "request", "calculator", "quiz", "partner"}
FIELDS = {"name": 150, "organization": 200, "inn": 12, "phone": 30, "revenue": 16, "comment": 1200, "messenger": 30}
UTMS = {"utm_source", "utm_medium", "utm_campaign", "utm_content"}
TOKEN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

def inn_valid(v):
    if not re.fullmatch(r"[0-9]{10}|[0-9]{12}", v):
        return False
    n = list(map(int, v))
    def digit(weights):
        return sum(a*b for a,b in zip(n, weights)) % 11 % 10
    if len(n) == 10:
        return digit([2,4,10,3,5,9,4,6,8]) == n[9]
    return digit([7,2,4,10,3,5,9,4,6,8]) == n[10] and digit([3,7,2,4,10,3,5,9,4,6,8]) == n[11]

def validate(obj, consent_version):
    if not isinstance(obj, dict) or set(obj) - {"kind","fields","consent","consent_version","request_id","attribution"}:
        raise ValueError("invalid_payload")
    kind = obj.get("kind")
    if not isinstance(kind,str) or kind not in KINDS or obj.get("consent") is not True or obj.get("consent_version") != consent_version:
        raise ValueError("consent_or_kind")
    try:
        rid = str(uuid.UUID(obj.get("request_id","")))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_request_id")
    fields=obj.get("fields")
    if not isinstance(fields,dict) or set(fields)-set(FIELDS):
        raise ValueError("invalid_fields")
    clean={}
    for k,v in fields.items():
        if not isinstance(v,str) or len(v)>FIELDS[k] or any(ord(c)<32 and c not in "\n\r\t" for c in v):
            raise ValueError("invalid_field")
        if v.strip():
            clean[k]=v.strip()
    phone=clean.get("phone","")
    if not re.fullmatch(r"[+0-9() -]{10,30}",phone):
        raise ValueError("invalid_phone")
    digits=re.sub(r"[^0-9]","",phone)
    if len(digits)==11 and digits[0]=="8":
        digits="7"+digits[1:]
    if len(digits)!=11 or digits[0]!="7":
        raise ValueError("invalid_phone")
    clean["phone"]="+"+digits
    if kind=="callback" and set(clean)!={"phone"}:
        raise ValueError("callback_minimization")
    if kind!="callback" and not clean.get("name"):
        raise ValueError("missing_name")
    if kind=="request" and not all(clean.get(k) for k in ("organization","inn","revenue")):
        raise ValueError("missing_request_fields")
    if "inn" in clean and not inn_valid(clean["inn"]):
        raise ValueError("invalid_inn")
    if "revenue" in clean and not re.fullmatch(r"[0-9]{1,16}",clean["revenue"]):
        raise ValueError("invalid_revenue")
    if "messenger" in clean and clean["messenger"] not in {"Макс","MAX","Телефон","Email","E-mail","Электронная почта"}:
        raise ValueError("invalid_contact_method")
    attribution=obj.get("attribution",{})
    if not isinstance(attribution,dict) or set(attribution)-UTMS:
        raise ValueError("invalid_attribution")
    if any(not isinstance(v,str) or not TOKEN.fullmatch(v) for v in attribution.values()):
        raise ValueError("invalid_attribution")
    return rid,kind,clean,attribution

class Intake:
    def __init__(self, db, origin="", consent_version="", enabled=False):
        self.db=str(db)
        self.origin=origin
        self.version=consent_version
        self.enabled=enabled
        if enabled and (not origin.startswith("https://") or not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?::[0-9]+)?",origin) or not TOKEN.fullmatch(consent_version)):
            raise ValueError("approved HTTPS origin and consent version required")
        path=pathlib.Path(db)
        if path.exists() and not path.is_file():
            raise ValueError("invalid database")
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, created TEXT NOT NULL, kind TEXT NOT NULL, fields TEXT NOT NULL, attribution TEXT NOT NULL, consent_version TEXT NOT NULL, digest TEXT NOT NULL)")
        if os.name!="nt":
            path.chmod(0o600)
    def connect(self):
        return sqlite3.connect(self.db,timeout=5)
    def store(self, data):
        rid,kind,fields,attribution=validate(data,self.version)
        canonical=json.dumps([kind,fields,attribution,self.version],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        now=dt.datetime.now(dt.timezone.utc)
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT digest FROM leads WHERE id=?",(rid,)).fetchone()
            if row:
                if not hmac.compare_digest(row[0],digest):
                    return 409,{"error":"id_conflict"}
                return 200,{"accepted":True,"id":rid}
            # Global emergency ceiling; reverse proxy must enforce per-client limits before requests reach this process.
            cutoff=(now-dt.timedelta(minutes=1)).isoformat()
            count=c.execute("SELECT count(*) FROM leads WHERE created>=?",(cutoff,)).fetchone()[0]
            if count>=30:
                return 429,{"error":"busy"}
            c.execute("INSERT INTO leads VALUES (?,?,?,?,?,?,?)",(rid,now.isoformat(),kind,json.dumps(fields,ensure_ascii=False),json.dumps(attribution),self.version,digest))
        return 201,{"accepted":True,"id":rid}
    def __call__(self, env,start_response):
        status=200
        out={}
        method=env.get("REQUEST_METHOD")
        path=env.get("PATH_INFO")
        try:
            if path=="/api/health" and method=="GET":
                out={"ready":self.enabled}
            elif path!="/api/leads":
                status,out=404,{"error":"not_found"}
            elif method!="POST":
                status,out=405,{"error":"method"}
            elif not self.enabled:
                status,out=503,{"error":"not_configured"}
            elif env.get("HTTP_ORIGIN")!=self.origin:
                status,out=403,{"error":"origin"}
            elif env.get("CONTENT_TYPE","").split(";")[0].strip().lower()!="application/json":
                status,out=415,{"error":"content_type"}
            else:
                try:
                    length=int(env.get("CONTENT_LENGTH",""))
                except ValueError:
                    length=-1
                if not 0<length<=MAX_BODY:
                    status,out=413,{"error":"body_size"}
                else:
                    raw=env["wsgi.input"].read(length)
                    if len(raw)!=length:
                        raise ValueError("body_size")
                    obj=json.loads(raw.decode("utf-8"))
                    status,out=self.store(obj)
        except (ValueError, UnicodeError, RecursionError):
            status,out=400,{"error":"invalid_input"}
        except sqlite3.Error:
            status,out=503,{"error":"storage_unavailable"}
        payload=json.dumps(out,ensure_ascii=False).encode("utf-8")
        labels={200:"OK",201:"Created",400:"Bad Request",403:"Forbidden",404:"Not Found",405:"Method Not Allowed",409:"Conflict",413:"Payload Too Large",415:"Unsupported Media Type",429:"Too Many Requests",503:"Service Unavailable"}
        start_response(f"{status} {labels[status]}",[("Content-Type","application/json; charset=utf-8"),("Content-Length",str(len(payload))),("Cache-Control","no-store"),("X-Content-Type-Options","nosniff")])
        return [payload]

class QuietHandler(WSGIRequestHandler):
    def log_message(self,*args):
        pass

if __name__=="__main__":
    os.umask(0o077)
    db=os.environ.get("LK_DB","")
    if not db or not pathlib.Path(db).is_absolute():
        raise SystemExit("Set LK_DB to an absolute private path outside web root/repository")
    app=Intake(db,os.environ.get("LK_ORIGIN",""),os.environ.get("LK_CONSENT_VERSION",""),os.environ.get("LK_ENABLE_INTAKE")=="approved")
    with make_server("127.0.0.1",8088,app,handler_class=QuietHandler) as httpd:
        print("Intake listening on loopback; ready:",app.enabled)
        httpd.serve_forever()
