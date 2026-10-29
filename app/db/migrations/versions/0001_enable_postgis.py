"""Enable PostGIS extension

Revision ID: 0001_enable_postgis
Revises:
Create Date: 2026-10-30 01:25:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_enable_postgis"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable PostGIS extension for spatial queries and geometry/geography types
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")


def downgrade() -> None:
    # Downgrade drops postgis extension
    op.execute("DROP EXTENSION IF EXISTS postgis CASCADE;")
