"""
SmartGuard AI — SQLAlchemy Models (Phase 1)

Tables defined here:
  - security_accounts : application user accounts (ADMIN / SECURITY roles)
  - audit_logs        : immutable record of administrative operations
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    String,
    Text,
    func,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ---------------------------------------------------------------------------
# Enums stored as Postgres CHECK constraints (avoids ALTER TYPE pain)
# ---------------------------------------------------------------------------
ROLE_VALUES = ("ADMIN", "SECURITY")
STATUS_VALUES = ("active", "inactive")


class SecurityAccount(Base):
    """
    Application user account.
    Roles:
      ADMIN    — full access, account management.
      SECURITY — gate/monitoring operations only.
    """
    __tablename__ = "security_accounts"
    __table_args__ = (
        UniqueConstraint("username", name="uq_security_accounts_username"),
        CheckConstraint("role IN ('ADMIN', 'SECURITY')", name="ck_security_accounts_role"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_security_accounts_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="SECURITY")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Audit log entries authored by this account
    audit_entries: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SecurityAccount id={self.id} username={self.username!r} role={self.role}>"


class AuditLog(Base):
    """
    Immutable record of administrative operations.
    Never store passwords, JWTs, or secrets in metadata.
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Safe metadata only — no credentials
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    actor: Mapped["SecurityAccount | None"] = relationship(
        "SecurityAccount", back_populates="audit_entries", foreign_keys=[actor_id]
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog id={self.id} action={self.action!r}>"
