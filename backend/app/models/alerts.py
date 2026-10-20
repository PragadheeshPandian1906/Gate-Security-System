"""
SmartGuard AI — Phase 4 SQLAlchemy Models

Tables defined here:
  - security_alerts    : persistent alert records with lifecycle, dedup key, and assignment
  - alert_notes        : investigation note history per alert
  - security_contacts  : configurable email recipients with notification preferences
  - notification_log   : email delivery tracking with retry and idempotency
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ---------------------------------------------------------------------------
# Shared constant sets
# ---------------------------------------------------------------------------
ALERT_SEVERITY_VALUES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
ALERT_STATUS_VALUES = ("OPEN", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "DISMISSED")
ALERT_CATEGORY_VALUES = (
    "DENIED_ACCESS", "WATCHLIST_HIT", "REPEATED_DENIAL",
    "MANUAL_REVIEW", "SYSTEM_FAULT", "GENERAL",
    "VISITOR_APPROVAL", "VISITOR_VIOLATION",
)
NOTIFICATION_TYPE_VALUES = ("ALERT", "DAILY_SUMMARY", "TEST")
NOTIFICATION_STATUS_VALUES = ("PENDING", "SENDING", "SENT", "FAILED", "RETRY_SCHEDULED")
NOTE_TYPE_VALUES = ("NOTE", "STATUS_CHANGE", "ASSIGNMENT", "SYSTEM")


# ---------------------------------------------------------------------------
# security_alerts
# ---------------------------------------------------------------------------
class SecurityAlert(Base):
    """
    A persistent security alert created by the alert engine.
    Lifecycle: OPEN → ACKNOWLEDGED → INVESTIGATING → RESOLVED | DISMISSED
    """
    __tablename__ = "security_alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_security_alerts_severity",
        ),
        CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','INVESTIGATING','RESOLVED','DISMISSED')",
            name="ck_security_alerts_status",
        ),
        CheckConstraint(
            "category IN ('DENIED_ACCESS','WATCHLIST_HIT','REPEATED_DENIAL','MANUAL_REVIEW','SYSTEM_FAULT','GENERAL','VISITOR_APPROVAL','VISITOR_VIOLATION')",
            name="ck_security_alerts_category",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Classification
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")

    # Related entities
    access_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_attempts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
    )
    detected_plate: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    watchlist_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("watchlist_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    visitor_pass_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("visitor_passes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Timestamps
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Occurrence tracking
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    related_attempt_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Assignment
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Resolution
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Deduplication key (unique per logical alert group)
    dedup_key: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)

    # Relationships
    notes: Mapped[list["AlertNote"]] = relationship(
        "AlertNote",
        back_populates="alert",
        order_by="AlertNote.created_at",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["NotificationLog"]] = relationship(
        "NotificationLog",
        back_populates="alert",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SecurityAlert id={self.id} category={self.category!r} "
            f"severity={self.severity} status={self.status}>"
        )


# ---------------------------------------------------------------------------
# alert_notes
# ---------------------------------------------------------------------------
class AlertNote(Base):
    """Investigation note or lifecycle transition record for a security alert."""
    __tablename__ = "alert_notes"
    __table_args__ = (
        CheckConstraint(
            "note_type IN ('NOTE','STATUS_CHANGE','ASSIGNMENT','SYSTEM')",
            name="ck_alert_notes_note_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_alerts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    note_type: Mapped[str] = mapped_column(String(32), nullable=False, default="NOTE")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    alert: Mapped["SecurityAlert"] = relationship("SecurityAlert", back_populates="notes")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AlertNote id={self.id} alert_id={self.alert_id} type={self.note_type!r}>"


# ---------------------------------------------------------------------------
# security_contacts
# ---------------------------------------------------------------------------
class SecurityContact(Base):
    """
    Configurable external security contact for email notifications.
    Can be restricted to specific alert categories and minimum severity.
    """
    __tablename__ = "security_contacts"
    __table_args__ = (
        UniqueConstraint("email", name="uq_security_contacts_email"),
        CheckConstraint(
            "min_severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_security_contacts_min_severity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # Notification preferences
    notify_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    min_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="HIGH")
    daily_summary_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

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
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Last notification status cache
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_notification_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Relationships
    notifications: Mapped[list["NotificationLog"]] = relationship(
        "NotificationLog",
        back_populates="contact",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SecurityContact id={self.id} email={self.email!r} "
            f"active={self.is_active}>"
        )


# ---------------------------------------------------------------------------
# notification_log
# ---------------------------------------------------------------------------
class NotificationLog(Base):
    """
    Persistent delivery tracking for every email notification attempt.
    Never stores secrets, credentials, or API keys.
    """
    __tablename__ = "notification_log"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','SENDING','SENT','FAILED','RETRY_SCHEDULED')",
            name="ck_notification_log_status",
        ),
        CheckConstraint(
            "notification_type IN ('ALERT','DAILY_SUMMARY','TEST')",
            name="ck_notification_log_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    notification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recipient_email: Mapped[str] = mapped_column(String(256), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)

    # Delivery state
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Provider details (no credentials)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Idempotency key — prevents duplicate sends for the same logical notification
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)

    # Daily summary metadata
    summary_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 'YYYY-MM-DD'

    # Relationships
    alert: Mapped["SecurityAlert | None"] = relationship(
        "SecurityAlert", back_populates="notifications"
    )
    contact: Mapped["SecurityContact | None"] = relationship(
        "SecurityContact", back_populates="notifications"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<NotificationLog id={self.id} type={self.notification_type!r} "
            f"to={self.recipient_email!r} status={self.status}>"
        )
