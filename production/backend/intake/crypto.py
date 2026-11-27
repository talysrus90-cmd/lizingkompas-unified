"""Encrypted Django model fields (PII encrypted before PostgreSQL storage).

Fernet AES-128-CBC + HMAC provides authenticated encryption; keys must be kept
outside Git, backed up separately, and rotated via MultiFernet newest-first.
TLS and encrypted infrastructure/backup storage are ALSO required in production.
"""
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

PREFIX = "enc:v1:"

def cipher():
    keys = settings.DATA_ENCRYPTION_KEYS
    if not keys:
        raise ImproperlyConfigured("COMPASS_FERNET_KEYS required before storing personal data")
    try:
        return MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("Invalid encryption key format") from exc

class EncryptedTextField(models.TextField):
    """Opaque ciphertext in database; encrypted fields are intentionally not searchable."""

    def get_prep_value(self, value):
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        if not value:
            return ""
        return PREFIX + cipher().encrypt(value.encode("utf-8")).decode("ascii")

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        if not isinstance(value, str) or not value.startswith(PREFIX):
            raise ImproperlyConfigured("Encountered unexpected unencrypted sensitive field")
        try:
            return cipher().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise ImproperlyConfigured("Sensitive field cannot be decrypted") from exc

    def to_python(self, value):
        # Model forms provide plaintext; ORM from_db_value decrypts once.
        return value
