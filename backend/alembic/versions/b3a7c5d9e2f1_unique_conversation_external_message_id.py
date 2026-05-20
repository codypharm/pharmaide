"""dedupe conversation messages by provider id

Revision ID: b3a7c5d9e2f1
Revises: 9d4a6f2b8c13
Create Date: 2026-05-20 14:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3a7c5d9e2f1"
down_revision: str | Sequence[str] | None = "9d4a6f2b8c13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_conversation_messages_external_message_id",
        "conversation_messages",
        ["external_message_id"],
        unique=True,
        postgresql_where=sa.text("external_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_conversation_messages_external_message_id",
        table_name="conversation_messages",
    )
