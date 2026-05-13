"""Embedding service tests."""

from dataclasses import dataclass

from app.services.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, embed_texts


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
