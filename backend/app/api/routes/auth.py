"""
SmartGuard AI — Authentication Routes
POST /api/auth/login   — issue JWT
GET  /api/auth/me      — return current user
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_active_account
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.schemas.account import AccountPublic, LoginRequest, TokenResponse
from app.services.account_service import AccountService, AuthenticationError

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger("smartguard.auth")


@router.post("/login", response_model=TokenResponse, summary="Obtain access token")
def login(
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    """
    Authenticate with username and password.
    Returns a JWT access token on success.
    Invalid credentials always return 401 to prevent field enumeration.
    """
    service = AccountService(db)
    try:
        account = service.authenticate(body.username, body.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    token, expires_in = service.build_token(account)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=AccountPublic.model_validate(account),
    )


@router.get("/me", response_model=AccountPublic, summary="Current user profile")
def get_me(
    account: Annotated[SecurityAccount, Depends(get_active_account)],
) -> AccountPublic:
    """Return the authenticated user's safe profile. Never returns password_hash."""
    return AccountPublic.model_validate(account)
