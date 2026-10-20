"""
SmartGuard AI — Admin Account Management Routes
All endpoints require ADMIN role — enforced via require_admin dependency.
"""
import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.schemas.account import (
    AccountCreate,
    AccountListResponse,
    AccountPublic,
    AccountStatusUpdate,
    PasswordResetRequest,
)
from app.services.account_service import AccountService

router = APIRouter(prefix="/admin", tags=["Account Management"])
logger = logging.getLogger("smartguard.admin")


@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(
    search: Optional[str] = Query(None, description="Search username or full name"),
    role: Optional[str] = Query(None, description="Filter by role: ADMIN or SECURITY"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: active or inactive"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: SecurityAccount = Depends(require_admin),
) -> AccountListResponse:
    """List security accounts. Supports search, role and status filtering."""
    service = AccountService(db)
    return service.list_accounts(
        search=search, role=role, status=status_filter, skip=skip, limit=limit
    )


@router.post("/accounts", response_model=AccountPublic, status_code=status.HTTP_201_CREATED)
def create_account(
    body: AccountCreate,
    db: Session = Depends(get_db),
    admin: SecurityAccount = Depends(require_admin),
) -> AccountPublic:
    """Create a new security account. Accounts are created with must_change_password=True."""
    service = AccountService(db)
    try:
        account = service.create_account(body, actor_id=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AccountPublic.model_validate(account)


@router.patch("/accounts/{account_id}/status", response_model=AccountPublic)
def update_account_status(
    account_id: uuid.UUID,
    body: AccountStatusUpdate,
    db: Session = Depends(get_db),
    admin: SecurityAccount = Depends(require_admin),
) -> AccountPublic:
    """Activate or deactivate an account. Administrators cannot deactivate themselves."""
    service = AccountService(db)
    try:
        account = service.update_status(account_id, body.status, actor_id=admin.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AccountPublic.model_validate(account)


@router.post("/accounts/{account_id}/reset-password", response_model=AccountPublic)
def reset_password(
    account_id: uuid.UUID,
    body: PasswordResetRequest,
    db: Session = Depends(get_db),
    admin: SecurityAccount = Depends(require_admin),
) -> AccountPublic:
    """
    Reset another account's password.
    By default, marks must_change_password=True so the user sets a new password on next login.
    """
    service = AccountService(db)
    try:
        account = service.reset_password(
            account_id,
            new_password=body.new_password,
            must_change_password=body.must_change_password,
            actor_id=admin.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AccountPublic.model_validate(account)
