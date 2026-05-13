"""Validated LLM reranker for knowledge-base citations.

Vector search is good at broad recall, but it can rank semantically similar
chunks above the clinically sharper passage. This agent is the second stage:
it sees only already-retrieved citations, chooses the most relevant chunk IDs,
and returns validated scores. It must not create new citations or clinical
claims; downstream reasoning still happens in the analysis graph.
"""

from collections.abc import Sequence
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent
from pydantic_ai.models import Model


class CitationLike(Protocol):
    """Citation attributes required to build the reranking prompt."""

    chunk_id: UUID
    source_type: Literal["user_upload", "dailymed"]
    document_title: str
    text: str
    score: float


class RerankerEnvelope(BaseModel):
    """Base class for strict reranker payloads."""

    model_config = ConfigDict(extra="forbid")


class RerankedCitation(RerankerEnvelope):
    """One candidate selected by the reranker."""

    chunk_id: UUID
    relevance_score: float = Field(ge=0, le=1)


class RerankResult(RerankerEnvelope):
    """Validated reranker output used before citations enter the graph."""

    citations: list[RerankedCitation]

    @model_validator(mode="after")
    def _reject_duplicate_chunks(self) -> "RerankResult":
        chunk_ids = [citation.chunk_id for citation in self.citations]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("reranked citations must be unique")
        return self


RERANK_INSTRUCTIONS = """
You are PharmaAide's knowledge-base reranker.
Use only the candidate citations provided in the prompt.
Select the citations most relevant to the pharmacist's clinical query.
Return only candidate chunk IDs that appear in the prompt.
Do not invent citations, medications, patient facts, or clinical conclusions.
Prefer passages with specific actionable clinical details over broad background text.
Prefer clinic-uploaded assets over public references when both are similarly relevant.
"""


def build_reranker_agent(
    model: Model | str = "openai:gpt-5-mini",
) -> Agent[None, RerankResult]:
    """Build the typed PydanticAI agent used for citation reranking."""
    return Agent(
        model,
        output_type=RerankResult,
        instructions=RERANK_INSTRUCTIONS,
        defer_model_check=True,
    )


async def rerank_citations_with_agent(
    query: str,
    candidates: Sequence[CitationLike],
    limit: int,
    *,
    agent: Agent[None, RerankResult] | None = None,
) -> RerankResult:
    """Rerank retrieved citations with a validated PydanticAI agent."""
    reranker = agent or build_reranker_agent()
    result = await reranker.run(_rerank_prompt(query, candidates, limit))
    return result.output


def _rerank_prompt(query: str, candidates: Sequence[CitationLike], limit: int) -> str:
    return "\n".join(
        [
            "Rerank these retrieved knowledge-base citations.",
            f"Return at most {limit} citations.",
            f"query: {query}",
            "candidates:",
            _candidate_section(candidates),
        ]
    )


def _candidate_section(candidates: Sequence[CitationLike]) -> str:
    if not candidates:
        return "- none"
    return "\n".join(
        (
            f"- chunk_id={candidate.chunk_id} document_title={candidate.document_title} "
            f"source_type={candidate.source_type} retrieval_score={candidate.score}\n"
            f"  text={candidate.text}"
        )
        for candidate in candidates
    )
