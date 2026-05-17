"""System audit feed for the dashboard."""

import csv
from datetime import UTC, datetime
from io import StringIO
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry


@pytest.mark.usefixtures("postgres_container")
async def test_get_audits_returns_recent_entries_newest_first(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    older = AuditLogEntry(
        actor_id=None,
        event_type="analysis_started",
        resource_type="treatment",
        resource_id=uuid4(),
        payload={"medication_count": 2},
        created_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )
    newer = AuditLogEntry(
        actor_id=uuid4(),
        event_type="triage_item_status_changed",
        resource_type="triage_item",
        resource_id=uuid4(),
        payload={"old_status": "open", "new_status": "acknowledged"},
        created_at=datetime(2026, 5, 15, 11, 0, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    await db_session.flush()

    response = await app_client.get("/audits?limit=1")

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
    older = AuditLogEntry(
        actor_id=None,
        event_type="analysis_started",
        resource_type="treatment",
        resource_id=uuid4(),
        payload={"medication_count": 2},
        created_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
    )
    newer = AuditLogEntry(
        actor_id=None,
        event_type="analysis_completed",
        resource_type="treatment",
        resource_id=uuid4(),
        payload={"analysis_id": str(uuid4())},
        created_at=datetime(2026, 5, 15, 11, 0, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    await db_session.flush()

    response = await app_client.get("/audits?limit=1&offset=1")

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
