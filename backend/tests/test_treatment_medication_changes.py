"""Existing-treatment medication change commands."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLogEntry,
    ConversationMessage,
    Medication,
    Treatment,
    TreatmentAnalysis,
)
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep command tests focused on treatment mutation, not analysis workers."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_add_medication_pauses_cycle_notifies_patient_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-ADD")
    analysis = TreatmentAnalysis(
        treatment_id=treatment_id,
        status="completed",
        result={"clinical_summary": "Ready for monitoring."},
    )
    queued_reminder = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="queued",
        body="Reminder: it is time for Lisinopril.",
    )
    db_session.add_all([analysis, queued_reminder])
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    treatment.status = "active"
    treatment.automation_mode = "active"
    await db_session.flush()

    response = await app_client.post(
        f"/treatments/{treatment_id}/medications",
        json={
            "name": "Amlodipine",
            "dosage": "5 mg",
            "frequency": "Once Daily (QD)",
            "duration": "30 days",
            "objective": None,
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    medication_id = UUID(payload["id"])
    assert payload["name"] == "Amlodipine"
    assert payload["ordinal"] == 1
    assert payload["discontinued_at"] is None

    medication = await db_session.get(Medication, medication_id)
    assert medication is not None
    await db_session.refresh(treatment)
    await db_session.refresh(analysis)
    await db_session.refresh(queued_reminder)
    assert treatment.status == "pending"
    assert treatment.automation_mode == "paused"
    assert analysis.status == "superseded"
    assert queued_reminder.status == "cancelled"

    patient_update = await _patient_update_message(db_session, treatment_id)
    assert patient_update is not None
    assert patient_update.status == "queued"
    assert patient_update.body == (
        "Your pharmacist has updated your treatment plan. Amlodipine has been added. "
        "Please follow your pharmacist's direct instructions for this medication. "
        "Reminders are paused while your pharmacist reviews the updated plan."
    )

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "treatment_medication_added",
            AuditLogEntry.resource_id == medication_id,
        )
    )
    assert audit is not None
    assert audit.resource_type == "medication"
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "medication_id": str(medication_id),
        "old_treatment_status": "active",
        "new_treatment_status": "pending",
        "old_automation_mode": "active",
        "new_automation_mode": "paused",
        "superseded_analysis_count": 2,
        "active_medication_count": 2,
        "cancelled_queued_message_count": 1,
        "patient_notification_message_id": str(patient_update.id),
    }
    assert "amlodipine" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_add_medication_before_cycle_start_does_not_notify_patient(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-ADD-PENDING")
    db_session.add(
        TreatmentAnalysis(
            treatment_id=treatment_id,
            status="completed",
            result={"clinical_summary": "Ready for monitoring."},
        )
    )
    await db_session.flush()

    response = await app_client.post(
        f"/treatments/{treatment_id}/medications",
        json={
            "name": "Amlodipine",
            "dosage": "5 mg",
            "frequency": "Once Daily (QD)",
            "duration": "30 days",
            "objective": None,
        },
    )

    assert response.status_code == 201, response.text
    medication_id = UUID(response.json()["id"])
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.status == "pending"
    assert treatment.automation_mode == "paused"
    assert await _patient_update_message(db_session, treatment_id) is None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "treatment_medication_added",
            AuditLogEntry.resource_id == medication_id,
        )
    )
    assert audit is not None
    assert audit.payload["patient_notification_message_id"] is None


@pytest.mark.usefixtures("postgres_container")
async def test_edit_active_medication_pauses_cycle_notifies_patient_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-EDIT")
    medication = await _first_medication(db_session, treatment_id)
    analysis = TreatmentAnalysis(
        treatment_id=treatment_id,
        status="completed",
        result={"clinical_summary": "Ready for monitoring."},
    )
    queued_reminder = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="queued",
        body="Reminder: it is time for Lisinopril.",
    )
    db_session.add_all([analysis, queued_reminder])
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    treatment.status = "active"
    treatment.automation_mode = "active"
    await db_session.flush()

    response = await app_client.post(
        f"/treatments/{treatment_id}/medications/{medication.id}/edit",
        json={
            "name": "Lisinopril",
            "dosage": "20 mg",
            "frequency": "Twice Daily (BID)",
            "duration": "14 days",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(medication.id)
    assert payload["dosage"] == "20 mg"
    assert payload["frequency"] == "Twice Daily (BID)"
    assert payload["duration"] == "14 days"

    await db_session.refresh(medication)
    await db_session.refresh(treatment)
    await db_session.refresh(analysis)
    await db_session.refresh(queued_reminder)
    assert medication.dosage == "20 mg"
    assert medication.frequency == "Twice Daily (BID)"
    assert medication.duration == "14 days"
    assert treatment.status == "pending"
    assert treatment.automation_mode == "paused"
    assert analysis.status == "superseded"
    assert queued_reminder.status == "cancelled"

    patient_update = await _patient_update_message(db_session, treatment_id)
    assert patient_update is not None
    assert patient_update.status == "queued"
    assert patient_update.body == (
        "Your pharmacist has updated your treatment plan. "
        "One medication instruction was changed. "
        "Please follow your pharmacist's latest direct instructions. "
        "Reminders are paused while your pharmacist reviews the updated plan."
    )

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "treatment_medication_edited",
            AuditLogEntry.resource_id == medication.id,
        )
    )
    assert audit is not None
    assert audit.resource_type == "medication"
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "medication_id": str(medication.id),
        "old_treatment_status": "active",
        "new_treatment_status": "pending",
        "old_automation_mode": "active",
        "new_automation_mode": "paused",
        "superseded_analysis_count": 2,
        "active_medication_count": 1,
        "cancelled_queued_message_count": 1,
        "patient_notification_message_id": str(patient_update.id),
        "changed_fields": ["dosage", "duration", "frequency"],
    }
    assert "20 mg" not in str(audit.payload).lower()
    assert "twice daily" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_discontinue_one_medication_pauses_cycle_notifies_patient_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-001", medication_count=2)
    medication = await _first_medication(db_session, treatment_id)
    analysis = TreatmentAnalysis(
        treatment_id=treatment_id,
        status="completed",
        result={"clinical_summary": "Ready for monitoring."},
    )
    db_session.add(analysis)
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    treatment.status = "active"
    treatment.automation_mode = "active"
    await db_session.flush()

    response = await app_client.post(
        f"/treatments/{treatment_id}/medications/{medication.id}/discontinue"
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(medication.id)
    assert payload["discontinued_at"] is not None

    await db_session.refresh(medication)
    await db_session.refresh(treatment)
    await db_session.refresh(analysis)
    assert medication.discontinued_at is not None
    assert treatment.status == "pending"
    assert treatment.automation_mode == "paused"
    assert analysis.status == "superseded"

    patient_update = await _patient_update_message(db_session, treatment_id)
    assert patient_update is not None
    assert patient_update.status == "queued"
    assert patient_update.body == (
        "Your pharmacist has updated your treatment plan. Please stop taking Lisinopril "
        "unless your pharmacist has told you otherwise. Reminders are paused while your "
        "pharmacist reviews the updated plan."
    )

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "treatment_medication_discontinued",
            AuditLogEntry.resource_id == medication.id,
        )
    )
    assert audit is not None
    assert audit.resource_type == "medication"
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "medication_id": str(medication.id),
        "old_treatment_status": "active",
        "new_treatment_status": "pending",
        "old_automation_mode": "active",
        "new_automation_mode": "paused",
        "superseded_analysis_count": 2,
        "active_medication_count": 1,
        "cancelled_queued_message_count": 0,
        "patient_notification_message_id": str(patient_update.id),
        "already_discontinued": False,
    }
    assert "lisinopril" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_discontinue_pending_medication_does_not_notify_patient(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(
        app_client,
        mrn="MED-CHANGE-PENDING-DISCONTINUE",
        medication_count=2,
    )
    medication = await _first_medication(db_session, treatment_id)
    analysis = TreatmentAnalysis(
        treatment_id=treatment_id,
        status="completed",
        result={"clinical_summary": "Ready for monitoring."},
    )
    db_session.add(analysis)
    await db_session.flush()

    response = await app_client.post(
        f"/treatments/{treatment_id}/medications/{medication.id}/discontinue"
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(medication)
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    await db_session.refresh(analysis)
    assert medication.discontinued_at is not None
    assert treatment.status == "pending"
    assert treatment.automation_mode == "paused"
    assert analysis.status == "superseded"
    assert await _patient_update_message(db_session, treatment_id) is None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "treatment_medication_discontinued",
            AuditLogEntry.resource_id == medication.id,
        )
    )
    assert audit is not None
    assert audit.payload["old_treatment_status"] == "pending"
    assert audit.payload["new_treatment_status"] == "pending"
    assert audit.payload["patient_notification_message_id"] is None


@pytest.mark.usefixtures("postgres_container")
async def test_discontinue_last_medication_terminates_cycle_and_cancels_queued_reminders(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-LAST")
    medication = await _first_medication(db_session, treatment_id)
    queued_reminder = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="queued",
        body="Reminder: it is time for Lisinopril.",
    )
    db_session.add(queued_reminder)
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    treatment.status = "active"
    treatment.automation_mode = "active"
    await db_session.flush()

    response = await app_client.post(
        f"/treatments/{treatment_id}/medications/{medication.id}/discontinue"
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(treatment)
    await db_session.refresh(queued_reminder)
    assert treatment.status == "terminated"
    assert treatment.automation_mode == "paused"
    assert queued_reminder.status == "cancelled"

    patient_update = await _patient_update_message(db_session, treatment_id)
    assert patient_update is not None
    assert patient_update.status == "queued"
    assert patient_update.body == (
        "Your pharmacist has updated your treatment plan. There are no active medications "
        "left for this monitoring cycle. Please follow your pharmacist's latest instructions."
    )

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "treatment_medication_discontinued",
            AuditLogEntry.resource_id == medication.id,
        )
    )
    assert audit is not None
    assert audit.payload["new_treatment_status"] == "terminated"
    assert audit.payload["active_medication_count"] == 0
    assert audit.payload["cancelled_queued_message_count"] == 1
    assert audit.payload["patient_notification_message_id"] == str(patient_update.id)


@pytest.mark.usefixtures("postgres_container")
async def test_discontinue_medication_returns_404_for_wrong_treatment(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-002")
    other_treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-003")
    medication = await _first_medication(db_session, treatment_id)

    response = await app_client.post(
        f"/treatments/{other_treatment_id}/medications/{medication.id}/discontinue"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "medication_not_found"}}


async def _create_treatment(
    app_client: AsyncClient,
    *,
    mrn: str,
    medication_count: int = 1,
) -> UUID:
    medications = [
        {
            "name": "Lisinopril",
            "dosage": "10 mg",
            "frequency": "Once Daily (QD)",
            "duration": "30 days",
            "objective": None,
        }
    ]
    if medication_count > 1:
        medications.append(
            {
                "name": "Amlodipine",
                "dosage": "5 mg",
                "frequency": "Once Daily (QD)",
                "duration": "30 days",
                "objective": None,
            }
        )

    response = await app_client.post(
        "/treatments",
        json={
            "patient": {
                "name": "Eleanor Vance",
                "dob": "1955-10-12",
                "mrn": mrn,
                "phone": "+18005551212",
            },
            "treatment": {
                "clinical_objective": "Monitor adherence",
                "treatment_start_at": "2026-05-16T08:00:00Z",
            },
            "medications": medications,
            "ingestion_method": "structured",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["treatment_id"])


async def _first_medication(db_session: AsyncSession, treatment_id: UUID) -> Medication:
    medication = await db_session.scalar(
        select(Medication).where(Medication.treatment_id == treatment_id)
    )
    assert medication is not None
    return medication


async def _patient_update_message(
    db_session: AsyncSession,
    treatment_id: UUID,
) -> ConversationMessage | None:
    return await db_session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.treatment_id == treatment_id,
            ConversationMessage.direction == "outbound",
            ConversationMessage.sender_type == "assistant",
            ConversationMessage.channel == "whatsapp",
            ConversationMessage.status == "queued",
            ConversationMessage.body.like("Your pharmacist has updated your treatment plan.%"),
        )
    )
