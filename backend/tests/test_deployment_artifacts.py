"""Deployment artifact guardrails."""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_backend_dockerfile_is_cloud_run_ready() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder" in dockerfile
    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    assert "ENV PORT=8080" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}" in dockerfile
    assert "USER pharmaide" in dockerfile
    assert "COPY . ." not in dockerfile


def test_backend_dockerignore_excludes_local_state_and_secrets() -> None:
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    required_ignores = {
        ".env",
        ".env.*",
        ".venv",
        "*.db",
        ".reports",
        "data",
    }
    assert required_ignores.issubset(set(dockerignore))
    assert "!.env.example" in dockerignore
