"""Configuration bridge for safety sandwich providers."""

from pydantic import SecretStr

from app.agents.model_safety_providers import ModelGuardProvider, ModelRefereeProvider
from app.agents.safety_provider_factory import build_configured_safety_providers
from app.agents.safety_providers import UnconfiguredGuardProvider, UnconfiguredRefereeProvider


def test_safety_provider_factory_fails_closed_without_openai_key() -> None:
    providers = build_configured_safety_providers(None)

    assert isinstance(providers.guard_provider, UnconfiguredGuardProvider)
    assert isinstance(providers.referee_provider, UnconfiguredRefereeProvider)


def test_safety_provider_factory_fails_closed_when_mode_is_unconfigured() -> None:
    providers = build_configured_safety_providers(
        SecretStr("test-openai-key"),
        provider_mode="unconfigured",
    )

    assert isinstance(providers.guard_provider, UnconfiguredGuardProvider)
    assert isinstance(providers.referee_provider, UnconfiguredRefereeProvider)


def test_safety_provider_factory_uses_model_providers_with_openai_key() -> None:
    providers = build_configured_safety_providers(
        SecretStr("test-openai-key"),
        provider_mode="model",
    )

    assert isinstance(providers.guard_provider, ModelGuardProvider)
    assert isinstance(providers.referee_provider, ModelRefereeProvider)
