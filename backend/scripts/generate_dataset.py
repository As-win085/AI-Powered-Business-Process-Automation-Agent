"""Generate a synthetic invoice dataset with ground truth for the extraction demo.

Produces ``--count`` PDF invoices with varied suppliers, customers, layouts,
fonts, currencies and line items. For each invoice three variants are written:

- ``digital/<id>.pdf``        - real selectable text (pymupdf path)
- ``scanned/<id>.pdf``        - same invoice rasterized to images (OCR path)
- ``ground_truth/<id>.json``  - the expected extracted fields

A few ``corrupt/<id>.pdf`` files are also written to exercise the failure path.

Usage:
    python scripts/generate_dataset.py [--count 40] [--seed 42]
"""

import argparse
import io
import json
import random
from pathlib import Path

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SUPPLIERS = [
    ("Acme Industrial Supply", "1 Market Street, Springfield, USA"),
    ("Borealis Components GmbH", "Industriestrasse 12, Berlin, Germany"),
    ("Nimbus Trading Co.", "22 Harbour Way, Southampton, UK"),
    ("Vertex Manufacturing Inc", "4400 Lithium Ave, Austin, USA"),
    ("Quanta Office Solutions", "8 Rue de la Paix, Paris, France"),
    ("Helios Food Distributors", "77 Graanmarkt, Amsterdam, Netherlands"),
    ("Zeppelin Electronics", "5-15 Shinbashi, Tokyo, Japan"),
    ("Onyx Construction Materials", "300 Cement Rd, Toronto, Canada"),
    ("Silverline Logistics", "18 Docklands Blvd, Singapore"),
    ("Atlas Power Systems", "66 Grid Street, Mumbai, India"),
]

CUSTOMERS = [
    "Riverside Hotel Group",
    "Bluewater Retail Ltd",
    "Kite Aviation Services",
    "Northbeam Energy LLC",
    "Crystal Peak Resorts",
    "Falcon Freight Co.",
    "Orchard Foods Inc.",
    "Summit Workspaces",
]

ITEM_DESCRIPTIONS = [
    "Stainless steel bolts (box of 500)",
    "Industrial lubricant, 5L drum",
    "Office chair - ergonomic mesh",
    "USB-C docking station",
    "Pallet wraps, 1200m roll",
    "LED panel light 60x60cm",
    "Cable management kit",
    "Safety goggles, ANSI rated",
    "Paper ream A4, 80gsm",
    "Wire shelving unit 4-tier",
    "Heat-resistant gloves, pair",
    "Label printer with 6 rolls",
]

TAX_RATES = [0.00, 0.05, 0.12, 0.18, 0.20, 0.25]

FONTS = ["Helvetica", "Times-Roman", "Courier"]

ACCENTS = [
    colors.HexColor("#1f4e79"),
    colors.HexColor("#7a1f42"),
    colors.HexColor("#14532d"),
    colors.HexColor("#7c3f00"),
    colors.HexColor("#3b0764"),
]


def _rand_invoice(rng: random.Random, supplier: tuple[str, str], customer: str, index: int) -> dict:
    year = rng.choice([2024, 2025, 2026])
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    invoice_date = f"{year:04d}-{month:02d}-{day:02d}"

    late_days = rng.randint(14, 45)
    due = f"{year:04d}-{(month + late_days - 1) % 12 + 1:02d}-{day:02d}"

    line_items = []
    for _ in range(rng.randint(2, 6)):
        description = rng.choice(ITEM_DESCRIPTIONS)
        quantity = rng.randint(1, 40)
        unit_price = round(rng.uniform(5, 500), 2)
        tax_rate = rng.choice(TAX_RATES)
        line_total = round(quantity * unit_price, 2)
        line_items.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "tax_rate": tax_rate,
                "line_total": line_total,
            }
        )

    subtotal = round(sum(item["line_total"] for item in line_items), 2)
    tax_total = round(
        sum(item["line_total"] * item["tax_rate"] for item in line_items), 2
    )
    total = round(subtotal + tax_total, 2)

    return {
        "id": index,
        "supplier": {"name": supplier[0], "address": supplier[1]},
        "customer": customer,
        "invoice_number": f"INV-{year}-{index:04d}",
        "invoice_date": invoice_date,
        "due_date": due,
        "currency": "USD",
        "subtotal": subtotal,
        "tax_total": tax_total,
        "total": total,
        "line_items": line_items,
    }


def _build_invoice_pdf(invoice: dict, layout: int, font: str, accent: colors.Color) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName=font,
        fontSize=9.5,
        textColor=colors.HexColor("#222222"),
    )
    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=8,
        textColor=colors.HexColor("#555555"),
    )
    title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName=font,
        fontSize=22,
        textColor=accent,
    )

    supplier = invoice["supplier"]
    story: list = []

    if layout == 0:
        header = Table(
            [
                [
                    Paragraph(f"<b>{supplier['name']}</b>", body),
                    Paragraph("INVOICE", title),
                ],
                [
                    Paragraph(supplier["address"], small),
                    Paragraph(invoice["invoice_number"], body),
                ],
            ],
            colWidths=[90 * mm, 70 * mm],
        )
        header.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.2, accent),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(header)
    else:
        banner = Table(
            [
                [
                    Paragraph(
                        f"<font color='white'><b>{supplier['name']}</b></font>", body
                    ),
                    Paragraph(
                        f"<font color='white'><b>INVOICE</b></font>", title
                    ),
                ]
            ],
            colWidths=[90 * mm, 70 * mm],
        )
        banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), accent),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(banner)
    story.append(Spacer(1, 6))

    meta = Table(
        [
            [Paragraph("<b>Bill To</b>", body), Paragraph("Invoice date", small), Paragraph("Due date", small)],
            [
                Paragraph(invoice["customer"], body),
                Paragraph(invoice["invoice_date"], body),
                Paragraph(invoice["due_date"], body),
            ],
        ],
        colWidths=[70 * mm, 45 * mm, 45 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 8))

    rows = [
        [
            Paragraph("<b>Description</b>", body),
            Paragraph("<b>Qty</b>", body),
            Paragraph("<b>Unit price</b>", body),
            Paragraph("<b>Tax</b>", body),
            Paragraph("<b>Amount</b>", body),
        ]
    ]
    for item in invoice["line_items"]:
        rows.append(
            [
                Paragraph(item["description"], body),
                Paragraph(str(item["quantity"]), body),
                Paragraph(f"{item['unit_price']:.2f}", body),
                Paragraph(f"{item['tax_rate']:.0%}", body),
                Paragraph(f"{item['line_total']:.2f}", body),
            ]
        )

    table = Table(rows, colWidths=[80 * mm, 15 * mm, 25 * mm, 15 * mm, 25 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), accent),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 1), (-1, -1), 0.4, colors.HexColor("#d0d0d0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 10))

    totals_rows = [
        ["Subtotal", f"{invoice['subtotal']:.2f}"],
        ["Tax total", f"{invoice['tax_total']:.2f}"],
        ["Grand total", f"USD {invoice['total']:.2f}"],
    ]
    totals = Table(totals_rows, colWidths=[50 * mm, 40 * mm])
    totals.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, -1), (1, -1), "Helvetica-Bold"),
                ("SIZE", (0, -1), (1, -1), 11),
                ("LINEABOVE", (0, -1), (1, -1), 1.2, accent),
                ("TOPPADDING", (0, -1), (1, -1), 4),
            ]
        )
    )
    story.append(totals)

    story.append(Spacer(1, 14))
    footer = Paragraph(
        "Payment terms: net 30 days. Thank you for your business.", small
    )
    story.append(footer)

    document.build(story)
    return buffer.getvalue()


def _to_scanned(content: bytes, dpi: int = 150) -> bytes:
    """Rasterize every page into an image-only PDF (no selectable text)."""
    source = fitz.open(stream=content, filetype="pdf")
    out = fitz.open()
    try:
        for page in source:
            pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, annots=True)
            new_page = out.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, pixmap=pixmap)
        buffer = io.BytesIO()
        out.save(buffer, garbage=4, deflate=True)
        return buffer.getvalue()
    finally:
        source.close()
        out.close()


def _to_corrupt(content: bytes) -> bytes:
    """Keep the ``%PDF-`` header but drop most of the body so parsing fails."""
    return content[: max(1, int(len(content) * 0.4))]


def generate(
    count: int,
    seed: int,
    output_dir: Path,
) -> None:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    digital_dir = output_dir / "digital"
    scanned_dir = output_dir / "scanned"
    truth_dir = output_dir / "ground_truth"
    corrupt_dir = output_dir / "corrupt"
    for directory in (digital_dir, scanned_dir, truth_dir, corrupt_dir):
        directory.mkdir(exist_ok=True)

    processed_ids: list[dict] = []
    for index in range(count):
        supplier = rng.choice(SUPPLIERS)
        customer = rng.choice(CUSTOMERS)
        invoice = _rand_invoice(rng, supplier, customer, index)
        layout = rng.randint(0, 1)
        font = rng.choice(FONTS)
        accent = rng.choice(ACCENTS)

        identifier = f"{index:05d}-{invoice['invoice_number']}"
        digital = _build_invoice_pdf(invoice, layout, font, accent)
        scanned = _to_scanned(digital)

        (digital_dir / f"{identifier}.pdf").write_bytes(digital)
        (scanned_dir / f"{identifier}.pdf").write_bytes(scanned)
        (truth_dir / f"{identifier}.json").write_text(
            json.dumps(invoice, indent=2), encoding="utf-8"
        )

        if index % 13 == 0:
            corrupt_id = f"{identifier}-corrupt"
            (corrupt_dir / f"{corrupt_id}.pdf").write_bytes(_to_corrupt(digital))

        processed_ids.append(
            {
                "id": identifier,
                "invoice_number": invoice["invoice_number"],
                "total": invoice["total"],
                "digital": digital,
                "scanned": scanned,
            }
        )

    manifest = {
        "count": count,
        "seed": seed,
        "vendor": "reportlab/fitz",
        "records": [
            {
                "id": record["id"],
                "invoice_number": record["invoice_number"],
                "total": record["total"],
            }
            for record in processed_ids
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    for record in processed_ids:
        print(
            f"{record['id']:>34}  digital={len(record['digital']):,}B  "
            f"scanned={len(record['scanned']):,}B"
        )
    print(f"\nWrote {count} invoices with ground truth to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=40, help="number of invoices")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "synthetic_invoices",
        help="output directory (default: <repo>/data/synthetic_invoices)",
    )
    args = parser.parse_args()
    generate(args.count, args.seed, args.output_dir)


if __name__ == "__main__":
    main()