"""PDF text extraction with OCR fallback.

Strategy per page:
1. Try embedded (selectable) text via PyMuPDF.
2. If there is too little text, render the page to an image and run Tesseract.
3. Raise ExtractionError if a page yields nothing usable so callers can mark the
   document as failed with a reason.
"""

import io
from dataclasses import dataclass

import fitz
import pytesseract
from PIL import Image

from app.core.config import settings
from app.core.exceptions import ValidationError

MIN_EMBEDDED_TEXT = 20


class ExtractionError(ValidationError):
    """Raised when a document cannot be processed for an explainable reason."""


@dataclass
class PageTextResult:
    page_number: int
    text: str
    source: str  # "embedded" | "ocr"
    engine: str  # "pymupdf" | "tesseract"


def extract_pdf_text(content: bytes) -> list[PageTextResult]:
    """Extract per-page text from ``content``, falling back to OCR as needed.

    Raises ExtractionError for corrupted, password-protected or unreadable PDFs
    and for documents that yield no text at all.
    """
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - normalize every fitz failure
        raise ExtractionError(f"Corrupt or unreadable PDF file: {exc}") from exc

    try:
        if document.needs_pass:
            raise ExtractionError("The PDF is password-protected and cannot be read")
        if document.page_count == 0:
            raise ExtractionError("The PDF contains no pages")
        if document.page_count > settings.ocr_max_pages:
            raise ExtractionError(
                f"The PDF has {document.page_count} pages; the limit is {settings.ocr_max_pages}"
            )
    except ExtractionError:
        document.close()
        raise
    except Exception as exc:  # noqa: BLE001
        document.close()
        raise ExtractionError(f"Corrupt or unreadable PDF file: {exc}") from exc

    pages: list[PageTextResult] = []
    try:
        for number in range(document.page_count):
            page = document.load_page(number)
            embedded = (page.get_text("text") or "").strip()
            if len(embedded) >= MIN_EMBEDDED_TEXT:
                pages.append(
                    PageTextResult(
                        page_number=number + 1,
                        text=embedded,
                        source="embedded",
                        engine="pymupdf",
                    )
                )
                continue

            ocr_text = _ocr_page(page)
            if not ocr_text.strip():
                raise ExtractionError(
                    f"Page {number + 1} has no selectable text and OCR produced no output"
                )
            pages.append(
                PageTextResult(
                    page_number=number + 1,
                    text=ocr_text,
                    source="ocr",
                    engine="tesseract",
                )
            )
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Failed to extract text: {exc}") from exc
    finally:
        document.close()

    if not pages:
        raise ExtractionError("No extractable text found in the document")
    return pages


def _configure_tesseract() -> None:
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def _ocr_page(page: fitz.Page) -> str:
    if settings.ocr_engine != "tesseract":
        raise ExtractionError(f"Unsupported OCR engine: {settings.ocr_engine}")
    _configure_tesseract()
    try:
        pixmap = page.get_pixmap(dpi=settings.ocr_dpi)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang=settings.ocr_languages).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise ExtractionError("OCR engine (Tesseract) is not installed on this server") from exc
    except Exception as exc:  # noqa: BLE001 - normalize OCR failures
        raise ExtractionError(f"OCR failed on a scanned page: {exc}") from exc
