"""Run the configured private safety gateway smoke check."""

import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.services.safety_gateway_smoke import SafetyGatewaySmokeReport, run_safety_gateway_smoke


async def _main() -> int:
    try:
        report = await run_safety_gateway_smoke(Settings())
    except ValidationError as exc:
        report = SafetyGatewaySmokeReport(
            ok=False,
            provider_mode="unknown",
            guard_action=None,
            referee_action=None,
            errors=(str(exc),),
        )

    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
