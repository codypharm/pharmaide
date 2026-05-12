"""End-to-end behavior for the Sprint 3 treatment analysis graph."""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import httpx
import pytest
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.test import TestModel

from app.agents.analysis_graph import open_analysis_graph
from app.agents.analysis_schemas import AnalysisState
from app.agents.nodes.summarize import build_summary_agent
from app.errors import run_graph
from app.logging_setup import configure_logging
from app.services.rxnorm import clear_rxnorm_cache

FIRST_MEDICATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_MEDICATION_ID = UUID("22222222-2222-2222-2222-222222222222")
START = datetime(2026, 5, 12, 9, 0, tzinfo=UTC)


async def test_analysis_graph_runs_grounding_ddi_schedule_and_summary(
    tmp_path: Path,
) -> None:
    configure_logging("json")
    clear_rxnorm_cache()
    db_path = str(tmp_path / "analysis.db")
    summary_agent = build_summary_agent(
        model=TestModel(
            custom_output_args={
                "summary": "Analysis completed for pharmacist review.",
                "red_flags": ["DDI provider is not configured."],
                "confidence": 0.74,
            }
        )
    )

    async with (
        httpx.AsyncClient(
            base_url="https://rxnav.test/REST",
            transport=httpx.MockTransport(_rxnorm_handler),
        ) as rxnorm_client,
        open_analysis_graph(
            db_path,
            rxnorm_client=rxnorm_client,
            start_dt=START,
            summary_agent=summary_agent,
        ) as graph,
    ):
        result = await run_graph(
            graph,
            thread_id="treatment-1",
            input_state=_state(),
        )

    state = cast("AnalysisState", result)
    assert [grounding.rxcui for grounding in state["groundings"]] == ["29046", "11289"]
    assert state["ddi_warnings"] == []
    assert state["degraded"] is True
    assert state["schedule"] is not None
    assert len(state["schedule"].reminders) == 5
    assert state["reasoning"] is not None
    assert state["reasoning"].summary == "Analysis completed for pharmacist review."
    assert state["completed_stages"] == [
        "ground_medications",
        "check_interactions",
        "generate_schedule",
        "summarize_treatment",
    ]


@pytest.mark.live_llm
@pytest.mark.skipif(
    os.getenv("PHARMAIDE_RUN_LIVE_LLM") != "1"
    or not os.getenv("PHARMAIDE_OPENAI_API_KEY"),
    reason="Set PHARMAIDE_RUN_LIVE_LLM=1 and PHARMAIDE_OPENAI_API_KEY to run live LLM smoke tests.",
)
async def test_analysis_graph_live_llm_smoke(tmp_path: Path) -> None:
    """Manual smoke test for the real OpenAI structured-output path."""
    configure_logging("json")
    clear_rxnorm_cache()
    api_key = os.environ["PHARMAIDE_OPENAI_API_KEY"]
    summary_agent = build_summary_agent(
        OpenAIResponsesModel("gpt-5-mini", provider=OpenAIProvider(api_key=api_key))
    )

    async with (
        httpx.AsyncClient(
            base_url="https://rxnav.test/REST",
            transport=httpx.MockTransport(_rxnorm_handler),
        ) as rxnorm_client,
        open_analysis_graph(
            str(tmp_path / "analysis-live.db"),
            rxnorm_client=rxnorm_client,
            start_dt=START,
            summary_agent=summary_agent,
        ) as graph,
    ):
        result = await run_graph(
            graph,
            thread_id="live-llm-smoke",
            input_state=_state(),
        )

    state = cast("AnalysisState", result)
    assert state["reasoning"] is not None
    assert state["reasoning"].summary.strip()
    assert 0 <= state["reasoning"].confidence <= 1
    assert [grounding.rxcui for grounding in state["groundings"]] == ["29046", "11289"]
    assert state["schedule"] is not None
    assert state["completed_stages"] == [
        "ground_medications",
        "check_interactions",
        "generate_schedule",
        "summarize_treatment",
    ]


def _state() -> AnalysisState:
    return {
        "treatment_id": UUID("33333333-3333-3333-3333-333333333333"),
        "medications": [
            {
                "id": FIRST_MEDICATION_ID,
                "name": "Lisinopril",
                "dosage": "10 mg",
                "frequency": "BID",
                "duration": "1 day",
                "objective": "blood pressure control",
            },
            {
                "id": SECOND_MEDICATION_ID,
                "name": "Warfarin",
                "dosage": "5 mg",
                "frequency": "Q8H",
                "duration": "1 day",
                "objective": "anticoagulation",
            },
        ],
        "degraded": False,
    }


async def _rxnorm_handler(request: httpx.Request) -> httpx.Response:
    term = request.url.params.get("term", "").lower()
    if "lisinopril" in term:
        return _rxnorm_response("29046", "lisinopril")
    if "warfarin" in term:
        return _rxnorm_response("11289", "warfarin")
    return httpx.Response(200, json={"approximateGroup": {}})


def _rxnorm_response(rxcui: str, name: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "approximateGroup": {
                "candidate": [
                    {
                        "rxcui": rxcui,
                        "name": name,
                        "score": "100",
                    }
                ]
            }
        },
    )
