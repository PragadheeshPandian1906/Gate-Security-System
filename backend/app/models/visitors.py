"""
SmartGuard AI — Phase 5 Visitor Management SQLAlchemy Models

Tables defined here:
  - visitor_passes    : secure temporary passes with SHA-256 token hashes, QR metadata & lifecycle
  - visitor_approvals : mandatory security officer approval queue for visitor entry/exit
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


VISITOR_PASS_STATUS_VALUES = (
    "ISSUED",
    "PENDING_APPROVAL",
    "ACTIVE_INSIDE",
    "COMPLETED",
    "EXPIRED",
    "REVOKED",
    "DENIED",
)

VISITOR_APPROVAL_STATUS_VALUES = (
    "PENDING",
    "APPROVED",
    "DENIED",
    "CANCELLED",
)


class VisitorPass(Base):
    """
    A temporary access pass issued to a visitor.
    Stores the cryptographic SHA-256 hash of the random QR credential (never the raw token).
    Lifecycle:
      ISSUED → PENDING_APPROVAL → ACTIVE_INSIDE → COMPLETED
      (Can also transition to EXPIRED, REVOKED, or DENIED)
    """
    __tablename__ = "visitor_passes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ISSUED','PENDING_APPROVAL','ACTIVE_INSIDE','COMPLETED','EXPIRED','REVOKED','DENIED')",
            name="ck_visitor_passes_status",
        ),
        UniqueConstraint("pass_number", name="uq_visitor_passes_pass_number"),
        UniqueConstraint("token_hash", name="uq_visitor_passes_token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Human-readable pass reference e.g. VP-20261018-7F3A2C
    pass_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # The visitor (campus_people where person_type='visitor')
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional campus host (faculty/staff in campus_people)
    host_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional vehicle link & raw plate input
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehicle_plate: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Visit context & visitor personal identification details
    purpose: Mapped[str] = mapped_column(String(128), nullable=False, default="Campus Meeting")
    organization: Mapped[str | None] = mapped_column(String(128), nullable=True)
    id_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    id_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Validity window
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Security: SHA-256 hash of high-entropy token (raw token is NEVER stored)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # QR storage locations (dual-storage contract)
    qr_code_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    qr_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Current lifecycle state
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ISSUED", index=True)

    # Issuance attribution
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Check-in tracking (entry)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_in_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Check-out tracking (exit)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Revocation tracking
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    visitor = relationship("CampusPerson", foreign_keys=[visitor_id])
    host = relationship("CampusPerson", foreign_keys=[host_person_id])
    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id])
    approvals = relationship("VisitorApproval", back_populates="pass_rel", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VisitorPass id={self.id} num={self.pass_number} status={self.status}>"


class VisitorApproval(Base):
    """
    Mandatory security officer approval queue item for visitor entry.
    Created when a valid pass is scanned at the gate.
    Requires an explicit Approve or Deny decision from an authorized officer.
    """
    __tablename__ = "visitor_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','APPROVED','DENIED','CANCELLED')",
            name="ck_visitor_approvals_status",
        ),
        CheckConstraint(
            "direction IN ('ENTRY','EXIT')",
            name="ck_visitor_approvals_direction",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    pass_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("visitor_passes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Scan metadata
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    scanned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    direction: Mapped[str] = mapped_column(String(8), nullable=False, default="ENTRY")

    # State: PENDING until resolved
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)

    # Decision audit
    decision_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    denial_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Link to access attempt & alert
    access_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_attempts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    pass_rel = relationship("VisitorPass", back_populates="approvals")
    visitor = relationship("CampusPerson", foreign_keys=[visitor_id])
    access_attempt = relationship("AccessAttempt", foreign_keys=[access_attempt_id])
    alert = relationship("SecurityAlert", foreign_keys=[alert_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VisitorApproval id={self.id} pass_id={self.pass_id} status={self.status}>"
