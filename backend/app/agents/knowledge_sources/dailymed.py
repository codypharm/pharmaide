"""DailyMed knowledge source for on-demand drug-label evidence.

The connector intentionally fetches one grounded medication label at a time.
Later cache orchestration can persist these chunks in ``kb_documents`` /
``kb_chunks``; this module only owns the external API adapter and conservative
section extraction.
"""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from xml.etree import ElementTree

import httpx
import structlog

from app.agents.knowledge_sources import KnowledgeSourceChunk
from app.services.chunker import ChunkDraft, chunk_segments
from app.services.kb_segments import TextSegment, clean_text

DAILYMED_BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
SELECTED_SECTION_TITLES = {
    "adverse reactions",
    "boxed warning",
    "contraindications",
    "dosage and administration",
    "drug interactions",
    "patient counseling information",
    "use in specific populations",
    "warnings and precautions",
}
SECTION_TITLE_ALIASES = {
    "warnings": "warnings and precautions",
}

log = structlog.get_logger(__name__)


class DailyMedLookupError(RuntimeError):
    """Raised when DailyMed cannot provide a usable label for a drug."""


@dataclass(frozen=True, slots=True)
class DailyMedLabel:
    """Candidate DailyMed label selected for a grounded medication."""

    setid: str
    title: str


@dataclass(frozen=True, slots=True)
class DailyMedSection:
    """Extracted label section that is useful for clinical retrieval."""

    title: str
    text: str


@dataclass(frozen=True, slots=True)
class DailyMedClient:
    """Small async client for the DailyMed v2 REST API."""

    http_client: httpx.AsyncClient
    base_url: str = DAILYMED_BASE_URL

    async def find_label(
        self,
        *,
        rxcui: str | None = None,
        drug_name: str | None = None,
    ) -> DailyMedLabel | None:
        """Find the strongest available SPL label candidate for a grounded drug."""
        params = _search_params(rxcui=rxcui, drug_name=drug_name)
        if params is None:
            return None

        response = await self.http_client.get(f"{self.base_url}/spls.json", params=params)
        response.raise_for_status()
        labels = _labels_from_search_response(response.json())
        if not labels:
            log.info("dailymed_label_not_found", rxcui=rxcui, drug_name=drug_name)
            return None
        return labels[0]

    async def fetch_label_xml(self, setid: str) -> str:
        """Fetch one SPL label XML document by DailyMed setid."""
        response = await self.http_client.get(f"{self.base_url}/spls/{setid}.xml")
        response.raise_for_status()
        return response.text


@dataclass(frozen=True, slots=True)
class DailyMedSource:
    """Yield selected DailyMed label sections as retrievable source chunks."""

    client: DailyMedClient
    rxcui: str | None
    drug_name: str

    async def list_chunks(self, _document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        label = await self.client.find_label(rxcui=self.rxcui, drug_name=self.drug_name)
        if label is None:
            raise DailyMedLookupError(f"DailyMed label not found for {self.drug_name}")

        sections = extract_selected_sections(await self.client.fetch_label_xml(label.setid))
        if not sections:
            raise DailyMedLookupError(f"DailyMed label has no selected sections for {label.setid}")

        segments = [
            TextSegment(
                kind="text",
                content=section.text,
                document_title=label.title,
                section_title=section.title,
            )
            for section in sections
        ]
        for chunk in chunk_segments(segments):
            yield _source_chunk(chunk, source_uri=f"dailymed://{label.setid}")


def extract_selected_sections(xml_text: str) -> list[DailyMedSection]:
    """Extract only label sections useful for safety/adherence reasoning."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise DailyMedLookupError("DailyMed returned invalid SPL XML") from exc

    sections: list[DailyMedSection] = []
    seen_titles: set[str] = set()
    for section in _iter_sections(root):
        title = _section_title(section)
        if title is None:
            continue
        normalized_title = _normalize_section_title(title)
        selected_title = SECTION_TITLE_ALIASES.get(normalized_title, normalized_title)
        if selected_title not in SELECTED_SECTION_TITLES or selected_title in seen_titles:
            continue

        text = clean_text(_section_text(section))
        if not text:
            continue
        sections.append(DailyMedSection(title=title, text=text))
        seen_titles.add(selected_title)
    return sections


def _search_params(
    *,
    rxcui: str | None,
    drug_name: str | None,
) -> dict[str, str] | None:
    if rxcui and rxcui.strip():
        return {"rxcui": rxcui.strip(), "pagesize": "5"}
    if drug_name and drug_name.strip():
        return {"drug_name": drug_name.strip(), "pagesize": "5"}
    return None


def _labels_from_search_response(payload: Mapping[str, Any]) -> list[DailyMedLabel]:
    object_rows = payload.get("data")
    if isinstance(object_rows, list):
        return _labels_from_object_rows(object_rows)

    columns = [str(column).lower() for column in payload.get("COLUMNS", [])]
    rows = payload.get("DATA", [])
    if not columns or not isinstance(rows, list):
        return []

    labels: list[DailyMedLabel] = []
    setid_index = _column_index(columns, "setid")
    title_index = _column_index(columns, "title")
    if setid_index is None or title_index is None:
        return []

    for row in rows:
        if not isinstance(row, list):
            continue
        try:
            setid = str(row[setid_index]).strip()
            title = str(row[title_index]).strip()
        except IndexError:
            continue
        if setid and title:
            labels.append(DailyMedLabel(setid=setid, title=title))
    return labels


def _labels_from_object_rows(rows: list[object]) -> list[DailyMedLabel]:
    labels: list[DailyMedLabel] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        setid = str(row.get("setid", "")).strip()
        title = str(row.get("title", "")).strip()
        if setid and title:
            labels.append(DailyMedLabel(setid=setid, title=title))
    return labels


def _column_index(columns: list[str], name: str) -> int | None:
    try:
        return columns.index(name)
    except ValueError:
        return None


def _iter_sections(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == "section"]


def _section_title(section: ElementTree.Element) -> str | None:
    title = _first_child_text(section, "title")
    if title:
        return title

    for child in section:
        if _local_name(child.tag) != "code":
            continue
        display_name = child.attrib.get("displayName")
        if display_name:
            return clean_text(display_name)
    return None


def _section_text(section: ElementTree.Element) -> str:
    text_nodes = [child for child in section if _local_name(child.tag) == "text"]
    return "\n\n".join(_text_content(node) for node in text_nodes)


def _first_child_text(element: ElementTree.Element, local_name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == local_name:
            text = clean_text(_text_content(child))
            return text or None
    return None


def _text_content(element: ElementTree.Element) -> str:
    return clean_text(" ".join(part.strip() for part in element.itertext() if part.strip()))


def _normalize_section_title(title: str) -> str:
    return clean_text(title).lower()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _source_chunk(chunk: ChunkDraft, *, source_uri: str) -> KnowledgeSourceChunk:
    return KnowledgeSourceChunk(
        content=chunk.content,
        tokens=chunk.tokens,
        source_uri=source_uri,
        document_title=chunk.document_title,
        section_title=chunk.section_title,
    )
