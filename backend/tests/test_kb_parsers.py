"""Knowledge-base parser tests."""

import types

import pytest

from app.services.kb_parsers.csv import parse_csv_segments
from app.services.kb_parsers.pdf import parse_pdf_segments
from app.services.kb_parsers.text import parse_text_segments
from app.services.kb_segments import render_segment


def test_parse_text_segments_returns_clean_document_segment() -> None:
    segments = parse_text_segments(
        b"\xef\xbb\xbf  Anticoagulation Protocol  \n\nWarfarin   initiation\n",
        title=" anticoagulation.txt ",
    )

    assert len(segments) == 1
    assert segments[0].kind == "text"
    assert segments[0].document_title == "anticoagulation.txt"
    assert render_segment(segments[0]) == (
        "Document: anticoagulation.txt\n\n"
        "Anticoagulation Protocol\n\n"
        "Warfarin initiation"
    )


def test_parse_csv_segments_formats_each_row_with_column_labels() -> None:
    segments = parse_csv_segments(
        b"drug,dose,monitoring\nWarfarin,5 mg,INR weekly\nAmoxicillin,500 mg,\n",
        title=" formulary.csv ",
    )

    assert [segment.row_number for segment in segments] == [2, 3]
    assert render_segment(segments[0]) == (
        "Document: formulary.csv\n"
        "Row: 2\n\n"
        "drug: Warfarin\n"
        "dose: 5 mg\n"
        "monitoring: INR weekly"
    )
    assert render_segment(segments[1]) == (
        "Document: formulary.csv\n"
        "Row: 3\n\n"
        "drug: Amoxicillin\n"
        "dose: 500 mg"
    )


def test_parse_pdf_segments_returns_one_clean_segment_per_non_empty_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTextPage:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_text_range(self) -> str:
            return self._text

        def close(self) -> None:
            return None

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_textpage(self) -> FakeTextPage:
            return FakeTextPage(self._text)

        def close(self) -> None:
            return None

    class FakePdfDocument:
        def __init__(self, _: bytes) -> None:
            self._pages = [
                FakePage("  Anticoagulation Protocol  \nWarfarin   initiation  "),
                FakePage(" \n \n "),
                FakePage("Target INR: 2.0-3.0"),
            ]

        def __len__(self) -> int:
            return len(self._pages)

        def __getitem__(self, index: int) -> FakePage:
            return self._pages[index]

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "app.services.kb_parsers.pdf.pdfium",
        types.SimpleNamespace(PdfDocument=FakePdfDocument),
    )

    segments = parse_pdf_segments(b"%PDF-fake", title=" anticoagulation.pdf ")

    assert [segment.page_number for segment in segments] == [1, 3]
    assert render_segment(segments[0]) == (
        "Document: anticoagulation.pdf\n"
        "Page: 1\n\n"
        "Anticoagulation Protocol\n"
        "Warfarin initiation"
    )
    assert render_segment(segments[1]) == (
        "Document: anticoagulation.pdf\n"
        "Page: 3\n\n"
        "Target INR: 2.0-3.0"
    )
