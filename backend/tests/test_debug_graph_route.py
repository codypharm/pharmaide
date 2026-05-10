from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


def _settings(tmp_path: Path, *, enabled: bool) -> Settings:
    return Settings(
        _env_file=None,
        checkpoint_db_path=str(tmp_path / "debug.db"),
        debug_routes_enabled=enabled,
        log_mode="json",
    )


async def test_debug_route_is_404_when_flag_disabled(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, enabled=False))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/debug/graph", json={"thread_id": "t1"})

    assert response.status_code == 404


async def test_debug_route_increments_when_enabled(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, enabled=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/debug/graph", json={"thread_id": "t1"})
        second = await client.post("/debug/graph", json={"thread_id": "t1"})
        other = await client.post("/debug/graph", json={"thread_id": "t2"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert other.status_code == 200
    assert first.json() == {"turn": 1}
    assert second.json() == {"turn": 2}
    assert other.json() == {"turn": 1}


@pytest.mark.parametrize("bad_body", [{}, {"thread_id": ""}, {"wrong_key": "t1"}])
async def test_debug_route_rejects_invalid_body(tmp_path: Path, bad_body: dict[str, str]) -> None:
    app = create_app(_settings(tmp_path, enabled=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/debug/graph", json=bad_body)

    assert response.status_code == 422
