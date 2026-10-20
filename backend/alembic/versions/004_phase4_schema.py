"""Phase 4 schema: security_alerts, alert_notes, security_contacts, notification_log

Revision ID: 004_phase4_schema
Revises: 003_phase3_schema
Create Date: 2026-10-15 00:00:00.000000

New tables:
  - security_alerts    : persistent alert records with lifecycle and deduplication
  - alert_notes        : officer investigation notes per alert
  - security_contacts  : configurable email recipients with notification preferences
  - notification_log   : email delivery tracking with retry and idempotency

NOTE: Does not modify Phase 1, 2, or 3 tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "004_phase4_schema"
down_revision: Union[str, None] = "003_phase3_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # security_alerts
    # ------------------------------------------------------------------
    op.create_table(
        "security_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Classification
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        # Lifecycle
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),

        # Related entities (nullable FKs, soft-linked for audit persistence)
        sa.Column("access_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detected_plate", sa.String(32), nullable=True),
        sa.Column("watchlist_entry_id", postgresql.UUID(as_uuid=True), nullable=True),

        # Timestamps
        sa.Column("first_detected_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        # Occurrence tracking
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        # JSON list of related access_attempt UUIDs for repeated-denial grouping
        sa.Column("related_attempt_ids", sa.JSON(), nullable=True),

        # Assignment
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),

        # Resolution
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_reason", sa.String(512), nullable=True),

        # Idempotency / deduplication key (unique per logical alert group)
        sa.Column("dedup_key", sa.String(256), nullable=True, unique=True),

        # Foreign key constraints
        sa.ForeignKeyConstraint(
            ["access_attempt_id"], ["access_attempts.id"],
            name="fk_security_alerts_access_attempt",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["campus_people.id"],
            name="fk_security_alerts_person",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicles.id"],
            name="fk_security_alerts_vehicle",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["watchlist_entry_id"], ["watchlist_entries.id"],
            name="fk_security_alerts_watchlist",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"], ["security_accounts.id"],
            name="fk_security_alerts_assigned_to",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"], ["security_accounts.id"],
            name="fk_security_alerts_acknowledged_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["security_accounts.id"],
            name="fk_security_alerts_resolved_by",
            ondelete="SET NULL",
        ),

        # Constraints
        sa.CheckConstraint(
            "severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_security_alerts_severity",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','INVESTIGATING','RESOLVED','DISMISSED')",
            name="ck_security_alerts_status",
        ),
        sa.CheckConstraint(
            "category IN ('DENIED_ACCESS','WATCHLIST_HIT','REPEATED_DENIAL','MANUAL_REVIEW','SYSTEM_FAULT','GENERAL')",
            name="ck_security_alerts_category",
        ),
    )
    op.create_index("ix_security_alerts_status", "security_alerts", ["status"])
    op.create_index("ix_security_alerts_severity", "security_alerts", ["severity"])
    op.create_index("ix_security_alerts_first_detected_at", "security_alerts", ["first_detected_at"])
    op.create_index("ix_security_alerts_category", "security_alerts", ["category"])
    op.create_index("ix_security_alerts_detected_plate", "security_alerts", ["detected_plate"])
    op.create_index("ix_security_alerts_person_id", "security_alerts", ["person_id"])
    op.create_index("ix_security_alerts_dedup_key", "security_alerts", ["dedup_key"], unique=True)

    # ------------------------------------------------------------------
    # alert_notes
    # ------------------------------------------------------------------
    op.create_table(
        "alert_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note_type", sa.String(32), nullable=False, server_default="NOTE"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        sa.ForeignKeyConstraint(
            ["alert_id"], ["security_alerts.id"],
            name="fk_alert_notes_alert",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["security_accounts.id"],
            name="fk_alert_notes_author",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "note_type IN ('NOTE','STATUS_CHANGE','ASSIGNMENT','SYSTEM')",
            name="ck_alert_notes_note_type",
        ),
    )
    op.create_index("ix_alert_notes_alert_id", "alert_notes", ["alert_id"])
    op.create_index("ix_alert_notes_created_at", "alert_notes", ["created_at"])

    # ------------------------------------------------------------------
    # security_contacts
    # ------------------------------------------------------------------
    op.create_table(
        "security_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(256), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        # Which alert categories this contact wants; JSON list of category strings
        # Empty/null = all categories
        sa.Column("notify_categories", sa.JSON(), nullable=True),
        # Minimum severity to notify ('LOW','MEDIUM','HIGH','CRITICAL')
        sa.Column("min_severity", sa.String(16), nullable=False, server_default="HIGH"),
        # Whether to receive daily summary emails
        sa.Column("daily_summary_enabled", sa.Boolean(), nullable=False, server_default="true"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        # Last notification result
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notification_status", sa.String(32), nullable=True),

        sa.ForeignKeyConstraint(
            ["created_by"], ["security_accounts.id"],
            name="fk_security_contacts_created_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("email", name="uq_security_contacts_email"),
        sa.CheckConstraint(
            "min_severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_security_contacts_min_severity",
        ),
    )
    op.create_index("ix_security_contacts_is_active", "security_contacts", ["is_active"])
    op.create_index("ix_security_contacts_email", "security_contacts", ["email"])

    # ------------------------------------------------------------------
    # notification_log
    # ------------------------------------------------------------------
    op.create_table(
        "notification_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # What triggered this notification
        sa.Column("notification_type", sa.String(32), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_email", sa.String(256), nullable=False),
        sa.Column("subject", sa.String(512), nullable=False),
        # Delivery state
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        # Provider details (never store secrets here)
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("provider_message_id", sa.String(256), nullable=True),
        # Sanitized error info (no credentials)
        sa.Column("error_detail", sa.String(512), nullable=True),
        # Idempotency key
        sa.Column("idempotency_key", sa.String(256), nullable=True, unique=True),
        # Daily summary metadata
        sa.Column("summary_date", sa.String(10), nullable=True),  # 'YYYY-MM-DD'

        sa.ForeignKeyConstraint(
            ["alert_id"], ["security_alerts.id"],
            name="fk_notification_log_alert",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["security_contacts.id"],
            name="fk_notification_log_contact",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','SENDING','SENT','FAILED','RETRY_SCHEDULED')",
            name="ck_notification_log_status",
        ),
        sa.CheckConstraint(
            "notification_type IN ('ALERT','DAILY_SUMMARY','TEST')",
            name="ck_notification_log_type",
        ),
    )
    op.create_index("ix_notification_log_status", "notification_log", ["status"])
    op.create_index("ix_notification_log_created_at", "notification_log", ["created_at"])
    op.create_index("ix_notification_log_contact_id", "notification_log", ["contact_id"])
    op.create_index("ix_notification_log_alert_id", "notification_log", ["alert_id"])
    op.create_index(
        "ix_notification_log_idempotency_key", "notification_log",
        ["idempotency_key"], unique=True,
    )


def downgrade() -> None:
    op.drop_table("notification_log")
    op.drop_table("security_contacts")
    op.drop_table("alert_notes")
    op.drop_table("security_alerts")
