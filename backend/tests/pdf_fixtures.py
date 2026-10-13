"""Helpers to build PDF fixtures for extraction tests."""

import io

import fitz
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def make_digital_pdf(text: str = "Hello extraction world", pages: int = 2) -> bytes:
    """A PDF with real selectable text on each page."""
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=A4)
    for page in range(pages):
        document.setFont("Helvetica-Bold", 20)
        document.drawString(72, 740, f"INVOICE {page + 1}")
        document.setFont("Helvetica", 12)
        document.drawString(72, 700, text)
        for line in range(1, 20):
            document.drawString(72, 640 - line * 18, f"Line item {line}: {text}")
        document.showPage()
    document.save()
    return buffer.getvalue()


def make_blank_pdf() -> bytes:
    """A PDF with no selectable text (forces the OCR fallback)."""
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=A4)
    document.setFillColorRGB(0.95, 0.97, 0.98)
    document.rect(50, 50, 495, 742, fill=1, stroke=0)
    document.showPage()
    document.save()
    return buffer.getvalue()


def make_password_protected_pdf() -> bytes:
    """A valid PDF encrypted with a user password."""
    base = make_digital_pdf("secret content", pages=1)
    source = fitz.open(stream=base, filetype="pdf")
    out = io.BytesIO()
    source.save(
        out,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
    )
    source.close()
    return out.getvalue()


def make_corrupt_pdf() -> bytes:
    """A file that passes magic-bytes sniffing but is not a readable PDF."""
    return b"%PDF-1.4\nthis is not a real pdf body"
