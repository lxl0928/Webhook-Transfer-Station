import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt
from cryptography.fernet import Fernet

from app.config import get_settings
from app.models import User, now


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000)
    return f"pbkdf2_sha256$600000${salt}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(base64.b64encode(actual).decode(), expected)
    except (ValueError, TypeError):
        return False


def encrypt(value: str) -> str:
    return Fernet(get_settings().encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return (
        Fernet(get_settings().encryption_key.encode()).decrypt(value.encode()).decode()
        if value
        else ""
    )


def create_token(user: User) -> str:
    settings = get_settings()
    return jwt.encode(
        {
            "sub": user.id,
            "ver": user.token_version,
            "iat": now(),
            "exp": now() + timedelta(minutes=settings.token_expire_minutes),
            "iss": "webhook-station",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "secret",
}


def redact(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if k.lower() in SENSITIVE_KEYS else redact(v) for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value
