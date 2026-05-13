"""Knowledge-base chunker tests."""

from app.services.chunker import ChunkDraft, chunk_segments
from app.services.kb_segments import TextSegment


class _WordEncoder:
    def encode(self, text: str) -> list[str]:
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        return " ".join(tokens)


def test_chunk_segments_applies_overlap_for_text_segments() -> None:
    chunks = chunk_segments(
        [
            TextSegment(
                kind="text",
                content="one two three four five six seven eight nine ten",
                document_title="Doc",
                section_title="Sec",
                page_number=2,
            )
        ],
        encoder=_WordEncoder(),
        max_tokens=12,
        overlap_tokens=2,
    )

    assert chunks == [
        ChunkDraft(
            content="Document: Doc\nSection: Sec\nPage: 2\n\none two three four five six",
            tokens=12,
            kind="text",
            document_title="Doc",
            section_title="Sec",
            page_number=2,
            row_number=None,
        ),
        ChunkDraft(
            content="Document: Doc\nSection: Sec\nPage: 2\n\nfive six seven eight nine ten",
            tokens=12,
            kind="text",
            document_title="Doc",
            section_title="Sec",
            page_number=2,
            row_number=None,
        ),
    ]


def test_chunk_segments_keeps_csv_row_fields_together_when_they_fit() -> None:
    chunks = chunk_segments(
        [
            TextSegment(
                kind="csv_row",
                content=(
                    "drug: Warfarin\n"
                    "dose: 5 mg\n"
                    "monitoring: INR weekly\n"
                    "warning: avoid NSAIDs"
                ),
                document_title="Formulary",
                row_number=7,
            )
        ],
        encoder=_WordEncoder(),
        max_tokens=20,
        overlap_tokens=2,
    )

    assert chunks == [
        ChunkDraft(
            content=(
                "Document: Formulary\n"
                "Row: 7\n\n"
                "drug: Warfarin\n"
                "dose: 5 mg\n"
                "monitoring: INR weekly\n"
                "warning: avoid NSAIDs"
            ),
            tokens=15,
            kind="csv_row",
            document_title="Formulary",
            section_title=None,
            page_number=None,
            row_number=7,
        ),
    ]


def test_chunk_segments_repeats_csv_label_for_oversized_field() -> None:
    chunks = chunk_segments(
        [
            TextSegment(
                kind="csv_row",
                content="notes: alpha beta gamma delta epsilon zeta",
                document_title="Formulary",
                row_number=8,
            )
        ],
        encoder=_WordEncoder(),
        max_tokens=8,
        overlap_tokens=2,
    )

    assert chunks == [
        ChunkDraft(
            content="Document: Formulary\nRow: 8\n\nnotes: alpha beta gamma",
            tokens=8,
            kind="csv_row",
            document_title="Formulary",
            section_title=None,
            page_number=None,
            row_number=8,
        ),
        ChunkDraft(
            content="Document: Formulary\nRow: 8\n\nnotes: delta epsilon zeta",
            tokens=8,
            kind="csv_row",
            document_title="Formulary",
            section_title=None,
            page_number=None,
            row_number=8,
        ),
    ]


def test_chunk_segments_keeps_paragraph_boundaries_when_blocks_fit() -> None:
    chunks = chunk_segments(
        [
            TextSegment(
                kind="text",
                content=(
                    "alpha one two three\n\n"
                    "beta four five six\n\n"
                    "gamma seven eight nine"
                ),
                document_title="Doc",
            )
        ],
        encoder=_WordEncoder(),
        max_tokens=9,
        overlap_tokens=2,
    )

    assert chunks == [
        ChunkDraft(
            content="Document: Doc\n\nalpha one two three",
            tokens=6,
            kind="text",
            document_title="Doc",
            section_title=None,
            page_number=None,
            row_number=None,
        ),
        ChunkDraft(
            content="Document: Doc\n\nbeta four five six",
            tokens=6,
            kind="text",
            document_title="Doc",
            section_title=None,
            page_number=None,
            row_number=None,
        ),
        ChunkDraft(
            content="Document: Doc\n\ngamma seven eight nine",
            tokens=6,
            kind="text",
            document_title="Doc",
            section_title=None,
            page_number=None,
            row_number=None,
        ),
    ]


def test_chunk_segments_uses_line_boundaries_before_token_windows() -> None:
    chunks = chunk_segments(
        [
            TextSegment(
                kind="text",
                content="alpha one two\nbeta three four\ngamma five six",
                document_title="PDF Guide",
                page_number=4,
            )
        ],
        encoder=_WordEncoder(),
        max_tokens=10,
        overlap_tokens=2,
    )

    assert chunks == [
        ChunkDraft(
            content="Document: PDF Guide\nPage: 4\n\nalpha one two",
            tokens=8,
            kind="text",
            document_title="PDF Guide",
            section_title=None,
            page_number=4,
            row_number=None,
        ),
        ChunkDraft(
            content="Document: PDF Guide\nPage: 4\n\nbeta three four",
            tokens=8,
            kind="text",
            document_title="PDF Guide",
            section_title=None,
            page_number=4,
            row_number=None,
        ),
        ChunkDraft(
            content="Document: PDF Guide\nPage: 4\n\ngamma five six",
            tokens=8,
            kind="text",
            document_title="PDF Guide",
            section_title=None,
            page_number=4,
            row_number=None,
        ),
    ]


def test_chunk_segments_uses_sentence_boundaries_before_token_windows() -> None:
    chunks = chunk_segments(
        [
            TextSegment(
                kind="text",
                content="Take with food. Monitor INR weekly. Avoid NSAIDs.",
                document_title="PDF Guide",
            )
        ],
        encoder=_WordEncoder(),
        max_tokens=7,
        overlap_tokens=2,
    )

    assert chunks == [
        ChunkDraft(
            content="Document: PDF Guide\n\nTake with food.",
            tokens=6,
            kind="text",
            document_title="PDF Guide",
            section_title=None,
            page_number=None,
            row_number=None,
        ),
        ChunkDraft(
            content="Document: PDF Guide\n\nMonitor INR weekly.",
            tokens=6,
            kind="text",
            document_title="PDF Guide",
            section_title=None,
            page_number=None,
            row_number=None,
        ),
        ChunkDraft(
            content="Document: PDF Guide\n\nAvoid NSAIDs.",
            tokens=5,
            kind="text",
            document_title="PDF Guide",
            section_title=None,
            page_number=None,
            row_number=None,
        ),
    ]
