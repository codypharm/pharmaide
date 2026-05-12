"""RxNorm client helpers.

RxNorm is the medication identity layer for Sprint 3: free-text drug names are
grounded to RxCUIs before downstream clinical logic runs.
"""

from typing import Any

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_rxcui_cache: dict[str, "RxNormMatch | None"] = {}
type QueryParams = dict[str, str | int | float | bool | None]


class RxNormMatch(BaseModel):
    """Best RxNorm approximate match for a medication name."""

    name: str
    rxcui: str
    score: float = Field(ge=0)


def clear_rxnorm_cache() -> None:
    """Clear process-local cache so tests can isolate HTTP behavior."""
    _rxcui_cache.clear()


async def find_rxcui(client: httpx.AsyncClient, name: str) -> RxNormMatch | None:
    """Return the best active RxNorm match for a medication name."""
    cache_key = name.strip().lower()
    if cache_key in _rxcui_cache:
        return _rxcui_cache[cache_key]

    payload = await _get_json_with_retry(
        client,
        "approximateTerm.json",
        params={"term": name, "maxEntries": 1, "option": 1},
    )
    candidate = _first_candidate(payload)
    if candidate is None:
        _rxcui_cache[cache_key] = None
        return None

    match = RxNormMatch(
        name=str(candidate["name"]),
        rxcui=str(candidate["rxcui"]),
        score=float(candidate["score"]),
    )
    _rxcui_cache[cache_key] = match
    return match


@retry(
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.01, max=4),
    reraise=True,
)
async def _get_json_with_retry(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: QueryParams,
) -> dict[str, Any]:
    response = await client.get(path, params=params)
    if response.status_code >= 500:
        response.raise_for_status()
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return {}
    return payload


def _first_candidate(payload: dict[str, Any]) -> dict[str, Any] | None:
    group = payload.get("approximateGroup")
    if not isinstance(group, dict):
        return None

    candidates = group.get("candidate")
    if not isinstance(candidates, list) or not candidates:
        return None

    candidate = candidates[0]
    if not isinstance(candidate, dict):
        return None
    return candidate
