"""HTTP adapters for private safety provider services."""

from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from app.agents.remote_safety_providers import (
    RemoteHttpGuardProvider,
    RemoteHttpRefereeProvider,
)
from app.agents.safety_providers import SafetyProviderUnavailable
from app.agents.safety_schemas import GuardRequest, RefereeRequest

TREATMENT_ID = UUID("11111111-1111-1111-1111-111111111111")


async def test_remote_http_guard_provider_posts_guard_request_and_returns_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = request.read()
        return httpx.Response(
            200,
            json={
                "stage": "input",
                "action": "allow",
                "categories": [],
                "rationale": "Safe adherence question.",
                "confidence": 0.88,
                "safe_response": None,
                "requires_pharmacist_review": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = RemoteHttpGuardProvider(
            url="https://safety.test/v1/guard/check",
            api_key=SecretStr("safety-key"),
            client=client,
        )

        payload = await provider.check(
            GuardRequest(
                stage="input",
                treatment_id=TREATMENT_ID,
                actor_role="patient",
                content="Can I take this after food?",
            )
        )

    assert seen["url"] == "https://safety.test/v1/guard/check"
    assert seen["authorization"] == "Bearer safety-key"
    assert b'"treatment_id":"11111111-1111-1111-1111-111111111111"' in seen["payload"]
    assert payload["action"] == "allow"


async def test_remote_http_referee_provider_posts_referee_request_and_returns_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = request.read()
        return httpx.Response(
            200,
            json={
                "action": "block",
                "violations": [
                    {
                        "violation_type": "dosage_change",
                        "description": "Draft changes the approved dose.",
                    }
                ],
                "rationale": "Draft changes treatment instructions.",
                "confidence": 0.93,
                "safe_response": None,
                "requires_pharmacist_review": True,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = RemoteHttpRefereeProvider(
            url="https://safety.test/v1/referee/review",
            api_key=None,
            client=client,
        )

        payload = await provider.review(
            RefereeRequest(
                treatment_id=TREATMENT_ID,
                patient_message="Can I take more?",
                assistant_draft="Take two tablets tonight.",
                prescription_context="Lisinopril 10 mg once daily.",
            )
        )

    assert seen["url"] == "https://safety.test/v1/referee/review"
    assert b'"assistant_draft":"Take two tablets tonight."' in seen["payload"]
    assert payload["action"] == "block"


async def test_remote_http_provider_fails_closed_on_http_error() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(503))
    ) as client:
        provider = RemoteHttpGuardProvider(
            url="https://safety.test/v1/guard/check",
            api_key=None,
            client=client,
        )

        with pytest.raises(SafetyProviderUnavailable):
            await provider.check(
                GuardRequest(
                    stage="output",
                    treatment_id=TREATMENT_ID,
                    actor_role="assistant",
                    content="Take twice the dose.",
                )
            )


async def test_remote_http_provider_fails_closed_on_timeout() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("guard timed out")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        provider = RemoteHttpGuardProvider(
            url="https://safety.test/v1/guard/check",
            api_key=None,
            client=client,
        )

        with pytest.raises(SafetyProviderUnavailable):
            await provider.check(
                GuardRequest(
                    stage="input",
                    treatment_id=TREATMENT_ID,
                    actor_role="patient",
                    content="Can I stop taking this medication?",
                )
            )
