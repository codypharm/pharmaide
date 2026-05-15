"""add treatment start timestamp

Revision ID: e6f4a9c2b1d8
Revises: a1f4c9d2e7b0
Create Date: 2026-05-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6f4a9c2b1d8"
down_revision: str | Sequence[str] | None = "a1f4c9d2e7b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "treatments",
        sa.Column("treatment_start_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("treatments", "treatment_start_at")
