"""
SmartGuard AI — Phase 3 SQLAlchemy Models

Tables defined here:
  - access_schedules   : per-weekday open/close times with timezone config
  - watchlist_entries  : vehicle watchlist with reason, severity, expiry
  - access_attempts    : full audit record of every access decision
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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
# access_schedules
# ---------------------------------------------------------------------------
WEEKDAY_VALUES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class AccessSchedule(Base):
    """
    Configurable per-weekday access schedule.
    One row per weekday. Default: Mon–Sat 08:00–17:00, Sun closed.
    Times stored as HH:MM strings (24-hour). Evaluated in campus_timezone.
    """
    __tablename__ = "access_schedules"
    __table_args__ = (
        UniqueConstraint("weekday", name="uq_access_schedules_weekday"),
        CheckConstraint(
            "weekday IN ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')",
            name="ck_access_schedules_weekday",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    weekday: Mapped[str] = mapped_column(String(16), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # HH:MM 24-hour format, nullable if is_open=False
    open_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    close_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # Campus timezone (IANA tz name e.g. "Asia/Kolkata")
    campus_timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AccessSchedule weekday={self.weekday!r} "
            f"open={self.is_open} {self.open_time}-{self.close_time}>"
        )


# ---------------------------------------------------------------------------
# watchlist_entries
# ---------------------------------------------------------------------------
WATCHLIST_SEVERITY_VALUES = ("low", "medium", "high")


class WatchlistEntry(Base):
    """
    Vehicle watchlist.  Can reference a registered vehicle OR a raw plate.
    High-severity active entries → DENY.  Others → MANUAL_REVIEW by default.
    """
    __tablename__ = "watchlist_entries"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low','medium','high')",
            name="ck_watchlist_severity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Optional FK to registered vehicle
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Raw plate text as supplied; normalized_plate computed on write
    plate_raw: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="medium")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    vehicle: Mapped["Vehicle | None"] = relationship("Vehicle", foreign_keys=[vehicle_id])  # type: ignore[name-defined]

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<WatchlistEntry id={self.id} plate={self.plate_normalized!r} "
            f"severity={self.severity} active={self.is_active}>"
        )


# ---------------------------------------------------------------------------
# access_attempts  (full decision audit record)
# ---------------------------------------------------------------------------
ACCESS_DECISION_VALUES = ("ALLOW", "DENY", "MANUAL_REVIEW")
ACCESS_DIRECTION_VALUES = ("ENTRY", "EXIT")
GATE_RESULT_VALUES = ("OPEN", "CLOSED", "MANUAL_REVIEW")
REVIEW_RESOLUTION_VALUES = ("approved", "denied")


class AccessAttempt(Base):
    """
    Immutable audit record of every access-decision attempt.
    Created by the access-decision engine.  Optionally resolved by a security officer.
    """
    __tablename__ = "access_attempts"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('ALLOW','DENY','MANUAL_REVIEW')",
            name="ck_access_attempts_decision",
        ),
        CheckConstraint(
            "direction IN ('ENTRY','EXIT')",
            name="ck_access_attempts_direction",
        ),
        CheckConstraint(
            "gate_result IN ('OPEN','CLOSED','MANUAL_REVIEW')",
            name="ck_access_attempts_gate_result",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # When the attempt occurred
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(8), nullable=False, index=True)

    # ── Face verification context ───────────────────────────────────────────
    face_verification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("face_verifications.id", ondelete="SET NULL"),
        nullable=True,
    )
    face_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    face_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    person_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # ── Plate / vehicle context ─────────────────────────────────────────────
    alpr_verification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alpr_verifications.id", ondelete="SET NULL"),
        nullable=True,
    )
    detected_plate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detected_plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    matched_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehicle_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    vehicle_owner_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Optional FK to visitor_passes
    visitor_pass_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("visitor_passes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Policy evaluation results ───────────────────────────────────────────
    ownership_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    schedule_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    watchlist_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    watchlist_severity: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # ── Final decision ──────────────────────────────────────────────────────
    decision: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # JSON list of reason codes e.g. ["OWNER_MISMATCH", "OUTSIDE_SCHEDULE"]
    reason_codes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_result: Mapped[str] = mapped_column(String(16), nullable=False, default="CLOSED")

    # Processing time in milliseconds
    processing_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Audit attribution ───────────────────────────────────────────────────
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Manual review fields ────────────────────────────────────────────────
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 'approved'|'denied'
    review_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AccessAttempt id={self.id} direction={self.direction} "
            f"decision={self.decision} gate={self.gate_result}>"
        )
