"""Private safety gateway smoke checks."""

from collections.abc import Mapping
from typing import Any

from app.config import Settings
from app.services.safety_gateway_smoke import run_safety_gateway_smoke


async def test_safety_gateway_smoke_validates_remote_guard_and_referee_contracts() -> None:
    settings = _remote_settings()

    report = await run_safety_gateway_smoke(
        settings,
        guard_provider=AllowGuardProvider(),
        referee_provider=AllowRefereeProvider(),
    )

    assert report.ok is True
    assert report.provider_mode == "remote_http"
    assert report.guard_action == "allow"
    assert report.referee_action == "allow"
    assert report.errors == ()


async def test_safety_gateway_smoke_requires_remote_http_mode() -> None:
    settings = Settings(_env_file=None, safety_provider="model")

    report = await run_safety_gateway_smoke(settings)

    assert report.ok is False
    assert report.errors == ("safety_provider_must_be_remote_http",)


async def test_safety_gateway_smoke_reports_schema_invalid_provider_output() -> None:
    settings = _remote_settings()

    report = await run_safety_gateway_smoke(
        settings,
        guard_provider=InvalidGuardProvider(),
        referee_provider=AllowRefereeProvider(),
    )

    assert report.ok is False
    assert report.guard_action is None
    assert any(error.startswith("guard:SafetyProviderUnavailable:") for error in report.errors)


async def test_safety_gateway_smoke_reports_provider_failure_without_stopping_other_stage() -> None:
    settings = _remote_settings()

    report = await run_safety_gateway_smoke(
        settings,
        guard_provider=FailingGuardProvider(),
        referee_provider=AllowRefereeProvider(),
    )

    assert report.ok is False
    assert report.guard_action is None
    assert report.referee_action == "allow"
    assert any(error == "guard:RuntimeError:gateway unavailable" for error in report.errors)


class AllowGuardProvider:
    async def check(self, _request) -> Mapping[str, Any]:  # type: ignore[no-untyped-def]
        return {
            "stage": "input",
            "action": "allow",
            "categories": [],
            "rationale": "Safe synthetic adherence question.",
            "confidence": 0.9,
            "safe_response": None,
            "requires_pharmacist_review": False,
        }


class AllowRefereeProvider:
    async def review(self, _request) -> Mapping[str, Any]:  # type: ignore[no-untyped-def]
        return {
            "action": "allow",
            "violations": [],
            "rationale": "Synthetic draft matches synthetic context.",
            "confidence": 0.9,
            "safe_response": None,
            "requires_pharmacist_review": False,
        }


class InvalidGuardProvider:
    async def check(self, _request) -> Mapping[str, Any]:  # type: ignore[no-untyped-def]
        return {"action": "allow"}


class FailingGuardProvider:
    async def check(self, _request) -> Mapping[str, Any]:  # type: ignore[no-untyped-def]
        raise RuntimeError("gateway unavailable")


def _remote_settings() -> Settings:
    return Settings(
        _env_file=None,
        safety_provider="remote_http",
        llama_guard_url="https://safety.test/v1/guard/check",
        agentdog_url="https://safety.test/v1/referee/review",
    )
