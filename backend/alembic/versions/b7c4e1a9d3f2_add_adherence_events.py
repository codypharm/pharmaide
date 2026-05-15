"""add adherence events

Revision ID: b7c4e1a9d3f2
Revises: f2a7d1c9e4b6
Create Date: 2026-05-15 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c4e1a9d3f2"
down_revision: str | Sequence[str] | None = "f2a7d1c9e4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adherence_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("treatment_id", sa.Uuid(), nullable=False),
        sa.Column("medication_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["treatment_id"], ["treatments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_adherence_events_treatment_id"),
        "adherence_events",
        ["treatment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_adherence_events_medication_id"),
        "adherence_events",
        ["medication_id"],
        unique=False,
    )
    op.create_index(
        "idx_adherence_events_treatment_created",
        "adherence_events",
        ["treatment_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_adherence_events_medication_scheduled",
        "adherence_events",
        ["medication_id", "scheduled_for"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_adherence_events_medication_scheduled", table_name="adherence_events")
    op.drop_index("idx_adherence_events_treatment_created", table_name="adherence_events")
    op.drop_index(op.f("ix_adherence_events_medication_id"), table_name="adherence_events")
    op.drop_index(op.f("ix_adherence_events_treatment_id"), table_name="adherence_events")
    op.drop_table("adherence_events")
