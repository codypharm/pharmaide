"""Prescription upload guard before any model call sees file bytes."""

import io
from dataclasses import dataclass

import pypdfium2 as pdfium

MAX_PRESCRIPTION_IMAGE_BYTES = 10 * 1024 * 1024

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
PDF_SIGNATURE = b"%PDF-"


@dataclass(frozen=True)
class GuardedImage:
    """Image bytes accepted for prescription extraction."""

    data: bytes
    media_type: str
    size_bytes: int


class ImageGuardError(ValueError):
    """Raised when an upload is unsafe or unsupported for extraction."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_prescription_image(
    data: bytes,
    *,
    declared_mime: str | None = None,
    max_bytes: int = MAX_PRESCRIPTION_IMAGE_BYTES,
) -> GuardedImage:
    """Validate upload bytes and return a model-ready image payload.

    The declared MIME is intentionally advisory. Browser-provided content types
    are easy to spoof, so the guard accepts only formats proven by magic bytes.
    """
    size_bytes = len(data)
    if size_bytes == 0:
        raise ImageGuardError("image_empty", "Prescription image is empty.")
    if size_bytes > max_bytes:
        raise ImageGuardError("image_too_large", "Prescription image exceeds the 10 MB limit.")

    detected_mime = _detect_mime(data)
    if detected_mime == "application/pdf":
        return _render_pdf_first_page(data)
    if detected_mime is None:
        raise ImageGuardError(
            "unsupported_image_type",
            "Prescription upload must be a PNG or JPEG image.",
        )

    return GuardedImage(data=data, media_type=detected_mime, size_bytes=size_bytes)


def _detect_mime(data: bytes) -> str | None:
    if data.startswith(PNG_SIGNATURE):
        return "image/png"
    if data.startswith(JPEG_SIGNATURE):
        return "image/jpeg"
    if data.startswith(PDF_SIGNATURE):
        return "application/pdf"
    return None


def _render_pdf_first_page(data: bytes) -> GuardedImage:
    try:
        document = pdfium.PdfDocument(data)
        if len(document) == 0:
            raise ImageGuardError("pdf_empty", "Prescription PDF does not contain any pages.")
        page = document[0]
        bitmap = page.render(scale=2)
        image = bitmap.to_pil()
        output = io.BytesIO()
        image.save(output, format="PNG")
    except ImageGuardError:
        raise
    except Exception as exc:
        raise ImageGuardError(
            "pdf_render_failed",
            "Prescription PDF could not be rendered for extraction.",
        ) from exc

    png_bytes = output.getvalue()
    return GuardedImage(
        data=png_bytes,
        media_type="image/png",
        size_bytes=len(png_bytes),
    )
