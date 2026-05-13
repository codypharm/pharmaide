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


def test_chunk_segments_does_not_overlap_csv_rows() -> None:
    chunks = chunk_segments(
        [
            TextSegment(
                kind="csv_row",
                content="drug: Warfarin dose: 5 mg monitoring: INR weekly warning: avoid NSAIDs",
                document_title="Formulary",
                row_number=7,
            )
        ],
        encoder=_WordEncoder(),
        max_tokens=8,
        overlap_tokens=2,
    )

    assert chunks == [
        ChunkDraft(
            content="Document: Formulary\nRow: 7\n\ndrug: Warfarin dose: 5",
            tokens=8,
            kind="csv_row",
            document_title="Formulary",
            section_title=None,
            page_number=None,
            row_number=7,
        ),
        ChunkDraft(
            content="Document: Formulary\nRow: 7\n\nmg monitoring: INR weekly",
            tokens=8,
            kind="csv_row",
            document_title="Formulary",
            section_title=None,
            page_number=None,
            row_number=7,
        ),
        ChunkDraft(
            content="Document: Formulary\nRow: 7\n\nwarning: avoid NSAIDs",
            tokens=7,
            kind="csv_row",
            document_title="Formulary",
            section_title=None,
            page_number=None,
            row_number=7,
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
