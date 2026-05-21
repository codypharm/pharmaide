from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

VITE_DEV_ORIGIN = "http://localhost:5173"


async def test_cors_preflight_allows_vite_dev_origin() -> None:
    app = create_app(Settings(_env_file=None))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": VITE_DEV_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == VITE_DEV_ORIGIN


async def test_cors_blocks_unlisted_origin() -> None:
    app = create_app(Settings(_env_file=None))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": "https://evil.example"})

    assert response.headers.get("access-control-allow-origin") != "https://evil.example"


async def test_cors_allows_configured_production_origin() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            cors_allowed_origins="https://app.pharmaide.example",
        )
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://app.pharmaide.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "https://app.pharmaide.example"
    )
