"""Create incidents, incident_media, and jobs tables

Revision ID: 0004_incidents_media_jobs
Revises: 0003_categories_settings_audit
Create Date: 2026-10-30 04:00:00.000000

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_incidents_media_jobs"
down_revision: str | None = "0003_categories_settings_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. incidents table
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reporter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "location_exact",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeogFromText",
                name="geography",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "location_public",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeogFromText",
                name="geography",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("public_lat", sa.Float(), nullable=False),
        sa.Column("public_lon", sa.Float(), nullable=False),
        sa.Column("place_label", sa.String(length=200), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=30),
            server_default="awaiting_media",
            nullable=False,
        ),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column(
            "verification_label",
            sa.String(length=30),
            server_default="none",
            nullable=False,
        ),
        sa.Column(
            "lifecycle_status",
            sa.String(length=30),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_incidents_reporter_id", "incidents", ["reporter_id"])
    op.create_index("ix_incidents_category_id", "incidents", ["category_id"])
    op.create_index("ix_incidents_review_status", "incidents", ["review_status"])
    op.create_index("ix_incidents_lifecycle_status", "incidents", ["lifecycle_status"])
    op.create_index("ix_incidents_published_at", "incidents", ["published_at"])
    op.create_index(
        "ix_incidents_status_composite",
        "incidents",
        ["review_status", "lifecycle_status", "published_at"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_incidents_location_public ON incidents USING GIST (location_public);"
    )

    # 2. incident_media table
    op.create_table(
        "incident_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cloudinary_public_id", sa.String(length=255), nullable=False),
        sa.Column("secure_url", sa.String(length=500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_incident_media_incident_id", "incident_media", ["incident_id"])

    # 3. jobs table
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="queued",
            nullable=False,
        ),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_jobs_type", "jobs", ["type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_run_at", "jobs", ["run_at"])
    op.create_index("ix_jobs_status_run_at", "jobs", ["status", "run_at"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("incident_media")
    op.drop_table("incidents")
