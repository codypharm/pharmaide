from httpx import ASGITransport, AsyncClient

from app.db.engine import get_session
from app.main import app


async def test_health_endpoint_returns_ok_envelope() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


async def test_readiness_endpoint_checks_database(app_client: AsyncClient) -> None:
    response = await app_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "version": "0.1.0",
        "checks": {"database": "ok"},
    }


async def test_readiness_endpoint_returns_503_when_database_check_fails() -> None:
    class FailingSession:
        async def execute(self, _statement: object) -> None:
            raise RuntimeError("database unavailable")

    async def failing_session_override() -> object:
        yield FailingSession()

    app.dependency_overrides[get_session] = failing_session_override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "unavailable",
            "checks": {"database": "unavailable"},
        }
    }
