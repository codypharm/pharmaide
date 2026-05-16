"""add conversation message processed timestamp

Revision ID: 5d3a7b9c1e24
Revises: 1f6b2a9c8e31
Create Date: 2026-05-16 19:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5d3a7b9c1e24"
down_revision: str | Sequence[str] | None = "1f6b2a9c8e31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_conversation_messages_unprocessed",
        "conversation_messages",
        ["treatment_id", "processed_at"],
        unique=False,
        postgresql_where=sa.text("direction = 'inbound' AND sender_type = 'patient'"),
    )


def downgrade() -> None:
    op.drop_index("idx_conversation_messages_unprocessed", table_name="conversation_messages")
    op.drop_column("conversation_messages", "processed_at")
