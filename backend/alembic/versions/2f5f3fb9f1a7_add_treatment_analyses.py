"""add treatment analyses

Revision ID: 2f5f3fb9f1a7
Revises: 8c2a1e3b9d44
Create Date: 2026-05-12 11:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2f5f3fb9f1a7"
down_revision: str | Sequence[str] | None = "8c2a1e3b9d44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "treatment_analyses",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("treatment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        "idx_treatment_analyses_treatment_created",
        "treatment_analyses",
        ["treatment_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_treatment_analyses_active_treatment",
        "treatment_analyses",
        ["treatment_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_treatment_analyses_active_treatment", table_name="treatment_analyses")
    op.drop_index("idx_treatment_analyses_treatment_created", table_name="treatment_analyses")
    op.drop_table("treatment_analyses")
