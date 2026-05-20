"""Deterministic patient-reply classification evaluation cases.

The live app uses a low-latency PydanticAI classifier for natural patient
phrases, then falls back to keyword matching if the model is unavailable. These
eval cases pin clinically important intents without making a live model call.
"""

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.patient_reply_classifier import (
    PatientReplyClassification,
    build_patient_reply_classifier_agent,
    classify_patient_reply_with_agent,
)
from app.services.patient_reply_capture import classify_patient_reply

pytestmark = pytest.mark.clinical_eval


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("I already had it after breakfast", "taken"),
        ("I forgot this morning", "missed"),
        ("My stomach hurts after the tablet", "side_effect"),
    ],
)
async def test_patient_reply_classifier_eval_routes_natural_patient_phrases(
    message: str,
    expected_intent: str,
) -> None:
    agent: Agent[None, PatientReplyClassification] = build_patient_reply_classifier_agent(
        model=FunctionModel(_classification_eval_model)
    )

    classification = await classify_patient_reply_with_agent(message, agent=agent)

    assert classification.intent == expected_intent
    assert classification.confidence >= 0.85


def test_patient_reply_classifier_eval_fallback_keeps_clear_missed_dose_signal() -> None:
    classification = classify_patient_reply("I forgot this morning")

    assert classification.intent == "missed"
    assert classification.confidence >= 0.9


def _classification_eval_model(
    messages: list[ModelMessage],
    info: AgentInfo,
) -> ModelResponse:
    prompt = _user_prompt(messages).lower()
    output_tool = info.output_tools[0]
    if "already had it" in prompt:
        intent = "taken"
    elif "forgot" in prompt:
        intent = "missed"
    elif "stomach hurts" in prompt:
        intent = "side_effect"
    else:
        intent = "general"
    return ModelResponse(
        parts=[ToolCallPart(output_tool.name, {"intent": intent, "confidence": 0.91})],
        model_name="patient-reply-classification-eval",
    )


def _user_prompt(messages: list[ModelMessage]) -> str:
    for message in messages:
        if isinstance(message, ModelRequest):
            return "\n".join(
                str(part.content) for part in message.parts if hasattr(part, "content")
            )
    raise AssertionError("expected a user prompt")
