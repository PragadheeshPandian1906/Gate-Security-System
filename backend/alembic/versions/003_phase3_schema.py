"""Phase 3 schema: access_schedules, watchlist_entries, access_attempts

Revision ID: 003_phase3_schema
Revises: 002_phase2_schema
Create Date: 2026-10-15 00:00:00.000000

Schema established in this migration:
  - access_schedules    : per-weekday open/close times with campus timezone
  - watchlist_entries   : vehicle watchlist with severity, expiry, resolution
  - access_attempts     : full access-decision audit record (Phase 3 core)

NOTE: Does not modify Phase 1 or Phase 2 tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "003_phase3_schema"
down_revision: Union[str, None] = "002_phase2_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # access_schedules
    # ------------------------------------------------------------------
    op.create_table(
        "access_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("weekday", sa.String(16), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("open_time", sa.String(5), nullable=True),
        sa.Column("close_time", sa.String(5), nullable=True),
        sa.Column("campus_timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "weekday IN ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')",
            name="ck_access_schedules_weekday",
        ),
        sa.UniqueConstraint("weekday", name="uq_access_schedules_weekday"),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["security_accounts.id"],
            name="fk_access_schedules_updated_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_access_schedules_weekday", "access_schedules", ["weekday"])

    # Seed default schedule: Mon–Sat 08:00–17:00, Sun closed
    op.execute("""
        INSERT INTO access_schedules (id, weekday, is_open, open_time, close_time, campus_timezone)
        VALUES
          (gen_random_uuid(), 'monday',    true,  '08:00', '17:00', 'Asia/Kolkata'),
          (gen_random_uuid(), 'tuesday',   true,  '08:00', '17:00', 'Asia/Kolkata'),
          (gen_random_uuid(), 'wednesday', true,  '08:00', '17:00', 'Asia/Kolkata'),
          (gen_random_uuid(), 'thursday',  true,  '08:00', '17:00', 'Asia/Kolkata'),
          (gen_random_uuid(), 'friday',    true,  '08:00', '17:00', 'Asia/Kolkata'),
          (gen_random_uuid(), 'saturday',  true,  '08:00', '17:00', 'Asia/Kolkata'),
          (gen_random_uuid(), 'sunday',    false, NULL,    NULL,    'Asia/Kolkata')
        ON CONFLICT (weekday) DO NOTHING
    """)

    # ------------------------------------------------------------------
    # watchlist_entries
    # ------------------------------------------------------------------
    op.create_table(
        "watchlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("plate_raw", sa.String(32), nullable=True),
        sa.Column("plate_normalized", sa.String(32), nullable=True),
        sa.Column("reason", sa.String(512), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False, server_default="medium"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_note", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "severity IN ('low','medium','high')",
            name="ck_watchlist_severity",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name="fk_watchlist_vehicle",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["security_accounts.id"],
            name="fk_watchlist_created_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["security_accounts.id"],
            name="fk_watchlist_resolved_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_watchlist_vehicle_id", "watchlist_entries", ["vehicle_id"])
    op.create_index("ix_watchlist_plate_normalized", "watchlist_entries", ["plate_normalized"])
    op.create_index("ix_watchlist_is_active", "watchlist_entries", ["is_active"])

    # ------------------------------------------------------------------
    # access_attempts
    # ------------------------------------------------------------------
    op.create_table(
        "access_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(8), nullable=False),
        # Face context
        sa.Column("face_verification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("face_result", sa.String(32), nullable=True),
        sa.Column("face_confidence", sa.Float(), nullable=True),
        sa.Column("matched_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_status", sa.String(16), nullable=True),
        # Plate / vehicle context
        sa.Column("alpr_verification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detected_plate", sa.String(32), nullable=True),
        sa.Column("detected_plate_normalized", sa.String(32), nullable=True),
        sa.Column("matched_vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vehicle_status", sa.String(16), nullable=True),
        sa.Column("vehicle_owner_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Policy results
        sa.Column("ownership_ok", sa.Boolean(), nullable=True),
        sa.Column("schedule_ok", sa.Boolean(), nullable=True),
        sa.Column("watchlist_hit", sa.Boolean(), nullable=True),
        sa.Column("watchlist_severity", sa.String(8), nullable=True),
        # Decision
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("gate_result", sa.String(16), nullable=False, server_default="CLOSED"),
        sa.Column("processing_ms", sa.Float(), nullable=True),
        # Audit
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=True),
        # Manual review
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("review_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("review_resolution", sa.String(16), nullable=True),
        sa.Column("review_reason", sa.String(512), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.CheckConstraint(
            "decision IN ('ALLOW','DENY','MANUAL_REVIEW')",
            name="ck_access_attempts_decision",
        ),
        sa.CheckConstraint(
            "direction IN ('ENTRY','EXIT')",
            name="ck_access_attempts_direction",
        ),
        sa.CheckConstraint(
            "gate_result IN ('OPEN','CLOSED','MANUAL_REVIEW')",
            name="ck_access_attempts_gate_result",
        ),
        # Foreign keys
        sa.ForeignKeyConstraint(
            ["face_verification_id"],
            ["face_verifications.id"],
            name="fk_access_attempts_face_ver",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["alpr_verification_id"],
            ["alpr_verifications.id"],
            name="fk_access_attempts_alpr_ver",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["matched_person_id"],
            ["campus_people.id"],
            name="fk_access_attempts_person",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_owner_person_id"],
            ["campus_people.id"],
            name="fk_access_attempts_vehicle_owner",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["matched_vehicle_id"],
            ["vehicles.id"],
            name="fk_access_attempts_vehicle",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by"],
            ["security_accounts.id"],
            name="fk_access_attempts_initiated_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["security_accounts.id"],
            name="fk_access_attempts_reviewed_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_access_attempts_timestamp", "access_attempts", ["timestamp"])
    op.create_index("ix_access_attempts_decision", "access_attempts", ["decision"])
    op.create_index("ix_access_attempts_direction", "access_attempts", ["direction"])
    op.create_index("ix_access_attempts_matched_person_id", "access_attempts", ["matched_person_id"])
    op.create_index("ix_access_attempts_matched_vehicle_id", "access_attempts", ["matched_vehicle_id"])
    op.create_index("ix_access_attempts_review_required", "access_attempts", ["review_required"])
    op.create_index("ix_access_attempts_detected_plate_normalized", "access_attempts", ["detected_plate_normalized"])


def downgrade() -> None:
    op.drop_table("access_attempts")
    op.drop_table("watchlist_entries")
    op.drop_table("access_schedules")
