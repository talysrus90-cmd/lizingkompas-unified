"""Server-side intake protection and cash-flow comparability.

No raw IP addresses are recorded. The reverse proxy overwrites X-Real-IP.
A per-digest database window protects basic accidental/bot overuse, not DDoS.
"""
import hashlib
import hmac
import ipaddress
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import Lead, SubmissionAttempt, AuditEvent

CONSENT_PURPOSE = (
    "обработка предоставленных контактных данных и параметров имущества "
    "для рассмотрения заявки на подбор лизинга, подготовки ответа и связи по заявке"
)

def consent_text():
    return (f"Я даю согласие {settings.OPERATOR_NAME} (ИНН {settings.OPERATOR_INN}) "
            f"на {CONSENT_PURPOSE}. Ознакомлен(а) с политикой обработки "
            f"персональных данных и понимаю право отозвать согласие.")

def consent_sha256():
    return hashlib.sha256(consent_text().encode("utf-8")).hexdigest()

def ip_digest(request):
    forwarded = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "")
    try:
        canonical = str(ipaddress.ip_address(forwarded))
    except ValueError:
        canonical = "unknown"
    secret = settings.THROTTLE_SECRET or ("test-only-secret" if settings.TESTING else "")
    if not secret:
        raise RuntimeError("throttle key missing")
    return hmac.new(secret.encode("utf-8"), canonical.encode("ascii"), hashlib.sha256).hexdigest()

def count_attempt(request):
    """Atomic 15-minute DB window, max 5 attempts incl. invalid submissions."""
    now = timezone.now()
    start = now.replace(minute=(now.minute//15)*15, second=0, microsecond=0)
    digest = ip_digest(request)
    with transaction.atomic():
        row, _ = SubmissionAttempt.objects.select_for_update().get_or_create(
            ip_digest=digest, window_at=start, defaults={"count":0}
        )
        if row.count >= 5:
            return False
        SubmissionAttempt.objects.filter(pk=row.pk).update(count=F("count")+1)
    return True

def save_application(data,request):
    with transaction.atomic():
        existing = Lead.objects.filter(request_key=data["request_key"]).first()
        if existing:
            return existing, False
        from django.db import IntegrityError
        payload = {k:data.get(k,"") for k in (
            "client_name","phone","email","company","inn","message","asset_type",
            "asset_price","advance","term_months","vat_basis"
        )}
        lead = Lead(
            **payload,
            request_key=data["request_key"],
            consent_version=settings.CONSENT_VERSION,
            consent_text_sha256=consent_sha256(),
            source_ip_digest=ip_digest(request),
        )
        lead.full_clean()
        lead.save(force_insert=True)
        AuditEvent.objects.create(lead=lead,action="lead.received",actor="public_submission")
        return lead, True
