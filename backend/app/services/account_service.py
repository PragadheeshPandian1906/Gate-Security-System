"""
SmartGuard AI — Account and Authentication Service Layer
Business logic between API routes and the data-access layer.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models.account import SecurityAccount
from app.repositories.account_repository import AccountRepository
from app.schemas.account import AccountCreate, AccountListResponse, AccountPublic

logger = logging.getLogger("smartguard.service")


class AuthenticationError(Exception):
    """Raised on invalid credentials or inactive account."""


class AccountService:
    def __init__(self, db: Session) -> None:
        self._repo = AccountRepository(db)
        self._db = db

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def authenticate(self, username: str, password: str) -> SecurityAccount:
        """
        Verify credentials and return the account.
        Raises AuthenticationError for any failure — never reveals which field
        was wrong to prevent username enumeration.
        """
        account = self._repo.get_by_username(username)
        if account is None or not verify_password(password, account.password_hash):
            logger.warning("smartguard.auth Login failed username=%r", username)
            raise AuthenticationError("Invalid credentials")

        if account.status != "active":
            logger.warning(
                "smartguard.auth Login rejected — inactive account account_id=%s", account.id
            )
            raise AuthenticationError("Account is inactive")

        # Opportunistically upgrade hash if parameters changed
        if needs_rehash(account.password_hash):
            account.password_hash = hash_password(password)
            self._db.flush()
            logger.info("Password hash upgraded for account_id=%s", account.id)

        logger.info("smartguard.auth Login succeeded account_id=%s", account.id)
        return account

    def build_token(self, account: SecurityAccount) -> tuple[str, int]:
        """Return (access_token, expires_in_seconds)."""
        settings = get_settings()
        token = create_access_token(
            subject=str(account.id),
            extra_claims={"role": account.role, "username": account.username},
        )
        return token, settings.access_token_expire_minutes * 60

    # ------------------------------------------------------------------
    # Account management (admin operations)
    # ------------------------------------------------------------------
    def create_account(
        self,
        data: AccountCreate,
        actor_id: Optional[uuid.UUID] = None,
    ) -> SecurityAccount:
        existing = self._repo.get_by_username(data.username)
        if existing:
            raise ValueError(f"Username '{data.username}' is already taken.")

        account = SecurityAccount(
            username=data.username,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            role=data.role,
            status="active",
            must_change_password=True,  # temporary password must be changed
            created_by=actor_id,
        )
        account = self._repo.create(account)
        self._repo.log_action(
            action="account.create",
            actor_id=actor_id,
            target_type="security_account",
            target_id=str(account.id),
            meta={"username": account.username, "role": account.role},
        )
        self._db.commit()
        logger.info(
            "smartguard.admin Account created account_id=%s username=%r role=%s by actor=%s",
            account.id, account.username, account.role, actor_id,
        )
        return account

    def list_accounts(
        self,
        search: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> AccountListResponse:
        accounts, total = self._repo.list_accounts(
            search=search, role=role, status=status, skip=skip, limit=limit
        )
        return AccountListResponse(
            accounts=[AccountPublic.model_validate(a) for a in accounts],
            total=total,
        )

    def update_status(
        self,
        account_id: uuid.UUID,
        new_status: str,
        actor_id: uuid.UUID,
    ) -> SecurityAccount:
        account = self._repo.get_by_id(account_id)
        if account is None:
            raise LookupError(f"Account {account_id} not found.")

        # Prevent self-lockout
        if str(account_id) == str(actor_id) and new_status == "inactive":
            raise ValueError("Administrators cannot deactivate their own account.")

        old_status = account.status
        account.status = new_status
        account.updated_at = datetime.now(timezone.utc)
        self._repo.log_action(
            action=f"account.status.{new_status}",
            actor_id=actor_id,
            target_type="security_account",
            target_id=str(account_id),
            meta={"from": old_status, "to": new_status},
        )
        self._db.commit()
        logger.info(
            "smartguard.admin Account status changed account_id=%s %s→%s by actor=%s",
            account_id, old_status, new_status, actor_id,
        )
        return account

    def reset_password(
        self,
        account_id: uuid.UUID,
        new_password: str,
        must_change_password: bool,
        actor_id: uuid.UUID,
    ) -> SecurityAccount:
        account = self._repo.get_by_id(account_id)
        if account is None:
            raise LookupError(f"Account {account_id} not found.")

        account.password_hash = hash_password(new_password)
        account.must_change_password = must_change_password
        account.updated_at = datetime.now(timezone.utc)
        self._repo.log_action(
            action="account.password.reset",
            actor_id=actor_id,
            target_type="security_account",
            target_id=str(account_id),
            meta={"must_change_password": must_change_password},
        )
        self._db.commit()
        logger.info(
            "smartguard.admin Password reset account_id=%s must_change=%s by actor=%s",
            account_id, must_change_password, actor_id,
        )
        return account

    # ------------------------------------------------------------------
    # Bootstrap — used by CLI only
    # ------------------------------------------------------------------
    def bootstrap_admin(
        self, username: str, password: str, full_name: str
    ) -> SecurityAccount:
        """
        Create the initial administrator account.
        Raises ValueError if any admin already exists.
        """
        if self._repo.exists_any_admin():
            raise ValueError(
                "An administrator account already exists. "
                "Use the account-management interface to create additional accounts."
            )
        if self._repo.get_by_username(username):
            raise ValueError(f"Username '{username}' is already taken.")

        account = SecurityAccount(
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            role="ADMIN",
            status="active",
            must_change_password=False,
        )
        account = self._repo.create(account)
        self._repo.log_action(
            action="account.bootstrap",
            actor_id=None,
            target_type="security_account",
            target_id=str(account.id),
            meta={"username": account.username},
        )
        self._db.commit()
        logger.info(
            "smartguard.admin Bootstrap administrator created account_id=%s", account.id
        )
        return account
