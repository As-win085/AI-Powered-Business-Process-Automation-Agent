import shutil

import pytest

from app.core.config import settings
from app.services.extraction_service import ExtractionError, extract_pdf_text
from tests.pdf_fixtures import (
    make_blank_pdf,
    make_corrupt_pdf,
    make_digital_pdf,
    make_password_protected_pdf,
)


def _tesseract_available() -> bool:
    command = settings.tesseract_cmd or "tesseract"
    return shutil.which(command) is not None


def test_digital_pdf_extracts_embedded_text_per_page():
    pages = extract_pdf_text(make_digital_pdf())
    assert len(pages) == 2
    for page in pages:
        assert page.source == "embedded"
        assert page.engine == "pymupdf"
        assert "Hello extraction world" in page.text
    assert [page.page_number for page in pages] == [1, 2]


@pytest.mark.skipif(
    not _tesseract_available(),
    reason="Tesseract is not installed on this machine",
)
def test_blank_page_uses_ocr_when_tesseract_available():
    pages = extract_pdf_text(make_blank_pdf())
    assert len(pages) == 1
    assert pages[0].source == "ocr"
    assert pages[0].engine == "tesseract"


def test_password_protected_pdf_is_rejected():
    with pytest.raises(ExtractionError, match="password-protected"):
        extract_pdf_text(make_password_protected_pdf())


def test_corrupt_pdf_is_rejected():
    with pytest.raises(ExtractionError, match="Corrupt"):
        extract_pdf_text(make_corrupt_pdf())


def test_empty_document_is_rejected():
    with pytest.raises(ExtractionError):
        extract_pdf_text(b"")
