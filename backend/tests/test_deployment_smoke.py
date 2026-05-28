"""Deployment smoke-check behavior."""

from app.services.deployment_smoke import FetchResult, run_deployment_smoke


def test_deployment_smoke_passes_liveness_readiness_and_frontend() -> None:
    requested_urls: list[str] = []

    def fake_fetch(url: str, timeout_seconds: float) -> FetchResult:
        requested_urls.append(url)
        assert timeout_seconds == 3
        if url.endswith("/health"):
            return FetchResult(status_code=200, body='{"status":"ok","version":"0.1.0"}')
        if url.endswith("/health/ready"):
            return FetchResult(
                status_code=200,
                body='{"status":"ready","version":"0.1.0","checks":{"database":"ok"}}',
            )
        return FetchResult(status_code=200, body='<html><div id="root"></div></html>')

    report = run_deployment_smoke(
        backend_url="https://api.example/",
        frontend_url="https://app.example/",
        timeout_seconds=3,
        fetch=fake_fetch,
    )

    assert report.ok is True
    assert [check.name for check in report.checks] == [
        "backend_liveness",
        "backend_readiness",
        "frontend",
    ]
    assert requested_urls == [
        "https://api.example/health",
        "https://api.example/health/ready",
        "https://app.example",
    ]


def test_deployment_smoke_fails_when_readiness_is_unavailable() -> None:
    def fake_fetch(url: str, _timeout_seconds: float) -> FetchResult:
        if url.endswith("/health/ready"):
            return FetchResult(
                status_code=503,
                body='{"detail":{"status":"unavailable"}}',
            )
        return FetchResult(status_code=200, body='{"status":"ok"}')

    report = run_deployment_smoke(
        backend_url="https://api.example",
        timeout_seconds=3,
        fetch=fake_fetch,
    )

    assert report.ok is False
    assert report.checks[0].ok is True
    assert report.checks[1].ok is False
    assert report.checks[1].detail == "expected HTTP 200, got 503"


def test_deployment_smoke_fails_when_frontend_is_not_spa_shell() -> None:
    def fake_fetch(url: str, _timeout_seconds: float) -> FetchResult:
        if url.endswith("/health"):
            return FetchResult(status_code=200, body='{"status":"ok"}')
        if url.endswith("/health/ready"):
            return FetchResult(status_code=200, body='{"status":"ready"}')
        return FetchResult(status_code=200, body="<html></html>")

    report = run_deployment_smoke(
        backend_url="https://api.example",
        frontend_url="https://app.example",
        timeout_seconds=3,
        fetch=fake_fetch,
    )

    assert report.ok is False
    assert report.checks[2].name == "frontend"
    assert report.checks[2].detail == "missing app root element"
