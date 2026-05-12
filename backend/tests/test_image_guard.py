"""Image upload validation for prescription extraction."""

import io

import pypdfium2 as pdfium
import pytest

from app.services.image_guard import ImageGuardError, validate_prescription_image


def test_validate_prescription_image_accepts_png_by_magic_bytes() -> None:
    data = b"\x89PNG\r\n\x1a\nfake-png-body"
    image = validate_prescription_image(
        data,
        declared_mime="application/octet-stream",
    )

    assert image.data == data
    assert image.media_type == "image/png"
    assert image.size_bytes == len(data)


def test_validate_prescription_image_accepts_jpeg_by_magic_bytes() -> None:
    image = validate_prescription_image(
        b"\xff\xd8\xff\xe0fake-jpeg-body",
        declared_mime="image/jpeg",
    )

    assert image.media_type == "image/jpeg"


def test_validate_prescription_image_rejects_oversized_upload() -> None:
    with pytest.raises(ImageGuardError) as exc_info:
        validate_prescription_image(b"x" * (10 * 1024 * 1024 + 1))

    assert exc_info.value.code == "image_too_large"


def test_validate_prescription_image_rejects_mime_spoofing() -> None:
    with pytest.raises(ImageGuardError) as exc_info:
        validate_prescription_image(
            b"not really an image",
            declared_mime="image/png",
        )

    assert exc_info.value.code == "unsupported_image_type"


def test_validate_prescription_image_renders_pdf_first_page_to_png() -> None:
    image = validate_prescription_image(
        _single_page_pdf(),
        declared_mime="application/pdf",
    )

    assert image.media_type == "image/png"
    assert image.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert image.size_bytes == len(image.data)


def test_validate_prescription_image_rejects_invalid_pdf() -> None:
    with pytest.raises(ImageGuardError) as exc_info:
        validate_prescription_image(b"%PDF-1.7\nnot a complete pdf")

    assert exc_info.value.code == "pdf_render_failed"


def _single_page_pdf() -> bytes:
    document = pdfium.PdfDocument.new()
    document.new_page(200, 100)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()
