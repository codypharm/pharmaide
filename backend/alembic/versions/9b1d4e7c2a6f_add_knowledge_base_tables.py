"""add knowledge base tables

Revision ID: 9b1d4e7c2a6f
Revises: 2f5f3fb9f1a7
Create Date: 2026-05-13 00:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9b1d4e7c2a6f"
down_revision: str | Sequence[str] | None = "2f5f3fb9f1a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 1536


class Vector(sa.types.UserDefinedType[str]):
    """Migration-local VECTOR type for pgvector-compatible databases."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"VECTOR({self.dimensions})"


def upgrade() -> None:
    _ensure_vector_type()
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["kb_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_kb_chunks_document_ordinal",
        "kb_chunks",
        ["document_id", "ordinal"],
        unique=False,
    )
    _create_vector_index()


def downgrade() -> None:
    _drop_vector_index()
    op.drop_index("idx_kb_chunks_document_ordinal", table_name="kb_chunks")
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")


def _ensure_vector_type() -> None:
    # PostgreSQL needs the pgvector extension. Cockroach exposes VECTOR
    # natively through a pgvector-compatible surface, so CREATE EXTENSION is
    # intentionally skipped there.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def _create_vector_index() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "cockroachdb":
        op.execute(
            "CREATE VECTOR INDEX idx_kb_chunks_embedding "
            "ON kb_chunks (embedding vector_cosine_ops)"
        )
        return

    op.execute(
        "CREATE INDEX idx_kb_chunks_embedding "
        "ON kb_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def _drop_vector_index() -> None:
    if op.get_bind().dialect.name == "cockroachdb":
        op.execute("DROP INDEX IF EXISTS kb_chunks@idx_kb_chunks_embedding")
        return

    op.drop_index("idx_kb_chunks_embedding", table_name="kb_chunks")
