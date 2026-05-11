"""use clock_timestamp() for created_at defaults

Switches every created_at server_default from now() (transaction-start
time) to clock_timestamp() (statement-time). With now(), rows written
inside a single transaction tie on created_at and the secondary sort is
undefined, which breaks audit-trail / triage-feed ordering.

Revision ID: 8c2a1e3b9d44
Revises: 503b50094423
Create Date: 2026-05-11 12:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8c2a1e3b9d44"
down_revision: str | Sequence[str] | None = "503b50094423"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = ("patients", "treatments", "medications", "audit_log")


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(
            table,
            "created_at",
            server_default=sa.text("clock_timestamp()"),
        )


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(
            table,
            "created_at",
            server_default=sa.text("now()"),
        )
