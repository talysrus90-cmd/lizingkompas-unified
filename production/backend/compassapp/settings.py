"""Fail-closed production settings for leasingcompass.ru.

No production secrets, customer records or operator keys are checked into Git.
Fail to start instead of silently falling back to SQLite.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, unquote

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = ("test" in sys.argv or os.getenv("COMPASS_TEST_MODE") == "1")
PRODUCTION = os.getenv("COMPASS_PRODUCTION") == "1"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 50 and not TESTING:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a long random secret")
if not SECRET_KEY:
    SECRET_KEY = "test-only-do-not-use-for-production-" + "a" * 60

DEBUG = False
hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [x.strip() for x in hosts.split(",") if x.strip()]
if TESTING and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["testserver", "127.0.0.1", "localhost"]
if PRODUCTION and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Explicit production ALLOWED_HOSTS required")
CSRF_TRUSTED_ORIGINS = [
    x.strip() for x in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "intake",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "compassapp.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "compassapp.wsgi.application"

dsn = os.getenv("DATABASE_URL", "")
if dsn:
    p = urlsplit(dsn)
    if p.scheme not in ("postgres", "postgresql") or not p.hostname or not p.path.strip("/"):
        raise ImproperlyConfigured("DATABASE_URL must point to PostgreSQL")
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(p.path.lstrip("/")),
        "USER": unquote(p.username or ""),
        "PASSWORD": unquote(p.password or ""),
        "HOST": p.hostname,
        "PORT": p.port or 5432,
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }}
elif TESTING:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
else:
    raise ImproperlyConfigured("PostgreSQL DATABASE_URL required; SQLite is test-only")

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "collected_static"
STORAGES = {
    "staticfiles": {"BACKEND": (
        "django.contrib.staticfiles.storage.StaticFilesStorage" if TESTING
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}
# Document uploads are NOT enabled. Any future private document storage must
# be placed outside this static folder and behind authorization and AV checks.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SAMESITE = "Strict"
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if PRODUCTION else None
SECURE_HSTS_SECONDS = int(os.getenv("COMPASS_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 14}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
DATA_ENCRYPTION_KEYS = [
    item.strip() for item in os.getenv("COMPASS_FERNET_KEYS", "").split(",") if item.strip()
]
LIVE_INTAKE = os.getenv("COMPASS_LIVE_INTAKE") == "yes"
CONSENT_VERSION = os.getenv("COMPASS_CONSENT_VERSION", "")
OPERATOR_NAME = os.getenv("COMPASS_OPERATOR_NAME", "")
OPERATOR_INN = os.getenv("COMPASS_OPERATOR_INN", "")
THROTTLE_SECRET = os.getenv("COMPASS_THROTTLE_SECRET", "")
if LIVE_INTAKE:
    required = {
        "production_flag": PRODUCTION,
        "postgresql": bool(dsn),
        "explicit_hosts": bool(ALLOWED_HOSTS) and "*" not in ALLOWED_HOSTS,
        "approved_policy": os.getenv("COMPASS_POLICY_APPROVED") == "yes",
        "confirmed_rkn_scope": os.getenv("COMPASS_RKN_SCOPE_CONFIRMED") == "yes",
        "verified_backup_restore": os.getenv("COMPASS_RESTORE_TEST_PASSED") == "yes",
        "operator": bool(OPERATOR_NAME and OPERATOR_INN),
        "consent_version": bool(CONSENT_VERSION),
        "encryption": bool(DATA_ENCRYPTION_KEYS),
        "throttle_secret": len(THROTTLE_SECRET) >= 32,
        "strong_secret": len(SECRET_KEY) >= 50,
    }
    missing = [name for name, is_ok in required.items() if not is_ok]
    if missing:
        raise ImproperlyConfigured("Intake launch gates not met: " + ", ".join(missing))

LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.request": {
        "handlers": ["console"], "level": "ERROR", "propagate": False,
    }},
}
