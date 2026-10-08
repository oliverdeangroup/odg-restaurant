"""Encrypted model field for secrets such as mailbox passwords."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    key = hashlib.sha256(settings.FIELD_ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value):
    if not value:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return ""


class EncryptedTextField(models.TextField):
    """Stores text encrypted at rest; reads back as plain text."""

    def from_db_value(self, value, expression, connection):
        return decrypt(value) if value else value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt(value) if value else value
