from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import CurrentActor, get_current_actor
from app.config import Settings


async def test_disabled_auth_mode_uses_development_actor_header() -> None:
    actor_id = uuid4()
    app = _auth_test_app(Settings(_env_file=None, auth_mode="disabled"))

    response = await _get_me(app, headers={"X-Pharmaide-User-Id": str(actor_id)})

    assert response.status_code == 200
    assert response.json() == {
        "actor_id": str(actor_id),
        "subject": str(actor_id),
        "auth_mode": "disabled",
        "email": None,
        "workspace_id": None,
        "kb_scope_id": str(actor_id),
    }


async def test_disabled_auth_mode_falls_back_to_anonymous_actor() -> None:
    app = _auth_test_app(Settings(_env_file=None, auth_mode="disabled"))

    first = await _get_me(app)
    second = await _get_me(app)

    assert first.status_code == 200
    assert first.json()["subject"] == "anonymous"
    assert UUID(first.json()["actor_id"]) == UUID(second.json()["actor_id"])
    assert first.json()["workspace_id"] is None
    assert UUID(first.json()["kb_scope_id"]) == UUID(first.json()["actor_id"])


async def test_gcip_auth_mode_requires_bearer_token() -> None:
    app = _auth_test_app(
        Settings(_env_file=None, auth_mode="gcip", gcip_project_id="pharmaide-test")
    )

    response = await _get_me(app)

    assert response.status_code == 401
    assert response.json()["detail"] == {"error": "auth_token_required"}


async def test_gcip_auth_mode_rejects_invalid_token(monkeypatch) -> None:
    def reject_token(token: str, *, project_id: str) -> dict[str, object]:
        del token, project_id
        raise ValueError("bad token")

    monkeypatch.setattr("app.auth.verify_gcip_id_token", reject_token)
    app = _auth_test_app(
        Settings(_env_file=None, auth_mode="gcip", gcip_project_id="pharmaide-test")
    )

    response = await _get_me(app, headers={"Authorization": "Bearer bad"})

    assert response.status_code == 401
    assert response.json()["detail"] == {"error": "invalid_auth_token"}


async def test_gcip_auth_mode_projects_verified_subject_to_stable_actor_id(monkeypatch) -> None:
    def verify_token(token: str, *, project_id: str) -> dict[str, object]:
        assert token == "good-token"
        assert project_id == "pharmaide-test"
        return {"sub": "firebase-user-123", "email": "pharmacist@example.com"}

    monkeypatch.setattr("app.auth.verify_gcip_id_token", verify_token)
    app = _auth_test_app(
        Settings(_env_file=None, auth_mode="gcip", gcip_project_id="pharmaide-test")
    )

    first = await _get_me(app, headers={"Authorization": "Bearer good-token"})
    second = await _get_me(app, headers={"Authorization": "Bearer good-token"})

    assert first.status_code == 200
    assert first.json()["subject"] == "firebase-user-123"
    assert first.json()["auth_mode"] == "gcip"
    assert first.json()["email"] == "pharmacist@example.com"
    assert UUID(first.json()["actor_id"]) == UUID(second.json()["actor_id"])
    assert first.json()["workspace_id"] is None
    assert UUID(first.json()["kb_scope_id"]) == UUID(first.json()["actor_id"])


async def test_gcip_workspace_claim_becomes_knowledge_scope(monkeypatch) -> None:
    workspace_id = uuid4()

    def verify_token(token: str, *, project_id: str) -> dict[str, object]:
        assert token == "good-token"
        assert project_id == "pharmaide-test"
        return {
            "sub": "firebase-user-123",
            "email": "pharmacist@example.com",
            "workspace_id": str(workspace_id),
        }

    monkeypatch.setattr("app.auth.verify_gcip_id_token", verify_token)
    app = _auth_test_app(
        Settings(_env_file=None, auth_mode="gcip", gcip_project_id="pharmaide-test")
    )

    response = await _get_me(app, headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    assert response.json()["workspace_id"] == str(workspace_id)
    assert response.json()["kb_scope_id"] == str(workspace_id)


async def test_gcip_auth_mode_can_require_workspace_claim(monkeypatch) -> None:
    def verify_token(token: str, *, project_id: str) -> dict[str, object]:
        del token, project_id
        return {"sub": "firebase-user-123", "email": "pharmacist@example.com"}

    monkeypatch.setattr("app.auth.verify_gcip_id_token", verify_token)
    app = _auth_test_app(
        Settings(
            _env_file=None,
            auth_mode="gcip",
            gcip_project_id="pharmaide-test",
            gcip_require_workspace_claim=True,
        )
    )

    response = await _get_me(app, headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 403
    assert response.json()["detail"] == {"error": "workspace_claim_required"}


def _auth_test_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings

    @app.get("/me")
    async def me(actor: Annotated[CurrentActor, Depends(get_current_actor)]):
        return {
            "actor_id": str(actor.actor_id),
            "subject": actor.subject,
            "auth_mode": actor.auth_mode,
            "email": actor.email,
            "workspace_id": str(actor.workspace_id) if actor.workspace_id is not None else None,
            "kb_scope_id": str(actor.kb_scope_id),
        }

    return app


async def _get_me(app: FastAPI, headers: dict[str, str] | None = None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/me", headers=headers)
