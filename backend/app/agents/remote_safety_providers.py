"""HTTP adapters for private safety-provider services.

These classes translate PharmaAide's validated provider requests into private
HTTP calls. They do not validate clinical decisions themselves; the existing
provider runners validate returned JSON with strict Pydantic schemas before
orchestration can use it.
"""

from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import SecretStr

from app.agents.safety_providers import SafetyProviderUnavailable
from app.agents.safety_schemas import GuardRequest, RefereeRequest

DEFAULT_TIMEOUT_SECONDS = 10.0


class RemoteHttpGuardProvider:
    """Llama Guard-style provider backed by a private HTTP endpoint."""

    def __init__(
        self,
        *,
        url: str,
        api_key: SecretStr | None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def check(self, request: GuardRequest) -> Mapping[str, Any]:
        return await _post_provider_json(
            self._url,
            request.model_dump(mode="json"),
            api_key=self._api_key,
            timeout_seconds=self._timeout_seconds,
            client=self._client,
        )


class RemoteHttpRefereeProvider:
    """AgentDoG-style referee provider backed by a private HTTP endpoint."""

    def __init__(
        self,
        *,
        url: str,
        api_key: SecretStr | None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def review(self, request: RefereeRequest) -> Mapping[str, Any]:
        return await _post_provider_json(
            self._url,
            request.model_dump(mode="json"),
            api_key=self._api_key,
            timeout_seconds=self._timeout_seconds,
            client=self._client,
        )


async def _post_provider_json(
    url: str,
    payload: Mapping[str, Any],
    *,
    api_key: SecretStr | None,
    timeout_seconds: float,
    client: httpx.AsyncClient | None,
) -> Mapping[str, Any]:
    headers = _auth_headers(api_key)
    try:
        if client is not None:
            response = await client.post(url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=timeout_seconds) as transient_client:
                response = await transient_client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SafetyProviderUnavailable("remote safety provider request failed") from exc

    if not isinstance(body, Mapping):
        raise SafetyProviderUnavailable("remote safety provider returned a non-object payload")
    return body


def _auth_headers(api_key: SecretStr | None) -> dict[str, str]:
    if api_key is None:
        return {}
    return {"Authorization": f"Bearer {api_key.get_secret_value()}"}
