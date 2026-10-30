"""Create categories, app_settings, and audit_log tables

Revision ID: 0003_categories_settings_audit
Revises: 0002_users_and_auth
Create Date: 2026-10-30 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_categories_settings_audit"
down_revision: str | None = "0002_users_and_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. categories table
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("icon_key", sa.String(length=50), nullable=False),
        sa.Column("color_hex", sa.String(length=7), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("urgency", sa.String(length=20), server_default="routine", nullable=False),
        sa.Column("default_ttl_minutes", sa.Integer(), server_default="1440", nullable=False),
        sa.Column("stale_after_minutes", sa.Integer(), server_default="180", nullable=False),
        sa.Column("resolve_flag_threshold", sa.Integer(), server_default="3", nullable=False),
        sa.Column("notify_throttle_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("notify_by_default", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("require_manual_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("safety_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)
    op.create_index("ix_categories_is_active", "categories", ["is_active"])

    # 2. app_settings table
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # 3. audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_target_type", "audit_log", ["target_type"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("app_settings")
    op.drop_table("categories")
