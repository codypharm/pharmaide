"""Evidence lookup for patient food, alcohol, and interaction questions.

The service does not answer the question. It detects when the patient is asking
for interaction-style guidance, builds a medication-scoped retrieval query, and
formats retrieved clinic/DailyMed snippets for the patient-reply draft and
safety-review context.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import structlog
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings import build_embedding_client, embed_texts
from app.services.kb_retrieval import Citation
from app.services.kb_scope import GLOBAL_DAILYMED_SCOPE_ID

log = structlog.get_logger(__name__)

EvidenceStatus = Literal["not_requested", "evidence_found", "no_evidence"]
InteractionEvidenceRetriever = Callable[[str, UUID | None], Awaitable[Sequence[Citation]]]

INTERACTION_TERMS = (
    "alcohol",
    "beer",
    "wine",
    "grapefruit",
    "fruit",
    "food",
    "meal",
    "milk",
    "juice",
    "coffee",
    "tea",
    "interaction",
    "interact",
    "with this",
    "with it",
)


@dataclass(frozen=True, slots=True)
class InteractionEvidence:
    """A retrieved snippet that may ground a patient interaction answer."""

    source_type: Literal["user_upload", "dailymed"]
    document_title: str
    source_uri: str
    text: str
    score: float


@dataclass(frozen=True, slots=True)
class PatientInteractionEvidence:
    """Structured lookup result for one patient message."""

    status: EvidenceStatus
    query: str | None
    citations: tuple[InteractionEvidence, ...]

    @property
    def is_interaction_question(self) -> bool:
        return self.status != "not_requested"


async def lookup_patient_interaction_evidence(
    *,
    patient_message: str,
    medication_names: Sequence[str],
    treatment_id: UUID | None,
    retriever: InteractionEvidenceRetriever | None,
) -> PatientInteractionEvidence:
    """Return retrieved evidence for patient interaction questions."""
    if not is_interaction_question(patient_message):
        return PatientInteractionEvidence(status="not_requested", query=None, citations=())
    query = build_interaction_query(patient_message, medication_names)
    if retriever is None:
        log.info(
            "patient_interaction_evidence_skipped",
            reason="retriever_not_configured",
            treatment_id=str(treatment_id) if treatment_id else None,
        )
        return PatientInteractionEvidence(status="no_evidence", query=query, citations=())

    retrieved = await retriever(query, treatment_id)
    citations = tuple(_evidence_from_citation(citation) for citation in retrieved)
    status: EvidenceStatus = "evidence_found" if citations else "no_evidence"
    log.info(
        "patient_interaction_evidence_lookup_completed",
        treatment_id=str(treatment_id) if treatment_id else None,
        citation_count=len(citations),
        status=status,
    )
    return PatientInteractionEvidence(status=status, query=query, citations=citations)


def is_interaction_question(message: str) -> bool:
    """Detect food, alcohol, fruit, and interaction questions conservatively."""
    normalised = " ".join(message.lower().split())
    return any(term in normalised for term in INTERACTION_TERMS)


def build_interaction_query(patient_message: str, medication_names: Sequence[str]) -> str:
    """Build a retrieval query constrained to the current treatment medications."""
    medication_part = ", ".join(name.strip() for name in medication_names if name.strip())
    return "\n".join(
        [
            "Patient interaction question.",
            f"patient_message: {patient_message.strip()}",
            f"treatment_medications: {medication_part or 'none'}",
            (
                "Find relevant food, alcohol, fruit, contraindication, warning, "
                "or drug interaction evidence."
            ),
        ]
    )


def format_interaction_evidence(evidence: PatientInteractionEvidence) -> str:
    """Format metadata and excerpts for prompts without inventing conclusions."""
    lines = [
        f"interaction_question_detected: {str(evidence.is_interaction_question).lower()}",
        f"interaction_evidence_status: {evidence.status}",
    ]
    if evidence.query:
        lines.append(f"interaction_query: {evidence.query}")
    if not evidence.citations:
        lines.append("citations: none")
        return "\n".join(lines)

    lines.append("citations:")
    for index, citation in enumerate(evidence.citations, start=1):
        lines.extend(
            [
                f"- citation_{index}:",
                f"  source_type: {citation.source_type}",
                f"  document_title: {citation.document_title}",
                f"  source_uri: {citation.source_uri}",
                f"  score: {citation.score:.4f}",
                f"  excerpt: {citation.text}",
            ]
        )
    return "\n".join(lines)


def build_patient_interaction_evidence_retriever(
    session: AsyncSession,
    *,
    openai_api_key: SecretStr | None,
    kb_scope_id: UUID | None,
) -> InteractionEvidenceRetriever | None:
    """Build the configured retrieval seam for patient interaction questions."""
    if openai_api_key is None:
        return None

    async def retriever(query: str, treatment_id: UUID | None) -> Sequence[Citation]:
        embedding_client = build_embedding_client(openai_api_key)

        async def embedder(texts: Sequence[str]) -> list[list[float]]:
            return await embed_texts(texts, client=embedding_client)

        try:
            return await retrieve_for_patient_interaction(
                session,
                query,
                embedder=embedder,
                treatment_id=treatment_id,
                kb_scope_id=kb_scope_id,
            )
        finally:
            await embedding_client.close()

    return retriever


async def retrieve_for_patient_interaction(
    session: AsyncSession,
    query: str,
    *,
    embedder: Callable[[Sequence[str]], Awaitable[list[list[float]]]],
    treatment_id: UUID | None,
    kb_scope_id: UUID | None,
) -> Sequence[Citation]:
    """Retrieve clinic-scoped KB plus global DailyMed evidence."""
    from app.services.kb_retrieval import retrieve

    return await retrieve(
        session,
        query,
        embedder=embedder,
        k=4,
        treatment_id=treatment_id,
        uploaded_by=kb_scope_id or GLOBAL_DAILYMED_SCOPE_ID,
    )


def _evidence_from_citation(citation: Citation) -> InteractionEvidence:
    return InteractionEvidence(
        source_type=citation.source_type,
        document_title=citation.document_title,
        source_uri=citation.source_uri,
        text=citation.text,
        score=citation.score,
    )
