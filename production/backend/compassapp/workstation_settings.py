"""Explicit local financial-only configuration. Never use on a public host."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from .settings import *

if PRODUCTION or LIVE_INTAKE or not SSH_OPERATOR or not TESTING or dsn:
    raise ImproperlyConfigured("Local workstation configuration only")
if set(ALLOWED_HOSTS) != {"127.0.0.1","localhost"}:
    raise ImproperlyConfigured("Loopback hosts only")
location = Path(os.environ.get("COMPASS_WORKSTATION_DB",""))
if not location.is_absolute() or location.suffix != ".sqlite3":
    raise ImproperlyConfigured("Explicit local database path required")
DATABASES = {"default":{"ENGINE":"django.db.backends.sqlite3","NAME":location}}
STATIC_ROOT = location.parent / "collected_static"
LIVE_INTAKE = False
DATA_ENCRYPTION_KEYS = []
