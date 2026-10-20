"""Initial schema: enable pgvector, create security_accounts and audit_logs

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-14 00:00:00.000000

Schema established in this migration:
  - pgvector extension (CREATE EXTENSION IF NOT EXISTS vector)
  - security_accounts: application user accounts (ADMIN/SECURITY)
  - audit_logs: immutable administrative operation log

NOTE: pgvector enabling requires CREATE EXTENSION privilege.
If this migration fails with a permissions error, run the following SQL
in the Supabase SQL Editor (as a superuser):

    CREATE EXTENSION IF NOT EXISTS vector;

Then re-run this migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Enable pgvector extension
    # Required for future face-embedding columns (vector(512))
    # This may fail if the database role lacks CREATE EXTENSION privilege.
    # In that case, enable it manually via the Supabase SQL Editor.
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # security_accounts
    # ------------------------------------------------------------------
    op.create_table(
        "security_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="SECURITY"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("role IN ('ADMIN', 'SECURITY')", name="ck_security_accounts_role"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_security_accounts_status"),
        sa.UniqueConstraint("username", name="uq_security_accounts_username"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["security_accounts.id"],
            name="fk_security_accounts_created_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_security_accounts_username", "security_accounts", ["username"])

    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["security_accounts.id"],
            name="fk_audit_logs_actor_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("security_accounts")
    # Note: We intentionally do NOT drop the pgvector extension on downgrade
    # because other schemas or extensions may depend on it.
