"""GCIP custom-claims manifest validation."""

import json
import subprocess
import sys
from pathlib import Path

from app.config import Settings
from app.services.gcip_claims_manifest import validate_gcip_claims_manifest

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
OTHER_WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"


def test_gcip_claims_manifest_projects_valid_users_with_configured_claim_names() -> None:
    settings = Settings(
        _env_file=None,
        gcip_workspace_claim="clinic_id",
        gcip_workspace_memberships_claim="clinic_memberships",
    )
    manifest = {
        "users": [
            {
                "email": " Pharmacist@Example.com ",
                "workspace_id": WORKSPACE_ID,
                "workspace_memberships": [WORKSPACE_ID, OTHER_WORKSPACE_ID],
            }
        ]
    }

    report = validate_gcip_claims_manifest(manifest, settings)

    assert report.ok is True
    assert report.as_dict()["users"] == [
        {
            "email": "pharmacist@example.com",
            "custom_claims": {
                "clinic_id": WORKSPACE_ID,
                "clinic_memberships": [WORKSPACE_ID, OTHER_WORKSPACE_ID],
            },
        }
    ]


def test_gcip_claims_manifest_defaults_memberships_to_workspace_id() -> None:
    manifest = {
        "users": [
            {
                "email": "pharmacist@example.com",
                "workspace_id": WORKSPACE_ID,
            }
        ]
    }

    report = validate_gcip_claims_manifest(manifest, Settings(_env_file=None))

    assert report.ok is True
    assert report.users[0].custom_claims == {
        "workspace_id": WORKSPACE_ID,
        "workspace_memberships": [WORKSPACE_ID],
    }


def test_gcip_claims_manifest_reports_invalid_rows_without_hiding_valid_rows() -> None:
    manifest = {
        "users": [
            {
                "email": "valid@example.com",
                "workspace_id": WORKSPACE_ID,
            },
            {
                "email": "missing-membership@example.com",
                "workspace_id": WORKSPACE_ID,
                "workspace_memberships": [OTHER_WORKSPACE_ID],
            },
            {
                "email": "bad-workspace@example.com",
                "workspace_id": "not-a-uuid",
            },
        ]
    }

    report = validate_gcip_claims_manifest(manifest, Settings(_env_file=None))

    assert report.ok is False
    assert [user.email for user in report.users] == ["valid@example.com"]
    assert {error.code for error in report.errors} == {
        "workspace_membership_missing",
        "workspace_id_required",
    }


def test_gcip_claims_manifest_rejects_duplicate_emails() -> None:
    manifest = {
        "users": [
            {"email": "pharmacist@example.com", "workspace_id": WORKSPACE_ID},
            {"email": "PHARMACIST@example.com", "workspace_id": WORKSPACE_ID},
        ]
    }

    report = validate_gcip_claims_manifest(manifest, Settings(_env_file=None))

    assert report.ok is False
    assert [error.code for error in report.errors] == ["duplicate_email"]


def test_gcip_claims_manifest_requires_users_list() -> None:
    report = validate_gcip_claims_manifest({}, Settings(_env_file=None))

    assert report.ok is False
    assert report.errors[0].code == "users_required"


def test_gcip_claims_manifest_cli_outputs_validated_claims(tmp_path: Path) -> None:
    manifest_path = tmp_path / "claims.json"
    manifest_path.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "email": "pharmacist@example.com",
                        "workspace_id": WORKSPACE_ID,
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, "scripts/gcip_claims_manifest.py", str(manifest_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["users"][0]["custom_claims"] == {
        "workspace_id": WORKSPACE_ID,
        "workspace_memberships": [WORKSPACE_ID],
    }
