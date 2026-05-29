"""Run the configured knowledge storage smoke check."""

import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.services.knowledge_storage_smoke import (
    KnowledgeStorageSmokeReport,
    run_knowledge_storage_smoke,
)


async def _main() -> int:
    try:
        report = await run_knowledge_storage_smoke(Settings())
    except ValidationError as exc:
        report = KnowledgeStorageSmokeReport(
            backend="unknown",
            ok=False,
            source_uri=None,
            read_chunk_count=0,
            removed=False,
            errors=(str(exc),),
        )

    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
