import pytest

from app.config import Settings


def test_settings_defaults_match_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "PHARMAIDE_LOG_MODE",
        "PHARMAIDE_DEBUG_ROUTES_ENABLED",
        "PHARMAIDE_CHECKPOINT_DB_PATH",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.log_mode == "console"
    assert settings.debug_routes_enabled is False
    assert settings.checkpoint_db_path == "./pharmaide.db"


def test_settings_reads_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_LOG_MODE", "json")
    monkeypatch.setenv("PHARMAIDE_DEBUG_ROUTES_ENABLED", "true")
    monkeypatch.setenv("PHARMAIDE_CHECKPOINT_DB_PATH", "/tmp/x.db")

    settings = Settings(_env_file=None)

    assert settings.log_mode == "json"
    assert settings.debug_routes_enabled is True
    assert settings.checkpoint_db_path == "/tmp/x.db"
