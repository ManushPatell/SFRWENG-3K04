"""Authentication/authorization policy; secrets: credential hashing and role rules."""
import hashlib
import hmac
import secrets
from .config import PERMISSIONS

def credential(password):
    salt = secrets.token_hex(16)
    return {'salt': salt, 'digest': hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 200000).hex()}

def verify(password, record):
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(record['salt']), 200000).hex()
    return hmac.compare_digest(digest, record['digest'])

def allowed(role, operation):
    return operation in PERMISSIONS.get(role, set())
