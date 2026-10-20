"""
SmartGuard AI — Account Repository
Data-access layer for security_accounts and audit_logs.
"""
import logging
import uuid
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.account import AuditLog, SecurityAccount

logger = logging.getLogger("smartguard.repository")


class AccountRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get_by_id(self, account_id: uuid.UUID) -> Optional[SecurityAccount]:
        return self.db.get(SecurityAccount, account_id)

    def get_by_username(self, username: str) -> Optional[SecurityAccount]:
        stmt = select(SecurityAccount).where(
            func.lower(SecurityAccount.username) == username.lower()
        )
        return self.db.scalars(stmt).first()

    def list_accounts(
        self,
        search: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[SecurityAccount], int]:
        stmt = select(SecurityAccount)

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    SecurityAccount.username.ilike(pattern),
                    SecurityAccount.full_name.ilike(pattern),
                )
            )
        if role:
            stmt = stmt.where(SecurityAccount.role == role.upper())
        if status:
            stmt = stmt.where(SecurityAccount.status == status.lower())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total: int = self.db.scalar(count_stmt) or 0

        stmt = stmt.order_by(SecurityAccount.created_at.desc()).offset(skip).limit(limit)
        accounts = list(self.db.scalars(stmt).all())
        return accounts, total

    def count_admins(self) -> int:
        stmt = select(func.count()).where(SecurityAccount.role == "ADMIN")
        return self.db.scalar(stmt) or 0

    def exists_any_admin(self) -> bool:
        return self.count_admins() > 0

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def create(self, account: SecurityAccount) -> SecurityAccount:
        self.db.add(account)
        self.db.flush()  # flush to get generated PK while still in transaction
        self.db.refresh(account)
        return account

    def save(self, account: SecurityAccount) -> SecurityAccount:
        self.db.flush()
        self.db.refresh(account)
        return account

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def log_action(
        self,
        action: str,
        actor_id: Optional[uuid.UUID] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        meta: Optional[dict] = None,
        request_id: Optional[str] = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            meta=meta,
            request_id=request_id,
        )
        self.db.add(entry)
        self.db.flush()
        return entry
