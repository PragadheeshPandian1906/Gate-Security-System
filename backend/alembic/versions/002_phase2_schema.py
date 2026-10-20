"""Phase 2 schema: campus_people, vehicles, face_profiles, face_verifications, alpr_verifications

Revision ID: 002_phase2_schema
Revises: 001_initial_schema
Create Date: 2026-10-15 00:00:00.000000

Schema established in this migration:
  - campus_people      : people registered in the campus system
  - vehicles           : vehicles with license plates
  - face_profiles      : 512-dim ArcFace embeddings (pgvector) per person
  - face_verifications : InsightFace recognition attempt log
  - alpr_verifications : FastALPR license-plate recognition log

NOTE: The face_profiles.embedding column uses pgvector's VECTOR(512) type.
      pgvector must already be enabled (done in migration 001).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "002_phase2_schema"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # campus_people
    # ------------------------------------------------------------------
    op.create_table(
        "campus_people",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("person_type", sa.String(16), nullable=False, server_default="staff"),
        sa.Column("employee_id", sa.String(64), nullable=True),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("email", sa.String(256), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("photo_path", sa.String(512), nullable=True),
        sa.Column("photo_storage_path", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("registered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "person_type IN ('staff', 'student', 'visitor', 'contractor')",
            name="ck_campus_people_person_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'suspended')",
            name="ck_campus_people_status",
        ),
        sa.ForeignKeyConstraint(
            ["registered_by"],
            ["security_accounts.id"],
            name="fk_campus_people_registered_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_campus_people_employee_id", "campus_people", ["employee_id"])
    op.create_index("ix_campus_people_status", "campus_people", ["status"])
    op.create_index("ix_campus_people_person_type", "campus_people", ["person_type"])

    # ------------------------------------------------------------------
    # vehicles
    # ------------------------------------------------------------------
    op.create_table(
        "vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plate_number", sa.String(32), nullable=False),
        sa.Column("plate_normalized", sa.String(32), nullable=False),
        sa.Column("make", sa.String(64), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("color", sa.String(32), nullable=True),
        sa.Column("vehicle_type", sa.String(32), nullable=True),
        sa.Column("owner_name", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("owner_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("registered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'flagged')",
            name="ck_vehicles_status",
        ),
        sa.UniqueConstraint("plate_number", name="uq_vehicles_plate_number"),
        sa.ForeignKeyConstraint(
            ["owner_person_id"],
            ["campus_people.id"],
            name="fk_vehicles_owner_person_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["registered_by"],
            ["security_accounts.id"],
            name="fk_vehicles_registered_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_vehicles_plate_number", "vehicles", ["plate_number"])
    op.create_index("ix_vehicles_plate_normalized", "vehicles", ["plate_normalized"])
    op.create_index("ix_vehicles_owner_person_id", "vehicles", ["owner_person_id"])
    op.create_index("ix_vehicles_status", "vehicles", ["status"])

    # ------------------------------------------------------------------
    # face_profiles  (with pgvector VECTOR(512) embedding column)
    # ------------------------------------------------------------------
    op.create_table(
        "face_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding_model", sa.String(64), nullable=False, server_default="buffalo_l"),
        sa.Column("image_path", sa.String(512), nullable=True),
        sa.Column("image_storage_path", sa.String(512), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("enrolled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["campus_people.id"],
            name="fk_face_profiles_person_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["enrolled_by"],
            ["security_accounts.id"],
            name="fk_face_profiles_enrolled_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_face_profiles_person_id", "face_profiles", ["person_id"])

    # Add the pgvector VECTOR(512) embedding column using raw SQL
    # This is the most reliable approach across SQLAlchemy versions.
    op.execute("ALTER TABLE face_profiles ADD COLUMN embedding vector(512)")
    # Create an IVFFlat index for approximate nearest-neighbour searches
    # (lists=100 is appropriate for <10 000 rows; tune for larger datasets)
    op.execute(
        "CREATE INDEX ix_face_profiles_embedding "
        "ON face_profiles USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # ------------------------------------------------------------------
    # face_verifications
    # ------------------------------------------------------------------
    op.create_table(
        "face_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("distance", sa.Float(), nullable=True),
        sa.Column("matched_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_image_path", sa.String(512), nullable=True),
        sa.Column("query_image_storage_path", sa.String(512), nullable=True),
        sa.Column("faces_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "result IN ('matched', 'no_match', 'low_confidence', 'error', 'no_face')",
            name="ck_face_verifications_result",
        ),
        sa.ForeignKeyConstraint(
            ["matched_person_id"],
            ["campus_people.id"],
            name="fk_face_verifications_person",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["security_accounts.id"],
            name="fk_face_verifications_verified_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_face_verifications_result", "face_verifications", ["result"])
    op.create_index("ix_face_verifications_timestamp", "face_verifications", ["timestamp"])
    op.create_index("ix_face_verifications_matched_person_id", "face_verifications", ["matched_person_id"])

    # ------------------------------------------------------------------
    # alpr_verifications
    # ------------------------------------------------------------------
    op.create_table(
        "alpr_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("detected_plate", sa.String(32), nullable=True),
        sa.Column("detected_plate_normalized", sa.String(32), nullable=True),
        sa.Column("detection_confidence", sa.Float(), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("matched_vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_image_path", sa.String(512), nullable=True),
        sa.Column("query_image_storage_path", sa.String(512), nullable=True),
        sa.Column("raw_detections", sa.JSON(), nullable=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "result IN ('matched', 'no_match', 'no_plate', 'error')",
            name="ck_alpr_verifications_result",
        ),
        sa.ForeignKeyConstraint(
            ["matched_vehicle_id"],
            ["vehicles.id"],
            name="fk_alpr_verifications_vehicle",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["security_accounts.id"],
            name="fk_alpr_verifications_verified_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_alpr_verifications_result", "alpr_verifications", ["result"])
    op.create_index("ix_alpr_verifications_timestamp", "alpr_verifications", ["timestamp"])
    op.create_index("ix_alpr_verifications_detected_plate_normalized", "alpr_verifications", ["detected_plate_normalized"])
    op.create_index("ix_alpr_verifications_matched_vehicle_id", "alpr_verifications", ["matched_vehicle_id"])


def downgrade() -> None:
    op.drop_table("alpr_verifications")
    op.drop_table("face_verifications")
    op.drop_table("face_profiles")
    op.drop_table("vehicles")
    op.drop_table("campus_people")
