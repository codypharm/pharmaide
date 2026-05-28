"""Deployment smoke checks for staging rollout.

These checks validate deployment wiring only. They intentionally avoid logging
or requesting clinical data.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class FetchResult:
    status_code: int
    body: str


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class SmokeReport:
    checks: tuple[SmokeCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checks": [
                {"name": check.name, "ok": check.ok, "detail": check.detail}
                for check in self.checks
            ],
        }


Fetch = Callable[[str, float], FetchResult]


def run_deployment_smoke(
    *,
    backend_url: str,
    frontend_url: str | None = None,
    timeout_seconds: float = 10,
    fetch: Fetch = None,
) -> SmokeReport:
    """Check deployed backend liveness/readiness and optional frontend reachability."""
    effective_fetch = fetch or fetch_url
    backend_base = _base_url(backend_url)
    checks = [
        _check_backend_health(backend_base, timeout_seconds, effective_fetch),
        _check_backend_readiness(backend_base, timeout_seconds, effective_fetch),
    ]
    if frontend_url:
        checks.append(_check_frontend(_base_url(frontend_url), timeout_seconds, effective_fetch))
    return SmokeReport(checks=tuple(checks))


def fetch_url(url: str, timeout_seconds: float) -> FetchResult:
    """Fetch a URL with stdlib networking so the smoke command has no new runtime deps."""
    request = Request(url, headers={"User-Agent": "pharmaide-deployment-smoke"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return FetchResult(
                status_code=response.status,
                body=response.read().decode("utf-8", errors="replace"),
            )
    except HTTPError as exc:
        return FetchResult(
            status_code=exc.code,
            body=exc.read().decode("utf-8", errors="replace"),
        )
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _check_backend_health(base_url: str, timeout_seconds: float, fetch: Fetch) -> SmokeCheck:
    try:
        response = fetch(f"{base_url}/health", timeout_seconds)
    except Exception as exc:
        return SmokeCheck(name="backend_liveness", ok=False, detail=str(exc))
    return _json_status_check(
        name="backend_liveness",
        response=response,
        expected_status_code=200,
        expected_status="ok",
    )


def _check_backend_readiness(base_url: str, timeout_seconds: float, fetch: Fetch) -> SmokeCheck:
    try:
        response = fetch(f"{base_url}/health/ready", timeout_seconds)
    except Exception as exc:
        return SmokeCheck(name="backend_readiness", ok=False, detail=str(exc))
    return _json_status_check(
        name="backend_readiness",
        response=response,
        expected_status_code=200,
        expected_status="ready",
    )


def _check_frontend(base_url: str, timeout_seconds: float, fetch: Fetch) -> SmokeCheck:
    try:
        response = fetch(base_url, timeout_seconds)
    except Exception as exc:
        return SmokeCheck(name="frontend", ok=False, detail=str(exc))
    if response.status_code != 200:
        return SmokeCheck(
            name="frontend",
            ok=False,
            detail=f"expected HTTP 200, got {response.status_code}",
        )
    if 'id="root"' not in response.body and "id='root'" not in response.body:
        return SmokeCheck(name="frontend", ok=False, detail="missing app root element")
    return SmokeCheck(name="frontend", ok=True, detail="reachable")


def _json_status_check(
    *,
    name: str,
    response: FetchResult,
    expected_status_code: int,
    expected_status: str,
) -> SmokeCheck:
    if response.status_code != expected_status_code:
        return SmokeCheck(
            name=name,
            ok=False,
            detail=f"expected HTTP {expected_status_code}, got {response.status_code}",
        )
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError:
        return SmokeCheck(name=name, ok=False, detail="response was not JSON")
    if payload.get("status") != expected_status:
        return SmokeCheck(
            name=name,
            ok=False,
            detail=f"expected status {expected_status!r}, got {payload.get('status')!r}",
        )
    return SmokeCheck(name=name, ok=True, detail="ok")


def _base_url(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        raise ValueError("deployment smoke URL cannot be empty")
    return cleaned
