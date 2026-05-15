"""add patient check-ins

Revision ID: f2a7d1c9e4b6
Revises: e6f4a9c2b1d8
Create Date: 2026-05-15 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a7d1c9e4b6"
down_revision: str | Sequence[str] | None = "e6f4a9c2b1d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_check_ins",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("treatment_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
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
        op.f("ix_patient_check_ins_treatment_id"),
        "patient_check_ins",
        ["treatment_id"],
        unique=False,
    )
    op.create_index(
        "idx_patient_check_ins_treatment_created",
        "patient_check_ins",
        ["treatment_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_patient_check_ins_treatment_created", table_name="patient_check_ins")
    op.drop_index(op.f("ix_patient_check_ins_treatment_id"), table_name="patient_check_ins")
    op.drop_table("patient_check_ins")
