"""
SmartGuard AI — Security Utilities
Password hashing with Argon2id and JWT operations.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from jose import JWTError, jwt

from app.core.config import get_settings

logger = logging.getLogger("smartguard.security")

# Argon2id hasher with strong parameters suitable for a security application.
# memory_cost=65536 (64 MB), time_cost=3, parallelism=4
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    """Return a secure Argon2id hash of *plaintext*."""
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Return True if *plaintext* matches *hashed*.
    Never raises — all errors are mapped to False and logged at DEBUG.
    """
    try:
        return _ph.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError) as exc:
        logger.debug("Password verification error (non-sensitive): %s", type(exc).__name__)
        return False


def needs_rehash(hashed: str) -> bool:
    """Return True if the stored hash should be upgraded to current parameters."""
    return _ph.check_needs_rehash(hashed)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """
    Create a signed JWT.

    Args:
        subject: Unique account identifier (account ID as string).
        extra_claims: Additional non-sensitive claims (e.g., role).

    Never include passwords, hashes, or secrets in claims.
    """
    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT. Raises JWTError on any failure.
    The caller is responsible for handling JWTError appropriately.
    """
    settings = get_settings()
    # jose raises JWTError for expired, tampered, or malformed tokens
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
