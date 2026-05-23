"""add treatment scope id

Revision ID: c2a4d8f1b7e9
Revises: b3a7c5d9e2f1
Create Date: 2026-05-23 00:00:00.000000

"""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from alembic import op

revision: str = "c2a4d8f1b7e9"
down_revision: str | Sequence[str] | None = "b3a7c5d9e2f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEV_ANONYMOUS_SCOPE_ID = uuid5(NAMESPACE_URL, "pharmaide:dev:anonymous")


def upgrade() -> None:
    op.add_column("treatments", sa.Column("scope_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text("UPDATE treatments SET scope_id = :scope_id WHERE scope_id IS NULL").bindparams(
            scope_id=DEV_ANONYMOUS_SCOPE_ID
        )
    )
    op.alter_column("treatments", "scope_id", nullable=False)
    op.create_index("ix_treatments_scope_id", "treatments", ["scope_id"])


def downgrade() -> None:
    op.drop_index("ix_treatments_scope_id", table_name="treatments")
    op.drop_column("treatments", "scope_id")
