"""Run production deployment preflight checks."""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.services.production_preflight import (
    PreflightIssue,
    PreflightReport,
    run_production_preflight,
)


def main() -> int:
    try:
        report = run_production_preflight(Settings())
    except ValidationError as exc:
        report = PreflightReport(
            issues=(
                PreflightIssue(
                    code="settings_validation",
                    severity="error",
                    message=str(exc),
                ),
            )
        )

    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
