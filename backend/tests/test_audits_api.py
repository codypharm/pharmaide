"""System audit feed for the dashboard."""

import csv
from datetime import UTC, datetime
from io import StringIO
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AuditLogEntry, Patient, Treatment


@pytest.mark.usefixtures("postgres_container")
async def test_get_audits_returns_recent_entries_newest_first(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    actor_id = uuid4()
    older = AuditLogEntry(
        actor_id=None,
        event_type="analysis_started",
        resource_type="treatment",
        resource_id=uuid4(),
        payload={"medication_count": 2},
        created_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )
    newer = AuditLogEntry(
        actor_id=actor_id,
        event_type="triage_item_status_changed",
        resource_type="triage_item",
        resource_id=uuid4(),
        payload={"old_status": "open", "new_status": "acknowledged"},
        created_at=datetime(2026, 5, 15, 11, 0, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    await db_session.flush()

    response = await app_client.get(
        "/audits?limit=1",
        headers={"X-Pharmaide-User-Id": str(actor_id)},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["event_type"] for item in payload["items"]] == [
        "triage_item_status_changed"
    ]
    assert payload["items"][0] == {
        "id": str(newer.id),
        "actor_id": str(newer.actor_id),
        "event_type": "triage_item_status_changed",
        "resource_type": "triage_item",
        "resource_id": str(newer.resource_id),
        "payload": {"old_status": "open", "new_status": "acknowledged"},
        "created_at": "2026-05-15T11:00:00Z",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_get_audits_supports_offset_pagination(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    scope_id = uuid4()
    treatment = await _persist_treatment(db_session, scope_id=scope_id)
    older = AuditLogEntry(
        actor_id=None,
        event_type="analysis_started",
        resource_type="treatment",
        resource_id=treatment.id,
        payload={"medication_count": 2},
        created_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )
    newer = AuditLogEntry(
        actor_id=None,
        event_type="analysis_completed",
        resource_type="treatment",
        resource_id=treatment.id,
        payload={"analysis_id": str(uuid4())},
        created_at=datetime(2026, 5, 15, 11, 0, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    await db_session.flush()

    response = await app_client.get(
        "/audits?limit=1&offset=1",
        headers={"X-Pharmaide-User-Id": str(scope_id)},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["event_type"] for item in payload["items"]] == ["analysis_started"]


@pytest.mark.usefixtures("postgres_container")
async def test_get_audits_filters_entries_before_pagination(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    human_actor_id = uuid4()
    matching = AuditLogEntry(
        actor_id=human_actor_id,
        event_type="triage_item_status_changed",
        resource_type="triage_item",
        resource_id=uuid4(),
        payload={"old_status": "open", "new_status": "acknowledged"},
        created_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    wrong_event = AuditLogEntry(
        actor_id=human_actor_id,
        event_type="analysis_started",
        resource_type="triage_item",
        resource_id=uuid4(),
        payload={"medication_count": 2},
        created_at=datetime(2026, 5, 15, 13, 0, tzinfo=UTC),
    )
    wrong_actor = AuditLogEntry(
        actor_id=uuid4(),
        event_type="triage_item_status_changed",
        resource_type="triage_item",
        resource_id=uuid4(),
        payload={"old_status": "open", "new_status": "resolved"},
        created_at=datetime(2026, 5, 15, 14, 0, tzinfo=UTC),
    )
    db_session.add_all([matching, wrong_event, wrong_actor])
    await db_session.flush()

    response = await app_client.get(
        "/audits",
        params={
            "event_type": "triage_item_status_changed",
            "resource_type": "triage_item",
            "actor_id": str(human_actor_id),
            "limit": 1,
        },
        headers={"X-Pharmaide-User-Id": str(human_actor_id)},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [str(matching.id)]


@pytest.mark.usefixtures("postgres_container")
async def test_export_audits_csv_uses_backend_filters(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    actor_id = uuid4()
    matching = AuditLogEntry(
        actor_id=actor_id,
        event_type="triage_item_status_changed",
        resource_type="triage_item",
        resource_id=uuid4(),
        payload={"old_status": "open", "new_status": "resolved"},
        created_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    other = AuditLogEntry(
        actor_id=None,
        event_type="analysis_started",
        resource_type="treatment",
        resource_id=uuid4(),
        payload={"medication_count": 2},
        created_at=datetime(2026, 5, 15, 13, 0, tzinfo=UTC),
    )
    db_session.add_all([matching, other])
    await db_session.flush()

    response = await app_client.get(
        "/audits/export.csv",
        params={
            "event_type": "triage_item_status_changed",
            "resource_type": "triage_item",
            "actor_id": str(actor_id),
        },
        headers={"X-Pharmaide-User-Id": str(actor_id)},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "pharmaide-audit-trail.csv" in response.headers["content-disposition"]
    rows = list(csv.DictReader(StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["id"] == str(matching.id)
    assert rows[0]["event_type"] == "triage_item_status_changed"
    assert rows[0]["resource_type"] == "triage_item"
    assert rows[0]["actor_id"] == str(actor_id)
    assert "analysis_started" not in response.text


@pytest.mark.usefixtures("postgres_container")
async def test_get_audits_returns_only_current_actor_scope(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    actor_a = uuid4()
    actor_b = uuid4()
    treatment_a = await _persist_treatment(db_session, scope_id=actor_a)
    treatment_b = await _persist_treatment(db_session, scope_id=actor_b)
    visible = AuditLogEntry(
        actor_id=None,
        event_type="analysis_started",
        resource_type="treatment",
        resource_id=treatment_b.id,
        payload={"treatment_id": str(treatment_b.id)},
        created_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    hidden = AuditLogEntry(
        actor_id=None,
        event_type="analysis_started",
        resource_type="treatment",
        resource_id=treatment_a.id,
        payload={"treatment_id": str(treatment_a.id)},
        created_at=datetime(2026, 5, 15, 13, 0, tzinfo=UTC),
    )
    db_session.add_all([visible, hidden])
    await db_session.flush()

    response = await app_client.get(
        "/audits",
        headers={"X-Pharmaide-User-Id": str(actor_b)},
    )

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [str(visible.id)]


@pytest.mark.usefixtures("postgres_container")
async def test_export_audits_csv_returns_only_current_actor_scope(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    actor_a = uuid4()
    actor_b = uuid4()
    treatment_a = await _persist_treatment(db_session, scope_id=actor_a)
    treatment_b = await _persist_treatment(db_session, scope_id=actor_b)
    visible = AuditLogEntry(
        actor_id=None,
        event_type="analysis_completed",
        resource_type="treatment",
        resource_id=treatment_b.id,
        payload={"treatment_id": str(treatment_b.id)},
        created_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    hidden = AuditLogEntry(
        actor_id=None,
        event_type="analysis_completed",
        resource_type="treatment",
        resource_id=treatment_a.id,
        payload={"treatment_id": str(treatment_a.id)},
        created_at=datetime(2026, 5, 15, 13, 0, tzinfo=UTC),
    )
    db_session.add_all([visible, hidden])
    await db_session.flush()

    response = await app_client.get(
        "/audits/export.csv",
        headers={"X-Pharmaide-User-Id": str(actor_b)},
    )

    assert response.status_code == 200, response.text
    rows = list(csv.DictReader(StringIO(response.text)))
    assert [row["id"] for row in rows] == [str(visible.id)]
    assert str(hidden.id) not in response.text


@pytest.mark.usefixtures("postgres_container")
async def test_get_audits_requires_bearer_token_in_gcip_mode(
    test_app: FastAPI,
) -> None:
    test_app.state.settings = Settings(
        _env_file=None,
        auth_mode="gcip",
        gcip_project_id="pharmaide-test",
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/audits")

    assert response.status_code == 401
    assert response.json()["detail"] == {"error": "auth_token_required"}


async def _persist_treatment(session: AsyncSession, *, scope_id: UUID) -> Treatment:
    patient = Patient(
        name=f"Audit Patient {uuid4()}",
        dob=datetime(1955, 10, 12, tzinfo=UTC).date(),
        mrn=f"AUDIT-{uuid4()}",
        phone="+18005559999",
    )
    treatment = Treatment(
        patient=patient,
        scope_id=scope_id,
        clinical_objective="Audit scoping",
    )
    session.add(treatment)
    await session.flush()
    return treatment
