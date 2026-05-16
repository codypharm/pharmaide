"""add treatment conversation modes

Revision ID: 1f6b2a9c8e31
Revises: 6e8a1c4b2d9f
Create Date: 2026-05-16 09:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1f6b2a9c8e31"
down_revision: str | Sequence[str] | None = "6e8a1c4b2d9f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "treatments",
        sa.Column(
            "chat_response_mode",
            sa.Text(),
            server_default=sa.text("'ai_active'"),
            nullable=False,
        ),
    )
    op.add_column(
        "treatments",
        sa.Column(
            "automation_mode",
            sa.Text(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("treatments", "automation_mode")
    op.drop_column("treatments", "chat_response_mode")
