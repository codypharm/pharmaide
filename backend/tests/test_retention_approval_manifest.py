"""Production retention approval manifest validation."""

import json
import os
import subprocess
import sys
from pathlib import Path

from app.config import Settings
from app.services.retention_approval_manifest import validate_retention_approval_manifest


def test_retention_approval_manifest_accepts_valid_approval_for_apply_mode() -> None:
    settings = Settings(
        _env_file=None,
        data_retention_closed_treatment_days=365,
        audit_retention_operational_days=120,
        data_retention_cleanup_dry_run=False,
        audit_retention_cleanup_dry_run=False,
    )

    report = validate_retention_approval_manifest(_valid_manifest(), settings)

    assert report.ok is True
    assert report.cleanup_apply_requested is True
    assert report.as_dict()["errors"] == []


def test_retention_approval_manifest_rejects_missing_approvers_and_audit_policy() -> None:
    manifest = _valid_manifest()
    manifest["clinical_audit_logs_retained"] = False
    manifest["approved_by"] = {"clinical": "Clinical Lead"}

    report = validate_retention_approval_manifest(manifest, _settings())

    assert report.ok is False
    assert {
        "clinical_audit_logs_not_retained",
        "legal_approver_required",
        "operations_approver_required",
    }.issubset({error.code for error in report.errors})


def test_retention_approval_manifest_rejects_gcs_lifecycle_shorter_than_db_retention() -> None:
    manifest = _valid_manifest()
    manifest["gcs_lifecycle_retention_days"] = 100

    report = validate_retention_approval_manifest(manifest, _settings())

    assert report.ok is False
    assert "gcs_lifecycle_too_short" in {error.code for error in report.errors}


def test_retention_approval_manifest_rejects_settings_mismatch() -> None:
    manifest = _valid_manifest()
    manifest["closed_treatment_retention_days"] = 90
    manifest["operational_audit_retention_days"] = 30

    report = validate_retention_approval_manifest(manifest, _settings())

    assert report.ok is False
    assert {
        "closed_treatment_retention_days_mismatch",
        "operational_audit_retention_days_mismatch",
    }.issubset({error.code for error in report.errors})


def test_retention_approval_manifest_blocks_apply_mode_when_approval_is_invalid() -> None:
    settings = Settings(
        _env_file=None,
        data_retention_cleanup_dry_run=False,
        audit_retention_cleanup_dry_run=True,
    )
    manifest = _valid_manifest()
    del manifest["approved_by"]

    report = validate_retention_approval_manifest(manifest, settings)

    assert report.ok is False
    assert "cleanup_apply_requires_valid_approval" in {error.code for error in report.errors}


def test_retention_approval_manifest_cli_outputs_valid_report(tmp_path: Path) -> None:
    manifest_path = tmp_path / "retention.json"
    manifest_path.write_text(json.dumps(_valid_manifest()))

    result = subprocess.run(
        [sys.executable, "scripts/retention_approval_manifest.py", str(manifest_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PHARMAIDE_DATA_RETENTION_CLOSED_TREATMENT_DAYS": "365",
            "PHARMAIDE_AUDIT_RETENTION_OPERATIONAL_DAYS": "120",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["closed_treatment_retention_days"] == 365


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        data_retention_closed_treatment_days=365,
        audit_retention_operational_days=120,
    )


def _valid_manifest() -> dict[str, object]:
    return {
        "closed_treatment_retention_days": 365,
        "operational_audit_retention_days": 120,
        "gcs_lifecycle_retention_days": 365,
        "clinical_audit_logs_retained": True,
        "approved_by": {
            "clinical": "Clinical Lead",
            "legal": "Legal Approver",
            "operations": "Operations Lead",
        },
    }
