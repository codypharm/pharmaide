"""unique kb document source owner

Revision ID: d8b6c9214f52
Revises: c74f90102ab3
Create Date: 2026-05-13 19:20:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d8b6c9214f52"
down_revision: str | Sequence[str] | None = "c74f90102ab3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY source_type, source_uri, uploaded_by
                    ORDER BY created_at, id
                ) AS duplicate_rank
            FROM kb_documents
            WHERE uploaded_by IS NOT NULL
        )
        DELETE FROM kb_documents
        WHERE id IN (
            SELECT id FROM ranked WHERE duplicate_rank > 1
        )
        """
    )
    op.create_index(
        "uq_kb_documents_source_owner_uri",
        "kb_documents",
        ["source_type", "source_uri", "uploaded_by"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_kb_documents_source_owner_uri", table_name="kb_documents")
