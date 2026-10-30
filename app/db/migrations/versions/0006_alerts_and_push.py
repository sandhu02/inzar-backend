"""Create alert_preferences, device_tokens, and notification_log tables

Revision ID: 0006_alerts_and_push
Revises: 0005_incident_flags
Create Date: 2026-10-30 06:00:00.000000

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_alerts_and_push"
down_revision: str | None = "0005_incident_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. alert_preferences table
    op.create_table(
        "alert_preferences",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "center",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeogFromText",
                name="geography",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lon", sa.Float(), nullable=False),
        sa.Column("radius_km", sa.Float(), server_default="5.0", nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("min_urgency", sa.String(length=20), server_default="routine", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_preferences_center ON alert_preferences USING GIST (center);"
    )

    # 2. device_tokens table
    op.create_table(
        "device_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=500), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])
    op.create_index("ix_device_tokens_token", "device_tokens", ["token"], unique=True)

    # 3. notification_log table
    op.create_table(
        "notification_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.UniqueConstraint(
            "user_id", "incident_id", "kind", name="uq_notification_log_user_incident_kind"
        ),
    )
    op.create_index("ix_notification_log_user_id", "notification_log", ["user_id"])
    op.create_index("ix_notification_log_incident_id", "notification_log", ["incident_id"])
    op.create_index("ix_notification_log_sent_at", "notification_log", ["sent_at"])


def downgrade() -> None:
    op.drop_table("notification_log")
    op.drop_table("device_tokens")
    op.drop_table("alert_preferences")
