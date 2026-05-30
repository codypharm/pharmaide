"""WhatsApp phone-to-workspace manifest validation."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from app.config import Settings
from app.services.whatsapp_workspace_manifest import validate_whatsapp_workspace_manifest

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
OTHER_WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"


def test_whatsapp_workspace_manifest_projects_valid_phone_mapping() -> None:
    settings = Settings(
        _env_file=None,
        whatsapp_cloud_api_phone_number_id="phone-1",
        whatsapp_workspace_scope_id=UUID(WORKSPACE_ID),
    )
    manifest = {
        "phone_numbers": [
            {
                "phone_number_id": "phone-1",
                "display_phone_number": "+1 800 555 1212",
                "workspace_id": WORKSPACE_ID,
            }
        ]
    }

    report = validate_whatsapp_workspace_manifest(manifest, settings)

    assert report.ok is True
    assert report.as_dict()["phone_numbers"] == [
        {
            "phone_number_id": "phone-1",
            "display_phone_number": "+18005551212",
            "workspace_id": WORKSPACE_ID,
            "matches_runtime_env": True,
        }
    ]


def test_whatsapp_workspace_manifest_reports_invalid_rows_without_hiding_valid_rows() -> None:
    manifest = {
        "phone_numbers": [
            {
                "phone_number_id": "phone-1",
                "display_phone_number": "+18005551212",
                "workspace_id": WORKSPACE_ID,
            },
            {
                "phone_number_id": "phone-2",
                "display_phone_number": "not-a-phone",
                "workspace_id": WORKSPACE_ID,
            },
            {
                "phone_number_id": "phone-3",
                "display_phone_number": "+18005551213",
                "workspace_id": "not-a-uuid",
            },
        ]
    }

    report = validate_whatsapp_workspace_manifest(manifest, Settings(_env_file=None))

    assert report.ok is False
    assert [phone.phone_number_id for phone in report.phone_numbers] == ["phone-1"]
    assert {error.code for error in report.errors} == {
        "display_phone_number_invalid",
        "workspace_id_required",
    }


def test_whatsapp_workspace_manifest_rejects_duplicate_phone_identifiers() -> None:
    manifest = {
        "phone_numbers": [
            {
                "phone_number_id": "phone-1",
                "display_phone_number": "+18005551212",
                "workspace_id": WORKSPACE_ID,
            },
            {
                "phone_number_id": "phone-1",
                "display_phone_number": "+18005551213",
                "workspace_id": OTHER_WORKSPACE_ID,
            },
        ]
    }

    report = validate_whatsapp_workspace_manifest(manifest, Settings(_env_file=None))

    assert report.ok is False
    assert [error.code for error in report.errors] == ["duplicate_phone_number_id"]


def test_whatsapp_workspace_manifest_rejects_duplicate_display_numbers() -> None:
    manifest = {
        "phone_numbers": [
            {
                "phone_number_id": "phone-1",
                "display_phone_number": "+18005551212",
                "workspace_id": WORKSPACE_ID,
            },
            {
                "phone_number_id": "phone-2",
                "display_phone_number": "+1 800 555 1212",
                "workspace_id": OTHER_WORKSPACE_ID,
            },
        ]
    }

    report = validate_whatsapp_workspace_manifest(manifest, Settings(_env_file=None))

    assert report.ok is False
    assert [error.code for error in report.errors] == ["duplicate_display_phone_number"]


def test_whatsapp_workspace_manifest_requires_runtime_mapping_when_env_is_set() -> None:
    settings = Settings(
        _env_file=None,
        whatsapp_cloud_api_phone_number_id="phone-1",
        whatsapp_workspace_scope_id=UUID(WORKSPACE_ID),
    )
    manifest = {
        "phone_numbers": [
            {
                "phone_number_id": "phone-2",
                "display_phone_number": "+18005551212",
                "workspace_id": OTHER_WORKSPACE_ID,
            }
        ]
    }

    report = validate_whatsapp_workspace_manifest(manifest, settings)

    assert report.ok is False
    assert "runtime_mapping_missing" in {error.code for error in report.errors}


def test_whatsapp_workspace_manifest_requires_phone_numbers_list() -> None:
    report = validate_whatsapp_workspace_manifest({}, Settings(_env_file=None))

    assert report.ok is False
    assert report.errors[0].code == "phone_numbers_required"


def test_whatsapp_workspace_manifest_cli_outputs_validated_mapping(tmp_path: Path) -> None:
    manifest_path = tmp_path / "whatsapp.json"
    manifest_path.write_text(
        json.dumps(
            {
                "phone_numbers": [
                    {
                        "phone_number_id": "phone-1",
                        "display_phone_number": "+18005551212",
                        "workspace_id": WORKSPACE_ID,
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, "scripts/whatsapp_workspace_manifest.py", str(manifest_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PHARMAIDE_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID": "phone-1",
            "PHARMAIDE_WHATSAPP_WORKSPACE_SCOPE_ID": WORKSPACE_ID,
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["phone_numbers"][0] == {
        "phone_number_id": "phone-1",
        "display_phone_number": "+18005551212",
        "workspace_id": WORKSPACE_ID,
        "matches_runtime_env": True,
    }
