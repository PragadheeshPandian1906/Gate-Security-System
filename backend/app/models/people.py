"""
SmartGuard AI — Phase 2 SQLAlchemy Models

Tables defined here:
  - campus_people      : registered people on campus (staff, students, visitors)
  - vehicles           : registered vehicles with license plates
  - face_profiles      : face embeddings (512-dim pgvector) linked to campus_people
  - face_verifications : log of InsightFace recognition attempts
  - alpr_verifications : log of FastALPR license-plate recognition attempts
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

try:
    from pgvector.sqlalchemy import Vector
    _VECTOR_AVAILABLE = True
except ImportError:
    _VECTOR_AVAILABLE = False
    Vector = None  # graceful degradation


# ---------------------------------------------------------------------------
# campus_people
# ---------------------------------------------------------------------------
PERSON_TYPE_VALUES = ("staff", "student", "visitor", "contractor")
PERSON_STATUS_VALUES = ("active", "inactive", "suspended")


class CampusPerson(Base):
    """
    A person registered in the campus security system.
    May be staff, student, visitor, or contractor.
    """
    __tablename__ = "campus_people"
    __table_args__ = (
        CheckConstraint(
            "person_type IN ('staff', 'student', 'visitor', 'contractor')",
            name="ck_campus_people_person_type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'suspended')",
            name="ck_campus_people_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    person_type: Mapped[str] = mapped_column(String(16), nullable=False, default="staff")
    employee_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Local storage path for primary photo
    photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Supabase Storage path (face-images bucket)
    photo_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    registered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    face_profiles: Mapped[list["FaceProfile"]] = relationship(
        "FaceProfile", back_populates="person", cascade="all, delete-orphan"
    )
    face_verifications: Mapped[list["FaceVerification"]] = relationship(
        "FaceVerification", back_populates="matched_person"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CampusPerson id={self.id} name={self.full_name!r} type={self.person_type}>"


# ---------------------------------------------------------------------------
# vehicles
# ---------------------------------------------------------------------------
VEHICLE_STATUS_VALUES = ("active", "inactive", "flagged")


class Vehicle(Base):
    """
    A registered vehicle in the campus security system.
    """
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'flagged')",
            name="ck_vehicles_status",
        ),
        UniqueConstraint("plate_number", name="uq_vehicles_plate_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plate_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Normalised plate (uppercase, no spaces/hyphens) for fuzzy matching
    plate_normalized: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    make: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vehicle_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional FK to campus_people
    owner_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="SET NULL"),
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
    registered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    alpr_verifications: Mapped[list["AlprVerification"]] = relationship(
        "AlprVerification", back_populates="matched_vehicle"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Vehicle id={self.id} plate={self.plate_number!r} status={self.status}>"


# ---------------------------------------------------------------------------
# face_profiles
# ---------------------------------------------------------------------------
class FaceProfile(Base):
    """
    Stores a 512-dimensional face embedding (InsightFace ArcFace) for a
    campus person, alongside the source image path.
    """
    __tablename__ = "face_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 512-dim ArcFace embedding stored as pgvector
    # Column is added dynamically if pgvector is available
    embedding_model: Mapped[str] = mapped_column(
        String(64), nullable=False, default="buffalo_l"
    )
    # Local path to enrolled face image
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Supabase Storage path
    image_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    enrolled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    person: Mapped["CampusPerson"] = relationship(
        "CampusPerson", back_populates="face_profiles"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FaceProfile id={self.id} person_id={self.person_id}>"


# ---------------------------------------------------------------------------
# face_verifications  (recognition log)
# ---------------------------------------------------------------------------
FACE_RESULT_VALUES = ("matched", "no_match", "low_confidence", "error", "no_face")


class FaceVerification(Base):
    """
    Immutable log entry for every InsightFace recognition attempt.
    """
    __tablename__ = "face_verifications"
    __table_args__ = (
        CheckConstraint(
            "result IN ('matched', 'no_match', 'low_confidence', 'error', 'no_face')",
            name="ck_face_verifications_result",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campus_people.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Path to the query image used for this verification
    query_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    query_image_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Number of faces detected in the query image
    faces_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Extra metadata (bounding boxes, landmarks, etc.)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    matched_person: Mapped["CampusPerson | None"] = relationship(
        "CampusPerson", back_populates="face_verifications"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FaceVerification id={self.id} result={self.result!r}>"


# ---------------------------------------------------------------------------
# alpr_verifications  (license-plate recognition log)
# ---------------------------------------------------------------------------
ALPR_RESULT_VALUES = ("matched", "no_match", "no_plate", "error")


class AlprVerification(Base):
    """
    Immutable log entry for every FastALPR license plate recognition attempt.
    """
    __tablename__ = "alpr_verifications"
    __table_args__ = (
        CheckConstraint(
            "result IN ('matched', 'no_match', 'no_plate', 'error')",
            name="ck_alpr_verifications_result",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    detected_plate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detected_plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    detection_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    matched_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Path to query image
    query_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    query_image_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Raw detections from FastALPR (list of all candidates)
    raw_detections: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    matched_vehicle: Mapped["Vehicle | None"] = relationship(
        "Vehicle", back_populates="alpr_verifications"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AlprVerification id={self.id} result={self.result!r} plate={self.detected_plate!r}>"
