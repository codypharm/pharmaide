"""switch kb embeddings to large model dimensions

Revision ID: c74f90102ab3
Revises: 9b1d4e7c2a6f
Create Date: 2026-05-13 00:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c74f90102ab3"
down_revision: str | Sequence[str] | None = "9b1d4e7c2a6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SMALL_EMBEDDING_DIMENSIONS = 1536
LARGE_EMBEDDING_DIMENSIONS = 3072


class Vector(sa.types.UserDefinedType[str]):
    """Migration-local VECTOR type for pgvector-compatible databases."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"VECTOR({self.dimensions})"


def upgrade() -> None:
    _drop_vector_index()
    _resize_embedding_column(LARGE_EMBEDDING_DIMENSIONS)
    _create_vector_index()


def downgrade() -> None:
    _drop_vector_index()
    _resize_embedding_column(SMALL_EMBEDDING_DIMENSIONS)
    _create_small_vector_index()


def _resize_embedding_column(dimensions: int) -> None:
    # No ingestion has shipped yet, so production data should not exist here.
    # The explicit cast keeps fresh and already-upgraded dev databases aligned.
    op.alter_column(
        "kb_chunks",
        "embedding",
        type_=Vector(dimensions),
        existing_type=Vector(SMALL_EMBEDDING_DIMENSIONS),
        postgresql_using=f"embedding::vector({dimensions})",
    )


def _create_vector_index() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "cockroachdb":
        op.execute(
            "CREATE VECTOR INDEX idx_kb_chunks_embedding "
            "ON kb_chunks (embedding vector_cosine_ops)"
        )
        return

    # pgvector HNSW cannot index float32 vector columns above 2000 dimensions.
    # Keep full 3072-dim storage for retrieval accuracy, but index a halfvec
    # expression so local/dev Postgres can still use ANN search.
    op.execute(
        "CREATE INDEX idx_kb_chunks_embedding "
        "ON kb_chunks USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)"
    )


def _create_small_vector_index() -> None:
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
