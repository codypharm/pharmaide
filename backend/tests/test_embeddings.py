"""Embedding service tests."""

import os
from dataclasses import dataclass

import pytest
from pydantic import SecretStr

from app.services.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    build_embedding_client,
    embed_texts,
)


@dataclass(frozen=True)
class _EmbeddingData:
    index: int
    embedding: list[float]


@dataclass(frozen=True)
class _EmbeddingResponse:
    data: list[_EmbeddingData]


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create(
        self,
        *,
        model: str,
        input: list[str],
        encoding_format: str,
        dimensions: int,
    ) -> _EmbeddingResponse:
        self.calls.append(
            {
                "model": model,
                "input": input,
                "encoding_format": encoding_format,
                "dimensions": dimensions,
            }
        )
        return _EmbeddingResponse(
            data=[
                _EmbeddingData(index=index, embedding=[float(len(text)), float(index)])
                for index, text in enumerate(input)
            ]
        )


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddings()


async def test_embed_texts_batches_requests_and_preserves_order() -> None:
    client = _FakeOpenAIClient()
    texts = [f"chunk {index}" for index in range(101)]

    embeddings = await embed_texts(texts, client=client)

    assert len(client.embeddings.calls) == 2
    assert client.embeddings.calls[0] == {
        "model": EMBEDDING_MODEL,
        "input": texts[:100],
        "encoding_format": "float",
        "dimensions": EMBEDDING_DIMENSIONS,
    }
    assert client.embeddings.calls[1]["input"] == texts[100:]
    assert embeddings[0] == [7.0, 0.0]
    assert embeddings[99] == [8.0, 99.0]
    assert embeddings[100] == [9.0, 0.0]


@pytest.mark.live_embedding
@pytest.mark.skipif(
    os.getenv("PHARMAIDE_RUN_LIVE_EMBEDDING") != "1"
    or not os.getenv("PHARMAIDE_OPENAI_API_KEY"),
    reason=(
        "Set PHARMAIDE_RUN_LIVE_EMBEDDING=1 and PHARMAIDE_OPENAI_API_KEY to run "
        "live embedding smoke tests."
    ),
)
async def test_embed_texts_live_embedding_smoke() -> None:
    """Manual smoke test for the real OpenAI embedding path."""
    client = build_embedding_client(SecretStr(os.environ["PHARMAIDE_OPENAI_API_KEY"]))
    try:
        embeddings = await embed_texts(
            ["Warfarin requires INR monitoring."],
            client=client,
        )
    finally:
        await client.close()

    assert len(embeddings) == 1
    assert len(embeddings[0]) == EMBEDDING_DIMENSIONS
    assert all(isinstance(value, float) for value in embeddings[0])
