"""HTTP seam for provider-neutral patient conversation turns."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.agents.safety_schemas import (
    GuardResult,
    PatientDraftSafetyDecision,
    RefereeResult,
    SafetyReview,
)
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conversation tests create treatments as setup; analysis has separate coverage."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_post_conversation_turn_returns_ready_draft(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-001")
    _patch_safety_decision(monkeypatch, treatment_id, status="send")

    response = await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "  Can I take this after food?  ",
            "assistant_draft": "Please follow the timing your pharmacist approved.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["inbound_message"]["body"] == "Can I take this after food?"
    assert payload["assistant_message"]["status"] == "draft_ready"
    assert payload["assistant_message"]["body"] == (
        "Please follow the timing your pharmacist approved."
    )
    assert payload["safety_decision"]["status"] == "send"


@pytest.mark.usefixtures("postgres_container")
async def test_post_conversation_turn_returns_held_draft_when_safety_blocks(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-002")
    _patch_safety_decision(monkeypatch, treatment_id, status="hold_for_pharmacist")

    response = await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "I feel faint after taking extra tablets.",
            "assistant_draft": "This draft must not be sent.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["assistant_message"]["status"] == "held_for_review"
    assert payload["assistant_message"]["safety_hold_reason"] == "input_guard"
    assert payload["safety_decision"]["status"] == "hold_for_pharmacist"
    assert payload["safety_decision"]["message_to_send"] is None


@pytest.mark.usefixtures("postgres_container")
async def test_post_conversation_turn_returns_404_for_unknown_treatment(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(
        f"/treatments/{uuid4()}/conversation-turns",
        json={
            "patient_message": "Hello",
            "assistant_draft": "Draft",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}


async def _create_treatment(app_client: AsyncClient, mrn: str) -> UUID:
    response = await app_client.post(
        "/treatments",
        json={
            "patient": {
                "name": "Eleanor Vance",
                "dob": "1955-10-12",
                "mrn": mrn,
                "phone": "+18005551212",
            },
            "treatment": {"clinical_objective": "Monitor recovery"},
            "medications": [
                {
                    "name": "Amoxicillin",
                    "dosage": "500 mg",
                    "frequency": "Three Times Daily (TID)",
                    "duration": "7 days",
                    "objective": None,
                }
            ],
            "ingestion_method": "structured",
        },
    )
    assert response.status_code == 201
    return UUID(response.json()["treatment_id"])


def _patch_safety_decision(
    monkeypatch: pytest.MonkeyPatch,
    treatment_id: UUID,
    *,
    status: str,
) -> None:
    async def fake_review_patient_draft_safety(*args: object, **kwargs: object) -> object:
        assistant_draft = str(kwargs["assistant_draft"])
        return _safety_decision(treatment_id, status=status, assistant_draft=assistant_draft)

    monkeypatch.setattr(
        "app.services.conversation_messages.review_patient_draft_safety",
        fake_review_patient_draft_safety,
    )


def _safety_decision(
    treatment_id: UUID,
    *,
    status: str,
    assistant_draft: str,
) -> PatientDraftSafetyDecision:
    action = "allow" if status == "send" else "block"
    return PatientDraftSafetyDecision(
        status=status,
        message_to_send=assistant_draft if status == "send" else None,
        hold_reason=None if status == "send" else "input_guard",
        review=SafetyReview(
            treatment_id=treatment_id,
            input_guard=GuardResult(
                stage="input",
                action=action,
                categories=[] if action == "allow" else ["unsafe_medical_advice"],
                rationale="Input guard decision.",
                confidence=0.9,
            ),
            referee=RefereeResult(
                action="allow",
                violations=[],
                rationale="Referee allowed.",
                confidence=0.9,
            ),
            output_guard=GuardResult(
                stage="output",
                action="allow",
                categories=[],
                rationale="Output guard allowed.",
                confidence=0.9,
            ),
        ),
    )
