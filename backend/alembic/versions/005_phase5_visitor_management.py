"""Phase 5 schema: visitor_passes, visitor_approvals, visitor links on access_attempts and security_alerts

Revision ID: 005_phase5_visitor_management
Revises: 004_phase4_schema
Create Date: 2026-10-18 00:00:00.000000

New tables:
  - visitor_passes    : secure temporary passes with SHA-256 token hashes, QR metadata & lifecycle
  - visitor_approvals : mandatory security officer approval queue for visitor entry/exit

Extended tables:
  - access_attempts   : add visitor_pass_id column and foreign key
  - security_alerts   : add visitor_pass_id column, foreign key, and expanded category check constraint
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "005_phase5_visitor_management"
down_revision: Union[str, None] = "004_phase4_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. visitor_passes table
    # ------------------------------------------------------------------
    op.create_table(
        "visitor_passes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pass_number", sa.String(32), nullable=False),
        sa.Column("visitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campus_people.id", ondelete="CASCADE"), nullable=False),
        sa.Column("host_person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campus_people.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vehicle_plate", sa.String(32), nullable=True),
        sa.Column("purpose", sa.String(128), nullable=False, server_default="Campus Meeting"),
        sa.Column("organization", sa.String(128), nullable=True),
        sa.Column("id_type", sa.String(64), nullable=True),
        sa.Column("id_number", sa.String(64), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("qr_code_path", sa.String(512), nullable=True),
        sa.Column("qr_storage_path", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ISSUED"),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_in_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revocation_reason", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("pass_number", name="uq_visitor_passes_pass_number"),
        sa.UniqueConstraint("token_hash", name="uq_visitor_passes_token_hash"),
        sa.CheckConstraint(
            "status IN ('ISSUED','PENDING_APPROVAL','ACTIVE_INSIDE','COMPLETED','EXPIRED','REVOKED','DENIED')",
            name="ck_visitor_passes_status",
        ),
    )
    op.create_index("ix_visitor_passes_pass_number", "visitor_passes", ["pass_number"])
    op.create_index("ix_visitor_passes_token_hash", "visitor_passes", ["token_hash"])
    op.create_index("ix_visitor_passes_visitor_id", "visitor_passes", ["visitor_id"])
    op.create_index("ix_visitor_passes_host_person_id", "visitor_passes", ["host_person_id"])
    op.create_index("ix_visitor_passes_status", "visitor_passes", ["status"])

    # ------------------------------------------------------------------
    # 2. visitor_approvals table
    # ------------------------------------------------------------------
    op.create_table(
        "visitor_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pass_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visitor_passes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campus_people.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("scanned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("direction", sa.String(8), nullable=False, server_default="ENTRY"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("decision_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denial_reason", sa.String(512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("access_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("access_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_alerts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','DENIED','CANCELLED')",
            name="ck_visitor_approvals_status",
        ),
        sa.CheckConstraint(
            "direction IN ('ENTRY','EXIT')",
            name="ck_visitor_approvals_direction",
        ),
    )
    op.create_index("ix_visitor_approvals_pass_id", "visitor_approvals", ["pass_id"])
    op.create_index("ix_visitor_approvals_visitor_id", "visitor_approvals", ["visitor_id"])
    op.create_index("ix_visitor_approvals_status", "visitor_approvals", ["status"])

    # ------------------------------------------------------------------
    # 3. Soft-link columns in access_attempts and security_alerts
    # ------------------------------------------------------------------
    op.add_column(
        "access_attempts",
        sa.Column("visitor_pass_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visitor_passes.id", ondelete="SET NULL"), nullable=True)
    )
    op.create_index("ix_access_attempts_visitor_pass_id", "access_attempts", ["visitor_pass_id"])

    op.add_column(
        "security_alerts",
        sa.Column("visitor_pass_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visitor_passes.id", ondelete="SET NULL"), nullable=True)
    )
    op.create_index("ix_security_alerts_visitor_pass_id", "security_alerts", ["visitor_pass_id"])

    # ------------------------------------------------------------------
    # 4. Update check constraint on security_alerts.category safely
    # ------------------------------------------------------------------
    try:
        op.drop_constraint("ck_security_alerts_category", "security_alerts", type_="check")
    except Exception:
        pass
    op.create_check_constraint(
        "ck_security_alerts_category",
        "security_alerts",
        "category IN ('DENIED_ACCESS','WATCHLIST_HIT','REPEATED_DENIAL','MANUAL_REVIEW','SYSTEM_FAULT','GENERAL','VISITOR_APPROVAL','VISITOR_VIOLATION')"
    )


def downgrade() -> None:
    try:
        op.drop_constraint("ck_security_alerts_category", "security_alerts", type_="check")
        op.create_check_constraint(
            "ck_security_alerts_category",
            "security_alerts",
            "category IN ('DENIED_ACCESS','WATCHLIST_HIT','REPEATED_DENIAL','MANUAL_REVIEW','SYSTEM_FAULT','GENERAL')"
        )
    except Exception:
        pass

    op.drop_index("ix_security_alerts_visitor_pass_id", table_name="security_alerts")
    op.drop_column("security_alerts", "visitor_pass_id")

    op.drop_index("ix_access_attempts_visitor_pass_id", table_name="access_attempts")
    op.drop_column("access_attempts", "visitor_pass_id")

    op.drop_index("ix_visitor_approvals_status", table_name="visitor_approvals")
    op.drop_index("ix_visitor_approvals_visitor_id", table_name="visitor_approvals")
    op.drop_index("ix_visitor_approvals_pass_id", table_name="visitor_approvals")
    op.drop_table("visitor_approvals")

    op.drop_index("ix_visitor_passes_status", table_name="visitor_passes")
    op.drop_index("ix_visitor_passes_host_person_id", table_name="visitor_passes")
    op.drop_index("ix_visitor_passes_visitor_id", table_name="visitor_passes")
    op.drop_index("ix_visitor_passes_token_hash", table_name="visitor_passes")
    op.drop_index("ix_visitor_passes_pass_number", table_name="visitor_passes")
    op.drop_table("visitor_passes")
