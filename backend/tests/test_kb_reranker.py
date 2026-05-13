"""Knowledge-base reranker agent behavior."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.kb_reranker import (
    RerankResult,
    build_reranker_agent,
    rerank_citations_with_agent,
)

FIRST_CHUNK_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_CHUNK_ID = UUID("22222222-2222-2222-2222-222222222222")


@dataclass(frozen=True)
class _Candidate:
    chunk_id: UUID
    source_type: Literal["user_upload", "dailymed"]
    document_title: str
    text: str
    score: float


def test_build_reranker_agent_defaults_to_accuracy_then_latency_model() -> None:
    agent = build_reranker_agent()

    assert agent.model == "openai:gpt-5-mini"


async def test_rerank_citations_with_agent_uses_validated_candidate_ids() -> None:
    seen: dict[str, str] = {}

    def model_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = _user_prompt(messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "citations": [
                            {
                                "chunk_id": str(SECOND_CHUNK_ID),
                                "relevance_score": 0.91,
                            }
                        ]
                    },
                )
            ],
            model_name="kb-reranker-test",
        )

    agent: Agent[None, RerankResult] = build_reranker_agent(model=FunctionModel(model_function))

    result = await rerank_citations_with_agent(
        "metformin diarrhoea",
        [
            _Candidate(
                chunk_id=FIRST_CHUNK_ID,
                source_type="dailymed",
                document_title="General Protocol",
                text="General diabetes counselling.",
                score=0.88,
            ),
            _Candidate(
                chunk_id=SECOND_CHUNK_ID,
                source_type="user_upload",
                document_title="Metformin Protocol",
                text="Patients on metformin should report severe diarrhoea.",
                score=0.71,
            ),
        ],
        1,
        agent=agent,
    )

    assert result.citations[0].chunk_id == SECOND_CHUNK_ID
    assert result.citations[0].relevance_score == 0.91
    assert "use only the candidate citations" in seen["instructions"].lower()
    assert "do not invent citations" in seen["instructions"].lower()
    assert "metformin diarrhoea" in seen["prompt"]
    assert "source_type=user_upload" in seen["prompt"]
    assert str(FIRST_CHUNK_ID) in seen["prompt"]
    assert str(SECOND_CHUNK_ID) in seen["prompt"]


def _user_prompt(messages: list[ModelMessage]) -> str:
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    raise AssertionError("expected a user prompt")
