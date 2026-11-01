"""Authentication/authorization policy; secrets: credential hashing and role rules."""

import hashlib
import hmac
import secrets
from .config import PERMISSIONS


def credential(password):
    """Create a salted password record for local demonstration accounts."""

    salt = secrets.token_hex(16)
    return {
        "salt": salt,
        "digest": hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), 200000
        ).hex(),
    }


def verify(password, record):
    """Compare a password with a stored record using a constant-time check."""

    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(record["salt"]), 200000
    ).hex()
    return hmac.compare_digest(digest, record["digest"])


def allowed(role, operation):
    """Return whether a role is allowed to perform an operation."""

    return operation in PERMISSIONS.get(role, set())
