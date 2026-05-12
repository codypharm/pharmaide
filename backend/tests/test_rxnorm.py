"""RxNorm HTTP client behavior."""

import httpx
import pytest

from app.services.rxnorm import RxNormMatch, clear_rxnorm_cache, find_rxcui


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    clear_rxnorm_cache()


async def test_find_rxcui_returns_best_approximate_match() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/REST/approximateTerm.json"
        assert request.url.params["term"] == "Lisinopril"
        assert request.url.params["maxEntries"] == "1"
        assert request.url.params["option"] == "1"
        return httpx.Response(
            200,
            json={
                "approximateGroup": {
                    "candidate": [
                        {
                            "rxcui": "29046",
                            "name": "lisinopril",
                            "score": "12.5",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        match = await find_rxcui(client, "Lisinopril")

    assert match == RxNormMatch(name="lisinopril", rxcui="29046", score=12.5)


async def test_find_rxcui_returns_none_when_rxnorm_has_no_match() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"approximateGroup": {}})

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        match = await find_rxcui(client, "Not A Drug")

    assert match is None


async def test_find_rxcui_retries_server_errors_before_success() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "temporarily unavailable"})
        return httpx.Response(
            200,
            json={
                "approximateGroup": {
                    "candidate": [
                        {
                            "rxcui": "11289",
                            "name": "warfarin",
                            "score": "9.25",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        match = await find_rxcui(client, "Warfarin")

    assert attempts == 3
    assert match == RxNormMatch(name="warfarin", rxcui="11289", score=9.25)


async def test_find_rxcui_raises_after_three_server_errors() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await find_rxcui(client, "Warfarin")

    assert attempts == 3


async def test_find_rxcui_uses_case_insensitive_cache() -> None:
    requests = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={
                "approximateGroup": {
                    "candidate": [
                        {
                            "rxcui": "29046",
                            "name": "lisinopril",
                            "score": "12.5",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        first = await find_rxcui(client, "Lisinopril")
        second = await find_rxcui(client, " lisinopril ")

    assert first == second
    assert requests == 1
