"""Create incident_flags table

Revision ID: 0005_incident_flags
Revises: 0004_incidents_media_jobs
Create Date: 2026-10-30 05:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_incident_flags"
down_revision: str | None = "0004_incidents_media_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incident_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("incident_id", "user_id", "type", name="uq_incident_flags_user_type"),
    )
    op.create_index("ix_incident_flags_incident_id", "incident_flags", ["incident_id"])
    op.create_index("ix_incident_flags_user_id", "incident_flags", ["user_id"])
    op.create_index("ix_incident_flags_type", "incident_flags", ["type"])
    op.create_index("ix_incident_flags_incident_type", "incident_flags", ["incident_id", "type"])


def downgrade() -> None:
    op.drop_table("incident_flags")
