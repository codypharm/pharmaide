"""Knowledge-base text segment tests."""

from app.services.kb_segments import TextSegment, clean_text, csv_row_to_segment, render_segment


def test_clean_text_preserves_titles_and_section_headings() -> None:
    raw = "\x00  Anticoagulation Protocol  \n\n\n  Warfarin   initiation\t\nDose:  5 mg\r\n"

    assert clean_text(raw) == "Anticoagulation Protocol\n\nWarfarin initiation\nDose: 5 mg"


def test_render_segment_carries_pdf_context_into_chunk_text() -> None:
    segment = TextSegment(
        kind="text",
        content="Target INR: 2.0-3.0",
        document_title="Anticoagulation Protocol",
        section_title="Warfarin initiation",
        page_number=3,
    )

    assert render_segment(segment) == (
        "Document: Anticoagulation Protocol\n"
        "Section: Warfarin initiation\n"
        "Page: 3\n\n"
        "Target INR: 2.0-3.0"
    )


def test_csv_row_becomes_labeled_record_with_row_context() -> None:
    segment = csv_row_to_segment(
        [" drug ", "dose", "monitoring", "warning", ""],
        [" Warfarin ", "5 mg", "INR weekly", " Avoid NSAIDs ", "ignored note"],
        document_title="Clinic formulary",
        row_number=7,
    )

    assert segment.kind == "csv_row"
    assert segment.row_number == 7
    assert render_segment(segment) == (
        "Document: Clinic formulary\n"
        "Row: 7\n\n"
        "drug: Warfarin\n"
        "dose: 5 mg\n"
        "monitoring: INR weekly\n"
        "warning: Avoid NSAIDs\n"
        "column_5: ignored note"
    )


def test_csv_row_skips_empty_values() -> None:
    segment = csv_row_to_segment(
        ["drug", "dose", "notes"],
        ["Amoxicillin", "", "Take with food"],
    )

    assert segment.content == "drug: Amoxicillin\nnotes: Take with food"
