"""DailyMed knowledge-source seam for Sprint 3.6b.

DailyMed is a free FDA label source, but the production connector still needs
scope rules, sync cadence, and label-selection policy before it can ingest
content. This stub makes the source boundary visible without silently making
network calls from the analysis path.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from app.agents.knowledge_sources import KnowledgeSourceChunk


class DailyMedSourceNotConfigured(RuntimeError):
    """Raised until the DailyMed connector is implemented in Sprint 3.6b."""


@dataclass(frozen=True, slots=True)
class DailyMedSource:
    """Placeholder source implementing the shared KnowledgeSource shape."""

    base_url: str = "https://dailymed.nlm.nih.gov/dailymed/services/v2"

    async def list_chunks(self, _document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        # Avoid a half-wired connector: labels must be curated and scoped before
        # they become retrievable clinical evidence.
        raise DailyMedSourceNotConfigured("DailyMed ingestion is planned for Sprint 3.6b")
        yield
