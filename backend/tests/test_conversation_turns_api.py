"""HTTP seam for provider-neutral patient conversation turns."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.patient_reply import PatientReplyDraft
from app.agents.safety_schemas import (
    GuardResult,
    PatientDraftSafetyDecision,
    RefereeResult,
    SafetyReview,
)
from app.db.models import (
    AdherenceEvent,
    AuditLogEntry,
    ConversationMessage,
    Medication,
    PatientCheckIn,
    Treatment,
    TriageItem,
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
async def test_held_conversation_turn_creates_open_triage_item(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-009")
    _patch_safety_decision(monkeypatch, treatment_id, status="hold_for_pharmacist")

    turn_response = await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "Can I take an extra dose?",
            "assistant_draft": "This draft must be reviewed.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )
    response = await app_client.get("/triage/items")

    assert turn_response.status_code == 201, turn_response.text
    turn = turn_response.json()
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["treatment_id"] == str(treatment_id)
    assert items[0]["conversation_message_id"] == turn["assistant_message"]["id"]
    assert items[0]["reason"] == "input_guard"
    assert items[0]["status"] == "open"

    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.chat_response_mode == "pharmacist_takeover"
    assert treatment.automation_mode == "active"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "treatment_chat_response_mode_changed"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "old_chat_response_mode": "ai_active",
        "new_chat_response_mode": "pharmacist_takeover",
        "automation_mode": "active",
        "trigger": "triage_item_opened",
        "triage_item_id": items[0]["id"],
    }


@pytest.mark.usefixtures("postgres_container")
async def test_allowed_conversation_turn_does_not_create_triage_item(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-010")
    _patch_safety_decision(monkeypatch, treatment_id, status="send")

    turn_response = await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "Can I take this after food?",
            "assistant_draft": "Please follow the timing your pharmacist approved.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )
    response = await app_client.get("/triage/items")

    assert turn_response.status_code == 201, turn_response.text
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


@pytest.mark.usefixtures("postgres_container")
async def test_list_triage_items_returns_newest_first(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_treatment_id = await _create_treatment(app_client, "CONV-API-011")
    second_treatment_id = await _create_treatment(app_client, "CONV-API-012")
    _patch_safety_decision(monkeypatch, first_treatment_id, status="hold_for_pharmacist")
    await app_client.post(
        f"/treatments/{first_treatment_id}/conversation-turns",
        json={
            "patient_message": "First blocked message",
            "assistant_draft": "First blocked draft.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )
    _patch_safety_decision(monkeypatch, second_treatment_id, status="hold_for_pharmacist")
    await app_client.post(
        f"/treatments/{second_treatment_id}/conversation-turns",
        json={
            "patient_message": "Second blocked message",
            "assistant_draft": "Second blocked draft.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )

    response = await app_client.get("/triage/items")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["treatment_id"] for item in items] == [
        str(second_treatment_id),
        str(first_treatment_id),
    ]


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
async def test_post_pharmacist_message_records_queued_outbound_message_and_non_phi_audit(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-014")

    response = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "  Please continue the current dose and call us if dizziness worsens.  "},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["treatment_id"] == str(treatment_id)
    assert payload["direction"] == "outbound"
    assert payload["sender_type"] == "pharmacist"
    assert payload["channel"] == "whatsapp"
    assert payload["status"] == "queued"
    assert payload["body"] == "Please continue the current dose and call us if dizziness worsens."

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "pharmacist_conversation_message_queued"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "message_id": payload["id"],
        "channel": "whatsapp",
        "status": "queued",
    }
    assert "dizziness" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_post_pharmacist_message_rejects_blank_message(app_client: AsyncClient) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-015")

    response = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "   "},
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("postgres_container")
async def test_post_pharmacist_message_returns_404_for_unknown_treatment(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(
        f"/treatments/{uuid4()}/pharmacist-messages",
        json={"message": "Hello"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_retry_delivery_requeues_failed_message_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-018")
    created = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "Please call the pharmacy today."},
    )
    assert created.status_code == 201, created.text
    message_id = UUID(created.json()["id"])
    message = await db_session.get(ConversationMessage, message_id)
    assert message is not None
    message.status = "failed"
    message.external_message_id = "whatsapp-failed-1"
    await db_session.flush()

    response = await app_client.post(
        f"/treatments/{treatment_id}/conversation-messages/{message_id}/retry-delivery"
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(message_id)
    assert payload["status"] == "queued"
    assert payload["external_message_id"] is None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_retried"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "message_id": str(message_id),
        "old_status": "failed",
        "new_status": "queued",
        "channel": "whatsapp",
    }
    assert "pharmacy" not in str(audit.payload).lower()


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
async def test_post_patient_reply_draft_records_taken_reply_as_adherence_event(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-019")
    medication_id = await _first_medication_id(db_session, treatment_id)
    await _seed_monitoring_reminder(db_session, treatment_id, medication_id)
    _patch_generated_reply(monkeypatch)
    _patch_safety_decision(monkeypatch, treatment_id, status="send")

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "Taken"},
    )

    assert response.status_code == 201, response.text
    event = await db_session.scalar(select(AdherenceEvent))
    assert event is not None
    assert event.treatment_id == treatment_id
    assert event.medication_id == medication_id
    assert event.status == "taken"
    assert event.source == "patient"
    assert event.occurred_at is not None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "patient_reply_adherence_captured"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "inbound_message_id": response.json()["inbound_message"]["id"],
        "medication_id": str(medication_id),
        "status": "taken",
        "reminder_key": f"{medication_id}:PT0S:morning dose",
        "reminder_key_present": True,
    }
    assert "amoxicillin" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_reply_draft_does_not_duplicate_adherence_for_same_reminder(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-021")
    medication_id = await _first_medication_id(db_session, treatment_id)
    await _seed_monitoring_reminder(db_session, treatment_id, medication_id)
    _patch_generated_reply(monkeypatch)
    _patch_safety_decision(monkeypatch, treatment_id, status="send")

    first = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "Taken"},
    )
    second = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "Taken"},
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    event_count = await db_session.scalar(select(func.count()).select_from(AdherenceEvent))
    capture_audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLogEntry)
        .where(AuditLogEntry.event_type == "patient_reply_adherence_captured")
    )
    assert event_count == 1
    assert capture_audit_count == 1


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_reply_draft_records_side_effect_as_check_in_and_triage(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-020")
    _patch_generated_reply(monkeypatch)
    _patch_safety_decision(monkeypatch, treatment_id, status="send")

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "I vomited after taking it"},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["assistant_message"]["status"] == "held_for_review"
    assert payload["assistant_message"]["safety_hold_reason"] == "draft_requires_review"

    check_in = await db_session.scalar(select(PatientCheckIn))
    assert check_in is not None
    assert check_in.treatment_id == treatment_id
    assert check_in.report_type == "side_effect"
    assert check_in.source == "patient"
    assert check_in.message == "I vomited after taking it"
    assert check_in.observed_at is not None

    triage = await db_session.scalar(select(TriageItem))
    assert triage is not None
    assert triage.treatment_id == treatment_id
    assert triage.conversation_message_id == UUID(payload["assistant_message"]["id"])
    assert triage.reason == "side_effect"
    assert triage.status == "open"


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

    triage = await app_client.get("/triage/items")
    assert triage.status_code == 200, triage.text
    item = triage.json()["items"][0]
    assert item["conversation_message_id"] == payload["assistant_message"]["id"]
    assert item["status"] == "open"


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_reply_draft_opens_triage_when_draft_requires_review(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-018")
    _patch_generated_reply(
        monkeypatch,
        requires_pharmacist_review=True,
        escalation_reason="dose_change_request",
    )
    _patch_safety_decision(monkeypatch, treatment_id, status="send")

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "Can I stop this medicine?"},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["assistant_message"]["status"] == "held_for_review"
    assert payload["assistant_message"]["safety_hold_reason"] == "draft_requires_review"
    assert payload["safety_decision"]["status"] == "hold_for_pharmacist"
    assert payload["safety_decision"]["hold_reason"] == "draft_requires_review"

    triage = await app_client.get("/triage/items")
    assert triage.status_code == 200, triage.text
    item = triage.json()["items"][0]
    assert item["conversation_message_id"] == payload["assistant_message"]["id"]
    assert item["reason"] == "dose_change_request"
    assert item["status"] == "open"


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_reply_draft_uses_holding_response_during_pharmacist_takeover(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-013")
    _patch_safety_decision(monkeypatch, treatment_id, status="hold_for_pharmacist")
    held = await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "Can I take an extra dose?",
            "assistant_draft": "This draft must be reviewed.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )
    assert held.status_code == 201, held.text

    async def fail_if_llm_draft_runs(*args: object, **kwargs: object) -> object:
        raise AssertionError("takeover holding replies must not call the patient-reply LLM")

    monkeypatch.setattr(
        "app.services.patient_reply_drafts.draft_patient_reply",
        fail_if_llm_draft_runs,
    )
    _patch_safety_decision(monkeypatch, treatment_id, status="send")

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "Any update on my question?"},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["inbound_message"]["body"] == "Any update on my question?"
    assert payload["assistant_message"]["status"] == "draft_ready"
    assert "pharmacist is reviewing" in payload["assistant_message"]["body"]
    assert payload["safety_decision"]["status"] == "send"


@pytest.mark.usefixtures("postgres_container")
async def test_post_patient_reply_draft_fast_paths_holding_response_during_takeover(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-017")
    _patch_safety_decision(monkeypatch, treatment_id, status="hold_for_pharmacist")
    held = await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "Can I take an extra dose?",
            "assistant_draft": "This draft must be reviewed.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )
    assert held.status_code == 201, held.text

    async def fail_if_safety_review_runs(*args: object, **kwargs: object) -> object:
        raise AssertionError("takeover holding replies must not call external safety review")

    monkeypatch.setattr(
        "app.services.conversation_messages.review_patient_draft_safety",
        fail_if_safety_review_runs,
    )

    response = await app_client.post(
        f"/treatments/{treatment_id}/patient-reply-drafts",
        json={"patient_message": "Any update?"},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["inbound_message"]["body"] == "Any update?"
    assert payload["assistant_message"]["status"] == "draft_ready"
    assert "pharmacist is reviewing" in payload["assistant_message"]["body"]
    assert payload["safety_decision"]["status"] == "send"


@pytest.mark.usefixtures("postgres_container")
async def test_post_chat_response_mode_resumes_ai_replies_and_audits_change(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-016")
    _patch_safety_decision(monkeypatch, treatment_id, status="hold_for_pharmacist")
    held = await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "Can I take an extra dose?",
            "assistant_draft": "This draft must be reviewed.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )
    assert held.status_code == 201, held.text

    response = await app_client.post(
        f"/treatments/{treatment_id}/chat-response-mode",
        json={"chat_response_mode": "ai_active"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(treatment_id)
    assert payload["chat_response_mode"] == "ai_active"
    assert payload["automation_mode"] == "active"

    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.chat_response_mode == "ai_active"

    audit = await db_session.scalar(
        select(AuditLogEntry)
        .where(AuditLogEntry.event_type == "treatment_chat_response_mode_changed")
        .order_by(AuditLogEntry.created_at.desc())
    )
    assert audit is not None
    assert audit.payload == {
        "old_chat_response_mode": "pharmacist_takeover",
        "new_chat_response_mode": "ai_active",
        "automation_mode": "active",
        "trigger": "manual_pharmacist_control",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_clinical_objective_updates_objective_and_audits_metadata(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "CONV-API-017")

    response = await app_client.post(
        f"/treatments/{treatment_id}/clinical-objective",
        json={"clinical_objective": "Monitor nausea and recovery"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(treatment_id)
    assert payload["clinical_objective"] == "Monitor nausea and recovery"

    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.clinical_objective == "Monitor nausea and recovery"

    audit = await db_session.scalar(
        select(AuditLogEntry)
        .where(AuditLogEntry.event_type == "treatment_clinical_objective_changed")
        .order_by(AuditLogEntry.created_at.desc())
    )
    assert audit is not None
    assert audit.payload == {
        "old_clinical_objective_present": True,
        "new_clinical_objective_present": True,
    }
    assert "nausea" not in str(audit.payload).lower()


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


async def _first_medication_id(db_session: AsyncSession, treatment_id: UUID) -> UUID:
    medication_id = await db_session.scalar(
        select(Medication.id).where(Medication.treatment_id == treatment_id)
    )
    assert medication_id is not None
    return medication_id


async def _seed_monitoring_reminder(
    db_session: AsyncSession,
    treatment_id: UUID,
    medication_id: UUID,
) -> None:
    reminder = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="sent",
        body="Reminder: it is time for Amoxicillin (morning dose).",
    )
    db_session.add(reminder)
    await db_session.flush()
    db_session.add(
        AuditLogEntry(
            event_type="monitoring_message_queued",
            resource_type="conversation_message",
            resource_id=reminder.id,
            payload={
                "treatment_id": str(treatment_id),
                "message_id": str(reminder.id),
                "reminder_key": f"{medication_id}:PT0S:morning dose",
                "scheduled_for_present": True,
                "channel": "whatsapp",
                "status": "queued",
            },
        )
    )
    await db_session.flush()


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


def _patch_generated_reply(
    monkeypatch: pytest.MonkeyPatch,
    *,
    requires_pharmacist_review: bool = False,
    escalation_reason: str = "none",
) -> None:
    async def fake_draft_patient_reply_for_treatment(*args: object, **kwargs: object) -> object:
        return PatientReplyDraft(
            message="Please follow the timing your pharmacist approved.",
            requires_pharmacist_review=requires_pharmacist_review,
            escalation_reason=escalation_reason,
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
