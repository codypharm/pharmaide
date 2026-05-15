"""add conversation messages

Revision ID: 4a9c2f6e8b1d
Revises: b7c4e1a9d3f2
Create Date: 2026-05-15 15:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4a9c2f6e8b1d"
down_revision: str | Sequence[str] | None = "b7c4e1a9d3f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("treatment_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("sender_type", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("safety_hold_reason", sa.Text(), nullable=True),
        sa.Column("external_message_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["treatment_id"], ["treatments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_messages_treatment_id"),
        "conversation_messages",
        ["treatment_id"],
        unique=False,
    )
    op.create_index(
        "idx_conversation_messages_treatment_created",
        "conversation_messages",
        ["treatment_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_conversation_messages_treatment_created",
        table_name="conversation_messages",
    )
    op.drop_index(
        op.f("ix_conversation_messages_treatment_id"),
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
