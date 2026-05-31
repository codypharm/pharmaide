"""Production knowledge storage manifest validation."""

import json
import os
import subprocess
import sys
from pathlib import Path

from app.config import Settings
from app.services.knowledge_storage_manifest import validate_knowledge_storage_manifest


def test_knowledge_storage_manifest_accepts_valid_gcs_runtime_manifest() -> None:
    report = validate_knowledge_storage_manifest(_valid_manifest(), _gcs_settings())

    assert report.ok is True
    assert report.bucket_name == "pharmaide-kb-prod"
    assert report.as_dict()["errors"] == []


def test_knowledge_storage_manifest_rejects_unsafe_bucket_controls() -> None:
    manifest = _valid_manifest()
    manifest["gcs"]["uniform_bucket_level_access"] = False
    manifest["gcs"]["public_access_prevention"] = "inherited"

    report = validate_knowledge_storage_manifest(manifest, _gcs_settings())

    assert report.ok is False
    assert {
        "uniform_bucket_level_access_required",
        "public_access_prevention_required",
    }.issubset({error.code for error in report.errors})


def test_knowledge_storage_manifest_rejects_runtime_mismatch_and_bad_prefix() -> None:
    manifest = _valid_manifest()
    manifest["storage"]["bucket_name"] = "other-bucket"
    manifest["storage"]["prefix"] = "../kb"
    manifest["storage"]["max_upload_bytes"] = 5 * 1024 * 1024

    report = validate_knowledge_storage_manifest(manifest, _gcs_settings())

    assert report.ok is False
    assert {
        "bucket_name_mismatch",
        "prefix_invalid",
        "max_upload_bytes_mismatch",
    }.issubset({error.code for error in report.errors})


def test_knowledge_storage_manifest_rejects_lifecycle_shorter_than_retention() -> None:
    manifest = _valid_manifest()
    manifest["gcs"]["lifecycle_retention_days"] = 90

    report = validate_knowledge_storage_manifest(manifest, _gcs_settings())

    assert report.ok is False
    assert "lifecycle_retention_too_short" in {error.code for error in report.errors}


def test_knowledge_storage_manifest_requires_runtime_service_account() -> None:
    manifest = _valid_manifest()
    manifest["gcs"]["runtime_service_account_email"] = ""

    report = validate_knowledge_storage_manifest(manifest, _gcs_settings())

    assert report.ok is False
    assert "runtime_service_account_email_invalid" in {error.code for error in report.errors}


def test_knowledge_storage_manifest_cli_outputs_valid_report(tmp_path: Path) -> None:
    manifest_path = tmp_path / "knowledge-storage.json"
    manifest_path.write_text(json.dumps(_valid_manifest()))

    result = subprocess.run(
        [sys.executable, "scripts/knowledge_storage_manifest.py", str(manifest_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PHARMAIDE_KNOWLEDGE_STORAGE_BACKEND": "gcs",
            "PHARMAIDE_KNOWLEDGE_GCS_BUCKET": "pharmaide-kb-prod",
            "PHARMAIDE_KNOWLEDGE_GCS_PREFIX": "kb_uploads",
            "PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES": "25MB",
            "PHARMAIDE_DATA_RETENTION_CLOSED_TREATMENT_DAYS": "365",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["bucket_name"] == "pharmaide-kb-prod"


def _gcs_settings() -> Settings:
    return Settings(
        _env_file=None,
        knowledge_storage_backend="gcs",
        knowledge_gcs_bucket="pharmaide-kb-prod",
        knowledge_gcs_prefix="kb_uploads",
        knowledge_max_upload_bytes=25 * 1024 * 1024,
        data_retention_closed_treatment_days=365,
    )


def _valid_manifest() -> dict[str, object]:
    return {
        "storage": {
            "backend": "gcs",
            "bucket_name": "pharmaide-kb-prod",
            "prefix": "kb_uploads",
            "max_upload_bytes": 25 * 1024 * 1024,
        },
        "gcs": {
            "runtime_service_account_email": (
                "backend-runtime@pharmaide-prod.iam.gserviceaccount.com"
            ),
            "lifecycle_retention_days": 365,
            "uniform_bucket_level_access": True,
            "public_access_prevention": "enforced",
        },
    }
