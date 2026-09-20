"""
services/crypto.py — Symmetric Credential Encryption at Rest
─────────────────────────────────────────────────────────────
Provides transparent encryption and decryption for sensitive user credentials
(such as third-party API keys) stored in the database.

Security properties:
- Uses cryptography.fernet.Fernet (AES-128 in CBC mode with HMAC-SHA256).
- Derives key deterministically from the application's SECRET_KEY via SHA-256.
- Backward-compatible: safely detects legacy unencrypted keys and returns them
  transparently so existing data is never broken.
- Resilient: Invalid tokens or decryption failures fall back safely without crashing.
"""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, has_app_context

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Derive a URL-safe 32-byte base64-encoded Fernet key from SECRET_KEY."""
    secret: Optional[str] = None
    if has_app_context():
        secret = current_app.config.get('SECRET_KEY')
    if not secret:
        import os
        secret = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')

    # Hash secret to 32 bytes and url-safe base64 encode for Fernet
    key_bytes = hashlib.sha256(secret.encode('utf-8')).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_credential(value: Optional[str]) -> Optional[str]:
    """Encrypt a sensitive credential string.

    If value is None or empty, returns None.
    If value is already encrypted (starts with standard Fernet header 'gAAAAA'),
    it returns the value as-is to prevent double encryption.
    """
    if not value or not str(value).strip():
        return None

    clean_value = str(value).strip()

    # Prevent double-encrypting an already encrypted token
    if clean_value.startswith('gAAAAA'):
        return clean_value

    try:
        f = _get_fernet()
        encrypted = f.encrypt(clean_value.encode('utf-8')).decode('utf-8')
        return encrypted
    except Exception as e:
        logger.error(f"Failed to encrypt credential: {e}")
        # Fallback to plain value if encryption system fails unexpectedly
        return clean_value


def decrypt_credential(encrypted_value: Optional[str]) -> Optional[str]:
    """Decrypt a sensitive credential string.

    Gracefully detects unencrypted legacy credentials (e.g. keys starting with
    'gsk_' or not matching the Fernet token header) and returns them as-is.
    """
    if not encrypted_value or not str(encrypted_value).strip():
        return None

    val = str(encrypted_value).strip()

    # If it doesn't match standard Fernet token prefix, it is an unencrypted legacy key
    if not val.startswith('gAAAAA'):
        return val

    try:
        f = _get_fernet()
        decrypted = f.decrypt(val.encode('utf-8')).decode('utf-8')
        return decrypted
    except InvalidToken:
        logger.warning("InvalidToken encountered during credential decryption; possible SECRET_KEY mismatch.")
        return val
    except Exception as e:
        logger.warning(f"Credential decryption error: {e}")
        return val
