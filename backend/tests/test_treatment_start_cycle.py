"""Treatment start-cycle lifecycle transition."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, Treatment, TreatmentAnalysis
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep lifecycle tests focused on treatment state, not analysis workers."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_post_start_cycle_marks_pending_treatment_active_and_audits(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    create = await app_client.post("/treatments", json=_treatment_body("START-CYCLE-001"))
    assert create.status_code == 201, create.text
    treatment_id = UUID(create.json()["treatment_id"])
    db_session.add(
        TreatmentAnalysis(
            treatment_id=treatment_id,
            status="completed",
            result={"clinical_summary": "Reviewed and ready for monitoring."},
        )
    )
    await db_session.flush()

    response = await app_client.post(f"/treatments/{treatment_id}/start-cycle")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(treatment_id)
    assert payload["status"] == "active"

    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.status == "active"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == treatment_id,
            AuditLogEntry.event_type == "treatment_cycle_started",
        )
    )
    assert audit is not None
    assert audit.resource_type == "treatment"
    assert UUID(audit.payload["analysis_id"])
    assert audit.payload == {
        "old_status": "pending",
        "new_status": "active",
        "analysis_id": audit.payload["analysis_id"],
        "onboarding_delivery": "not_configured",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_post_start_cycle_rejects_treatment_without_completed_analysis(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    create = await app_client.post("/treatments", json=_treatment_body("START-CYCLE-002"))
    assert create.status_code == 201, create.text
    treatment_id = UUID(create.json()["treatment_id"])

    response = await app_client.post(f"/treatments/{treatment_id}/start-cycle")

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "analysis_not_completed"}}
    detail = await app_client.get(f"/treatments/{treatment_id}")
    assert detail.status_code == 200
    assert detail.json()["treatment"]["status"] == "pending"


@pytest.mark.usefixtures("postgres_container")
async def test_post_start_cycle_rejects_completed_analysis_without_result(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    create = await app_client.post("/treatments", json=_treatment_body("START-CYCLE-003"))
    assert create.status_code == 201, create.text
    treatment_id = UUID(create.json()["treatment_id"])
    db_session.add(TreatmentAnalysis(treatment_id=treatment_id, status="completed", result=None))
    await db_session.flush()

    response = await app_client.post(f"/treatments/{treatment_id}/start-cycle")

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "analysis_not_completed"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_start_cycle_returns_404_for_missing_treatment(app_client: AsyncClient) -> None:
    response = await app_client.post(f"/treatments/{uuid4()}/start-cycle")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_archive_completed_treatment_sets_archived_at_and_audits(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    create = await app_client.post("/treatments", json=_treatment_body("ARCHIVE-001"))
    assert create.status_code == 201, create.text
    treatment_id = UUID(create.json()["treatment_id"])
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    treatment.status = "completed"
    await db_session.flush()

    response = await app_client.post(f"/treatments/{treatment_id}/archive")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(treatment_id)
    assert payload["status"] == "completed"
    assert payload["archived_at"] is not None

    await db_session.refresh(treatment)
    assert treatment.archived_at is not None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == treatment_id,
            AuditLogEntry.event_type == "treatment_archived",
        )
    )
    assert audit is not None
    assert audit.resource_type == "treatment"
    assert audit.payload == {
        "status": "completed",
        "already_archived": False,
    }


@pytest.mark.usefixtures("postgres_container")
async def test_post_archive_returns_existing_timestamp_when_already_archived(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    create = await app_client.post("/treatments", json=_treatment_body("ARCHIVE-002"))
    assert create.status_code == 201, create.text
    treatment_id = UUID(create.json()["treatment_id"])
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    treatment.status = "completed"
    await db_session.flush()

    first = await app_client.post(f"/treatments/{treatment_id}/archive")
    assert first.status_code == 200, first.text
    first_archived_at = first.json()["archived_at"]
    second = await app_client.post(f"/treatments/{treatment_id}/archive")

    assert second.status_code == 200, second.text
    assert second.json()["archived_at"] == first_archived_at
    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLogEntry)
        .where(
            AuditLogEntry.resource_id == treatment_id,
            AuditLogEntry.event_type == "treatment_archived",
        )
    )
    assert audit_count == 1


@pytest.mark.usefixtures("postgres_container")
async def test_post_archive_rejects_non_completed_treatment(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    create = await app_client.post("/treatments", json=_treatment_body("ARCHIVE-003"))
    assert create.status_code == 201, create.text
    treatment_id = UUID(create.json()["treatment_id"])

    response = await app_client.post(f"/treatments/{treatment_id}/archive")

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "treatment_not_completed"}}
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == treatment_id,
            AuditLogEntry.event_type == "treatment_archived",
        )
    )
    assert audit is None


@pytest.mark.usefixtures("postgres_container")
async def test_post_archive_returns_404_for_missing_treatment(app_client: AsyncClient) -> None:
    response = await app_client.post(f"/treatments/{uuid4()}/archive")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}


def _treatment_body(mrn: str) -> dict[str, object]:
    return {
        "patient": {
            "name": "Eleanor Vance",
            "dob": "1955-10-12",
            "mrn": mrn,
            "phone": "+18005551212",
        },
        "treatment": {
            "clinical_objective": "Monitor adherence",
            "treatment_start_at": "2026-05-16T08:30:00Z",
        },
        "medications": [
            {
                "name": "Lisinopril",
                "dosage": "10 mg",
                "frequency": "Once Daily (QD)",
                "duration": "30 days",
                "objective": None,
            }
        ],
        "ingestion_method": "structured",
    }
