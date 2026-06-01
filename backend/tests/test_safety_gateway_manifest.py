"""Private safety gateway deployment manifest validation."""

import json
import os
import subprocess
import sys
from pathlib import Path

from app.config import Settings
from app.services.safety_gateway_manifest import validate_safety_gateway_manifest


def test_safety_gateway_manifest_accepts_valid_runtime_manifest() -> None:
    report = validate_safety_gateway_manifest(_valid_manifest(), _remote_settings())

    assert report.ok is True
    assert report.environment == "staging"
    assert report.provider == "remote_http"
    assert report.as_dict()["errors"] == []


def test_safety_gateway_manifest_rejects_non_remote_provider() -> None:
    manifest = _valid_manifest()
    manifest["provider"] = "model"

    report = validate_safety_gateway_manifest(manifest, _remote_settings())

    assert report.ok is False
    assert "provider_must_be_remote_http" in {error.code for error in report.errors}


def test_safety_gateway_manifest_rejects_public_or_insecure_provider_urls() -> None:
    manifest = _valid_manifest()
    manifest["guard"]["url"] = "http://localhost:9001/v1/guard/check"
    manifest["referee"]["url"] = "https://127.0.0.1/v1/referee/review"

    report = validate_safety_gateway_manifest(manifest, _remote_settings())

    assert report.ok is False
    assert {
        "guard_url_invalid",
        "referee_url_invalid",
    }.issubset({error.code for error in report.errors})


def test_safety_gateway_manifest_rejects_open_ingress_and_missing_auth() -> None:
    manifest = _valid_manifest()
    manifest["network"]["ingress"] = "public"
    manifest["auth"] = {"mode": "none"}

    report = validate_safety_gateway_manifest(manifest, _remote_settings())

    assert report.ok is False
    assert {
        "network_ingress_must_be_private",
        "auth_mode_invalid",
    }.issubset({error.code for error in report.errors})


def test_safety_gateway_manifest_rejects_runtime_mismatch() -> None:
    manifest = _valid_manifest()
    manifest["guard"]["url"] = "https://other.internal.example/v1/guard/check"
    manifest["timeout_seconds"] = 30

    report = validate_safety_gateway_manifest(manifest, _remote_settings())

    assert report.ok is False
    assert {
        "guard_url_mismatch",
        "timeout_seconds_mismatch",
    }.issubset({error.code for error in report.errors})


def test_safety_gateway_manifest_cli_outputs_valid_report(tmp_path: Path) -> None:
    manifest_path = tmp_path / "safety-gateway.json"
    manifest_path.write_text(json.dumps(_valid_manifest()))

    result = subprocess.run(
        [sys.executable, "scripts/safety_gateway_manifest.py", str(manifest_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PHARMAIDE_SAFETY_PROVIDER": "remote_http",
            "PHARMAIDE_LLAMA_GUARD_URL": "https://llama-guard.internal.example/v1/guard/check",
            "PHARMAIDE_AGENTDOG_URL": "https://agentdog.internal.example/v1/referee/review",
            "PHARMAIDE_SAFETY_PROVIDER_API_KEY": "secret",
            "PHARMAIDE_SAFETY_PROVIDER_TIMEOUT_SECONDS": "10",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["provider"] == "remote_http"


def _remote_settings() -> Settings:
    return Settings(
        _env_file=None,
        safety_provider="remote_http",
        llama_guard_url="https://llama-guard.internal.example/v1/guard/check",
        agentdog_url="https://agentdog.internal.example/v1/referee/review",
        safety_provider_timeout_seconds=10,
    )


def _valid_manifest() -> dict[str, object]:
    return {
        "environment": "staging",
        "provider": "remote_http",
        "guard": {
            "service": "llama_guard",
            "url": "https://llama-guard.internal.example/v1/guard/check",
        },
        "referee": {
            "service": "agentdog",
            "url": "https://agentdog.internal.example/v1/referee/review",
        },
        "auth": {
            "mode": "bearer_token",
            "secret_name": "projects/pharmaide/secrets/safety-provider-api-key",
        },
        "network": {
            "ingress": "internal_only",
            "backend_access": "service_identity",
        },
        "timeout_seconds": 10,
    }
