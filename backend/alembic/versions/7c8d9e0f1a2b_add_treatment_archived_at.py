"""add treatment archived timestamp

Revision ID: 7c8d9e0f1a2b
Revises: 5d3a7b9c1e24
Create Date: 2026-05-17 13:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c8d9e0f1a2b"
down_revision: str | Sequence[str] | None = "5d3a7b9c1e24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "treatments",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("treatments", "archived_at")
