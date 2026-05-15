"""add triage items

Revision ID: 6e8a1c4b2d9f
Revises: 4a9c2f6e8b1d
Create Date: 2026-05-15 15:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6e8a1c4b2d9f"
down_revision: str | Sequence[str] | None = "4a9c2f6e8b1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "triage_items",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("treatment_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_message_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_message_id"],
            ["conversation_messages.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["treatment_id"], ["treatments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_triage_items_treatment_id"),
        "triage_items",
        ["treatment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_triage_items_conversation_message_id"),
        "triage_items",
        ["conversation_message_id"],
        unique=False,
    )
    op.create_index(
        "idx_triage_items_status_created",
        "triage_items",
        ["status", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_triage_items_treatment_created",
        "triage_items",
        ["treatment_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_triage_items_treatment_created", table_name="triage_items")
    op.drop_index("idx_triage_items_status_created", table_name="triage_items")
    op.drop_index(op.f("ix_triage_items_conversation_message_id"), table_name="triage_items")
    op.drop_index(op.f("ix_triage_items_treatment_id"), table_name="triage_items")
    op.drop_table("triage_items")
