"""HTTP seam for provider-neutral patient conversation turns."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.patient_reply import PatientReplyDraft
from app.agents.safety_schemas import (
    GuardResult,
    PatientDraftSafetyDecision,
    RefereeResult,
    SafetyReview,
)
from app.db.models import AuditLogEntry
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


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_message_records_inbound_message_and_non_phi_audit(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-003")

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-messages",
        json={"message": "  I feel nauseous after the morning dose.  "},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["treatment_id"] == str(treatment_id)
    assert payload["direction"] == "inbound"
    assert payload["sender_type"] == "patient"
    assert payload["channel"] == "whatsapp"
    assert payload["status"] == "received"
    assert payload["body"] == "I feel nauseous after the morning dose."

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "patient_conversation_message_recorded"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "message_id": payload["id"],
        "channel": "whatsapp",
    }
    assert "nauseous" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_message_rejects_blank_message(app_client: AsyncClient) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-004")

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-messages",
        json={"message": "   "},
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_message_returns_404_for_unknown_treatment(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(
        f"/treatments/{uuid4()}/patient-messages",
        json={"message": "Hello"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}


@pytest.mark.usefixtures("postgres_container")
async def test_list_conversation_messages_returns_oldest_first(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-005")
    _patch_safety_decision(monkeypatch, treatment_id, status="send")
    await app_client.post(
        f"/treatments/{treatment_id}/patient-messages",
        json={"message": "First patient message"},
    )
    await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "Second patient message",
            "assistant_draft": "Assistant draft",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )

    response = await app_client.get(f"/treatments/{treatment_id}/conversation-messages")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["body"] for item in items] == [
        "First patient message",
        "Second patient message",
        "Assistant draft",
    ]
    assert [item["direction"] for item in items] == ["inbound", "inbound", "outbound"]


@pytest.mark.usefixtures("postgres_container")
async def test_list_conversation_messages_supports_limit_and_offset(
    app_client: AsyncClient,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-006")
    for message in ["First", "Second", "Third"]:
        await app_client.post(
            f"/treatments/{treatment_id}/patient-messages",
            json={"message": message},
        )

    response = await app_client.get(
        f"/treatments/{treatment_id}/conversation-messages",
        params={"limit": 1, "offset": 1},
    )

    assert response.status_code == 200, response.text
    assert [item["body"] for item in response.json()["items"]] == ["Second"]


@pytest.mark.usefixtures("postgres_container")
async def test_list_conversation_messages_returns_404_for_unknown_treatment(
    app_client: AsyncClient,
) -> None:
    response = await app_client.get(f"/treatments/{uuid4()}/conversation-messages")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_reply_draft_generates_ready_conversation_turn(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-007")
    seen: dict[str, str] = {}
    _patch_generated_reply(monkeypatch)
    _patch_safety_decision(monkeypatch, treatment_id, status="send", seen=seen)

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "Can I take this after food?"},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["inbound_message"]["body"] == "Can I take this after food?"
    assert payload["assistant_message"]["body"] == (
        "Please follow the timing your pharmacist approved."
    )
    assert payload["assistant_message"]["status"] == "draft_ready"
    assert payload["safety_decision"]["status"] == "send"
    assert "Amoxicillin" in seen["prescription_context"]
    assert "Three Times Daily (TID)" in seen["prescription_context"]


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_reply_draft_holds_when_safety_blocks(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-008")
    _patch_generated_reply(monkeypatch)
    _patch_safety_decision(monkeypatch, treatment_id, status="hold_for_pharmacist")

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "Can I take an extra dose?"},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["assistant_message"]["status"] == "held_for_review"
    assert payload["assistant_message"]["safety_hold_reason"] == "input_guard"
    assert payload["safety_decision"]["status"] == "hold_for_pharmacist"


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_reply_draft_returns_404_for_unknown_treatment(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(
        f"/treatments/{uuid4()}/patient-reply-drafts",
        json={"patient_message": "Hello"},
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
    seen: dict[str, str] | None = None,
) -> None:
    async def fake_review_patient_draft_safety(*args: object, **kwargs: object) -> object:
        assistant_draft = str(kwargs["assistant_draft"])
        if seen is not None:
            seen["prescription_context"] = str(kwargs["prescription_context"])
        return _safety_decision(treatment_id, status=status, assistant_draft=assistant_draft)

    monkeypatch.setattr(
        "app.services.conversation_messages.review_patient_draft_safety",
        fake_review_patient_draft_safety,
    )


def _patch_generated_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_draft_patient_reply_for_treatment(*args: object, **kwargs: object) -> object:
        return PatientReplyDraft(
            message="Please follow the timing your pharmacist approved.",
            requires_pharmacist_review=False,
            escalation_reason="none",
            confidence=0.86,
        )

    monkeypatch.setattr(
        "app.api.treatments.draft_patient_reply_for_treatment",
        fake_draft_patient_reply_for_treatment,
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
