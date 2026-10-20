"""
SmartGuard AI — FastAPI Dependencies
Provides reusable dependency functions for authentication and authorisation.
"""
import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.repositories.account_repository import AccountRepository

logger = logging.getLogger("smartguard.auth")

import time
_bearer_scheme = HTTPBearer(auto_error=True)

# In-memory account cache: account_id -> (SecurityAccount, expires_at)
_ACCOUNT_CACHE: dict[uuid.UUID, tuple[SecurityAccount, float]] = {}


def _get_account_from_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> SecurityAccount:
    """Decode JWT and return the corresponding SecurityAccount."""
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        subject: str | None = payload.get("sub")
        if not subject:
            raise JWTError("Missing subject claim")
        account_id = uuid.UUID(subject)
    except (JWTError, ValueError):
        logger.warning("smartguard.auth Invalid or expired token presented")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check cache to avoid hitting connection pool on frequent requests
    now = time.monotonic()
    cached = _ACCOUNT_CACHE.get(account_id)
    if cached and cached[1] > now:
        return cached[0]

    repo = AccountRepository(db)
    account = repo.get_by_id(account_id)
    if account is None:
        _ACCOUNT_CACHE.pop(account_id, None)
        logger.warning("smartguard.auth Token references non-existent account account_id=%s", account_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load attributes into memory and expunge so account is safe to use detached
    _ = (account.id, account.username, account.role, account.status)
    try:
        db.expunge(account)
    except Exception:
        pass
    _ACCOUNT_CACHE[account_id] = (account, now + 10.0)

    return account


def get_current_account(
    account: Annotated[SecurityAccount, Depends(_get_account_from_token)],
) -> SecurityAccount:
    """Dependency: any valid token → authenticated account (may be inactive)."""
    return account


def get_active_account(
    account: Annotated[SecurityAccount, Depends(get_current_account)],
) -> SecurityAccount:
    """Dependency: token must belong to an active account."""
    if account.status != "active":
        logger.warning(
            "smartguard.auth Inactive account attempted access account_id=%s", account.id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    return account


def require_admin(
    account: Annotated[SecurityAccount, Depends(get_active_account)],
) -> SecurityAccount:
    """Dependency: account must be an active ADMIN."""
    if account.role != "ADMIN":
        logger.warning(
            "smartguard.auth Unauthorized admin endpoint access account_id=%s role=%s",
            account.id, account.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return account


def require_security(
    account: Annotated[SecurityAccount, Depends(get_active_account)],
) -> SecurityAccount:
    """Dependency: account must be active SECURITY or ADMIN."""
    if account.role not in {"SECURITY", "ADMIN"}:
        logger.warning(
            "smartguard.auth Unauthorized security endpoint access account_id=%s role=%s",
            account.id, account.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security role required",
        )
    return account
