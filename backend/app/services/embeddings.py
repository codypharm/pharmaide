"""OpenAI embedding helpers for the knowledge-base pipeline."""

from collections.abc import Sequence
from typing import Protocol

import structlog
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from pydantic import SecretStr
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072
EMBEDDING_BATCH_SIZE = 100

log = structlog.get_logger(__name__)

type EmbeddingVector = list[float]


class EmbeddingConfigurationError(RuntimeError):
    """Raised when the embedding client cannot be configured safely."""


class EmbeddingData(Protocol):
    index: int
    embedding: list[float]


class EmbeddingResponse(Protocol):
    data: list[EmbeddingData]


class EmbeddingsResource(Protocol):
    async def create(
        self,
        *,
        model: str,
        input: list[str],
        encoding_format: str,
        dimensions: int,
    ) -> EmbeddingResponse: ...


class EmbeddingClient(Protocol):
    embeddings: EmbeddingsResource


def build_embedding_client(openai_api_key: SecretStr | None) -> AsyncOpenAI:
    """Build an OpenAI client from the app-prefixed API key setting."""
    if openai_api_key is None:
        raise EmbeddingConfigurationError("PHARMAIDE_OPENAI_API_KEY is required")
    return AsyncOpenAI(api_key=openai_api_key.get_secret_value())


async def embed_texts(
    texts: Sequence[str],
    *,
    client: EmbeddingClient,
) -> list[EmbeddingVector]:
    """Embed text chunks in stable input order."""
    embeddings: list[EmbeddingVector] = []
    batches = _batches([_normalise_text(text) for text in texts], EMBEDDING_BATCH_SIZE)
    for index, batch in enumerate(batches, start=1):
        if not batch:
            continue
        log.info(
            "kb_embedding_batch_started",
            batch_index=index,
            batch_count=len(batches),
            item_count=len(batch),
        )
        response = await _create_embeddings_with_retry(client, batch)
        embeddings.extend(_ordered_embeddings(response))
        log.info(
            "kb_embedding_batch_completed",
            batch_index=index,
            batch_count=len(batches),
            item_count=len(batch),
        )
    return embeddings


@retry(
    retry=retry_if_exception_type(
        (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, max=4),
    reraise=True,
)
async def _create_embeddings_with_retry(
    client: EmbeddingClient,
    batch: list[str],
) -> EmbeddingResponse:
    return await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=batch,
        encoding_format="float",
        dimensions=EMBEDDING_DIMENSIONS,
    )


def _normalise_text(text: str) -> str:
    return text.replace("\x00", "").strip()


def _batches(texts: list[str], size: int) -> list[list[str]]:
    return [texts[index : index + size] for index in range(0, len(texts), size)]


def _ordered_embeddings(response: EmbeddingResponse) -> list[EmbeddingVector]:
    return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
