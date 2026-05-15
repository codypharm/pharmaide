import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_defaults_match_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "PHARMAIDE_LOG_MODE",
        "PHARMAIDE_DEBUG_ROUTES_ENABLED",
        "PHARMAIDE_CHECKPOINT_DB_PATH",
        "PHARMAIDE_RXNORM_BASE_URL",
        "PHARMAIDE_OPENAI_API_KEY",
        "PHARMAIDE_SAFETY_PROVIDER",
        "PHARMAIDE_LLAMA_GUARD_URL",
        "PHARMAIDE_AGENTDOG_URL",
        "PHARMAIDE_SAFETY_PROVIDER_API_KEY",
        "PHARMAIDE_SAFETY_PROVIDER_TIMEOUT_SECONDS",
        "PHARMAIDE_ANALYSIS_TIMEOUT_SECONDS",
        "PHARMAIDE_MAX_CONCURRENT_ANALYSES_PER_USER",
        "PHARMAIDE_KNOWLEDGE_UPLOAD_DIR",
        "PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES",
        "PHARMAIDE_KNOWLEDGE_INGESTION_STALE_MINUTES",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.log_mode == "console"
    assert settings.debug_routes_enabled is False
    assert settings.checkpoint_db_path == "./pharmaide.db"
    assert settings.rxnorm_base_url == "https://rxnav.nlm.nih.gov/REST"
    assert settings.openai_api_key is None
    assert settings.safety_provider == "model"
    assert settings.llama_guard_url is None
    assert settings.agentdog_url is None
    assert settings.safety_provider_api_key is None
    assert settings.safety_provider_timeout_seconds == 10
    assert settings.analysis_timeout_seconds == 60
    assert settings.max_concurrent_analyses_per_user == 3
    assert settings.knowledge_upload_dir == "./data/kb_uploads"
    assert settings.knowledge_max_upload_bytes == 25 * 1024 * 1024
    assert settings.knowledge_ingestion_stale_minutes == 30


def test_settings_reads_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_LOG_MODE", "json")
    monkeypatch.setenv("PHARMAIDE_DEBUG_ROUTES_ENABLED", "true")
    monkeypatch.setenv("PHARMAIDE_CHECKPOINT_DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("PHARMAIDE_RXNORM_BASE_URL", "https://rxnav.test/REST")
    monkeypatch.setenv("PHARMAIDE_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER", "remote_http")
    monkeypatch.setenv("PHARMAIDE_LLAMA_GUARD_URL", "https://safety.test/v1/guard/check")
    monkeypatch.setenv("PHARMAIDE_AGENTDOG_URL", "https://safety.test/v1/referee/review")
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER_API_KEY", "safety-test")
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER_TIMEOUT_SECONDS", "8")
    monkeypatch.setenv("PHARMAIDE_ANALYSIS_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("PHARMAIDE_MAX_CONCURRENT_ANALYSES_PER_USER", "5")
    monkeypatch.setenv("PHARMAIDE_KNOWLEDGE_UPLOAD_DIR", "/tmp/kb")
    monkeypatch.setenv("PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES", "1024")
    monkeypatch.setenv("PHARMAIDE_KNOWLEDGE_INGESTION_STALE_MINUTES", "7")

    settings = Settings(_env_file=None)

    assert settings.log_mode == "json"
    assert settings.debug_routes_enabled is True
    assert settings.checkpoint_db_path == "/tmp/x.db"
    assert settings.rxnorm_base_url == "https://rxnav.test/REST"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test"
    assert settings.safety_provider == "remote_http"
    assert settings.llama_guard_url == "https://safety.test/v1/guard/check"
    assert settings.agentdog_url == "https://safety.test/v1/referee/review"
    assert settings.safety_provider_api_key is not None
    assert settings.safety_provider_api_key.get_secret_value() == "safety-test"
    assert settings.safety_provider_timeout_seconds == 8
    assert settings.analysis_timeout_seconds == 12
    assert settings.max_concurrent_analyses_per_user == 5
    assert settings.knowledge_upload_dir == "/tmp/kb"
    assert settings.knowledge_max_upload_bytes == 1024
    assert settings.knowledge_ingestion_stale_minutes == 7


def test_settings_accepts_human_readable_knowledge_upload_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES", "25MB")

    settings = Settings(_env_file=None)

    assert settings.knowledge_max_upload_bytes == 25 * 1024 * 1024


def test_settings_rejects_unknown_safety_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER", "llama_guard")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_remote_http_safety_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER", "remote_http")
    monkeypatch.delenv("PHARMAIDE_LLAMA_GUARD_URL", raising=False)
    monkeypatch.delenv("PHARMAIDE_AGENTDOG_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
