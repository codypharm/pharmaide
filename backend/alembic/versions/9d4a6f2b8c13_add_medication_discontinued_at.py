"""add medication discontinued timestamp

Revision ID: 9d4a6f2b8c13
Revises: 7c8d9e0f1a2b
Create Date: 2026-05-17 18:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9d4a6f2b8c13"
down_revision: str | Sequence[str] | None = "7c8d9e0f1a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "medications",
        sa.Column("discontinued_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("medications", "discontinued_at")
