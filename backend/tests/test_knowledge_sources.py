"""Knowledge-source contract tests."""

from collections.abc import AsyncIterator
from uuid import UUID

import httpx

from app.agents.knowledge_sources import KnowledgeSource, KnowledgeSourceChunk
from app.agents.knowledge_sources.dailymed import (
    DailyMedClient,
    DailyMedSection,
    DailyMedSource,
    extract_selected_sections,
)
from app.agents.knowledge_sources.user_upload import UserUploadSource


class _MemorySource:
    async def list_chunks(self, document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        yield KnowledgeSourceChunk(
            content="Warfarin requires INR monitoring.",
            tokens=5,
            source_uri=f"memory://{document_id}",
            document_title="Anticoagulation Protocol",
            page_number=2,
        )


async def test_knowledge_source_protocol_yields_retrievable_chunks() -> None:
    document_id = UUID("00000000-0000-0000-0000-000000000123")
    source: KnowledgeSource = _MemorySource()

    chunks = [chunk async for chunk in source.list_chunks(document_id)]

    assert chunks == [
        KnowledgeSourceChunk(
            content="Warfarin requires INR monitoring.",
            tokens=5,
            source_uri="memory://00000000-0000-0000-0000-000000000123",
            document_title="Anticoagulation Protocol",
            page_number=2,
        )
    ]


async def test_user_upload_source_reads_stored_text_upload(tmp_path) -> None:
    path = tmp_path / "upload.txt"
    path.write_text("Warfarin requires INR monitoring.", encoding="utf-8")
    source = UserUploadSource(
        path=path,
        mime="text/plain",
        title="Anticoagulation Protocol",
        source_uri="local://kb/protocol.txt",
    )

    chunks = [chunk async for chunk in source.list_chunks(UUID(int=1))]

    assert len(chunks) == 1
    assert chunks[0].content.startswith("Document: Anticoagulation Protocol")
    assert "Warfarin requires INR monitoring." in chunks[0].content
    assert chunks[0].source_uri == "local://kb/protocol.txt"
    assert chunks[0].document_title == "Anticoagulation Protocol"


async def test_dailymed_source_fetches_selected_label_sections() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/dailymed/services/v2/spls.json":
            assert request.url.params["rxcui"] == "29046"
            return httpx.Response(
                200,
                json={
                    "data": [{"setid": "setid-1", "title": "Lisinopril Tablet"}],
                },
            )
        if request.url.path == "/dailymed/services/v2/spls/setid-1.xml":
            return httpx.Response(200, text=_SPL_XML)
        return httpx.Response(404)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://dailymed.nlm.nih.gov",
    ) as http_client:
        source: KnowledgeSource = DailyMedSource(
            client=DailyMedClient(http_client=http_client),
            rxcui="29046",
            drug_name="Lisinopril",
        )
        chunks = [chunk async for chunk in source.list_chunks(UUID(int=1))]

    assert len(chunks) == 2
    assert chunks[0].source_uri == "dailymed://setid-1"
    assert chunks[0].document_title == "Lisinopril Tablet"
    assert chunks[0].section_title == "Warnings and Precautions"
    assert "Monitor for symptomatic hypotension." in chunks[0].content
    assert chunks[1].section_title == "Patient Counseling Information"
    assert "Report dizziness promptly." in chunks[1].content


def test_extract_selected_sections_ignores_non_clinical_label_sections() -> None:
    sections = extract_selected_sections(_SPL_XML)

    assert sections == [
        DailyMedSection(
            title="Warnings and Precautions",
            text="Monitor for symptomatic hypotension.",
        ),
        DailyMedSection(
            title="Patient Counseling Information",
            text="Report dizziness promptly.",
        ),
    ]


_SPL_XML = """
<document xmlns="urn:hl7-org:v3">
  <component>
    <structuredBody>
      <component>
        <section>
          <title>Description</title>
          <text><paragraph>Tablet appearance and chemistry.</paragraph></text>
        </section>
      </component>
      <component>
        <section>
          <title>Warnings and Precautions</title>
          <text><paragraph>Monitor for symptomatic hypotension.</paragraph></text>
        </section>
      </component>
      <component>
        <section>
          <title>Patient Counseling Information</title>
          <text><paragraph>Report dizziness promptly.</paragraph></text>
        </section>
      </component>
    </structuredBody>
  </component>
</document>
"""
