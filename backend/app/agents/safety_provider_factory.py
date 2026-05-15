"""Configuration bridge for safety sandwich providers.

The rest of the app should not know whether safety checks are backed by
temporary model providers or dedicated Llama Guard / AgentDoG services. This
factory keeps that decision in one place and fails closed when no model key is
configured.
"""

from dataclasses import dataclass

from pydantic import SecretStr
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agents.model_safety_providers import (
    ModelGuardProvider,
    ModelRefereeProvider,
    build_guard_agent,
    build_referee_agent,
)
from app.agents.safety_providers import (
    SafetyGuardProvider,
    SafetyRefereeProvider,
    UnconfiguredGuardProvider,
    UnconfiguredRefereeProvider,
)


@dataclass(frozen=True)
class ConfiguredSafetyProviders:
    """Runtime provider pair used by the safety sandwich runner."""

    guard_provider: SafetyGuardProvider
    referee_provider: SafetyRefereeProvider


def build_configured_safety_providers(
    openai_api_key: SecretStr | None,
) -> ConfiguredSafetyProviders:
    """Build safety providers from PHARMAIDE_OPENAI_API_KEY."""
    if openai_api_key is None:
        return ConfiguredSafetyProviders(
            guard_provider=UnconfiguredGuardProvider(),
            referee_provider=UnconfiguredRefereeProvider(),
        )

    provider = OpenAIProvider(api_key=openai_api_key.get_secret_value())
    # Separate model instances keep future guard/referee model selection isolated.
    guard_agent = build_guard_agent(OpenAIResponsesModel("gpt-5", provider=provider))
    referee_agent = build_referee_agent(OpenAIResponsesModel("gpt-5", provider=provider))
    return ConfiguredSafetyProviders(
        guard_provider=ModelGuardProvider(guard_agent),
        referee_provider=ModelRefereeProvider(referee_agent),
    )
