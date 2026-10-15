"""Unit tests for the pure purchase-order matching logic."""
from decimal import Decimal

from app.services.po_matching import (
    InvoiceForMatch,
    MatchTolerance,
    POCandidate,
    POLineCandidate,
    match_purchase_order,
)


def _po(**overrides) -> POCandidate:
    base = {
        "purchase_order_id": "po-1",
        "po_number": "PO-1001",
        "supplier_name": "Acme Supplies Ltd",
        "currency": "USD",
        "total_amount": Decimal("500.00"),
        "line_items": [
            POLineCandidate(
                line_number=1,
                description="Widget",
                quantity=Decimal("10"),
                unit_price=Decimal("50.00"),
                line_total=Decimal("500.00"),
            )
        ],
    }
    base.update(overrides)
    return POCandidate(**base)


def _invoice(**overrides) -> InvoiceForMatch:
    base = {
        "invoice_id": "inv-1",
        "po_number": "PO-1001",
        "supplier_name": "Acme Supplies Ltd",
        "currency": "USD",
        "total_amount": Decimal("500.00"),
        "line_items": [
            {
                "line_number": 1,
                "description": "Widget",
                "quantity": Decimal("10"),
                "unit_price": Decimal("50.00"),
                "line_total": Decimal("500.00"),
            }
        ],
    }
    base.update(overrides)
    return InvoiceForMatch(**base)


def test_matches_cleanly_by_po_number():
    outcome = match_purchase_order(_invoice(), [_po()])
    assert outcome.matched is True
    assert outcome.method == "po_number"
    assert outcome.purchase_order_id == "po-1"
    rules = {f["rule_code"] for f in outcome.findings}
    assert rules == {"po.matched"}


def test_po_number_normalization_ignores_punctuation_and_zeros():
    outcome = match_purchase_order(_invoice(po_number="po 01001"), [_po()])
    assert outcome.matched is True
    assert outcome.method == "po_number"


def test_discrepancies_are_findings_not_rejections():
    invoice = _invoice(
        total_amount=Decimal("600.00"),
        line_items=[
            {
                "line_number": 1,
                "description": "Widget",
                "quantity": Decimal("12"),
                "unit_price": Decimal("50.00"),
                "line_total": Decimal("600.00"),
            }
        ],
    )
    outcome = match_purchase_order(invoice, [_po()])
    assert outcome.matched is True
    rules = {f["rule_code"] for f in outcome.findings}
    assert "po.total_mismatch" in rules
    assert "po.quantity_mismatch" in rules
    assert "po.line_total_mismatch" in rules
    total_finding = next(
        f for f in outcome.findings if f["rule_code"] == "po.total_mismatch"
    )
    assert total_finding["severity"] == "error"


def test_currency_mismatch_is_warning():
    outcome = match_purchase_order(_invoice(currency="EUR"), [_po()])
    rules = {f["rule_code"] for f in outcome.findings}
    assert "po.currency_mismatch" in rules
    finding = next(f for f in outcome.findings if f["rule_code"] == "po.currency_mismatch")
    assert finding["severity"] == "warning"


def test_price_within_tolerance_passes():
    invoice = _invoice(
        line_items=[
            {
                "line_number": 1,
                "description": "Widget",
                "quantity": Decimal("10"),
                "unit_price": Decimal("50.50"),
                "line_total": Decimal("505.00"),
            }
        ],
        total_amount=Decimal("505.00"),
    )
    outcome = match_purchase_order(invoice, [_po(total_amount=Decimal("505.00"))])
    rules = {f["rule_code"] for f in outcome.findings}
    assert "po.price_mismatch" not in rules


def test_falls_back_to_supplier_and_amount_without_po_number():
    outcome = match_purchase_order(_invoice(po_number=None), [_po()])
    assert outcome.matched is True
    assert outcome.method == "supplier_amount"


def test_supplier_amount_fallback_requires_amount_match():
    outcome = match_purchase_order(
        _invoice(po_number=None, total_amount=Decimal("999.00")), [_po()]
    )
    assert outcome.matched is False
    rules = {f["rule_code"] for f in outcome.findings}
    assert rules == {"po.not_found"}


def test_no_candidates_reports_not_found():
    outcome = match_purchase_order(_invoice(), [])
    assert outcome.matched is False
    assert outcome.findings[0]["rule_code"] == "po.not_found"


def test_unknown_po_number_reports_not_found():
    outcome = match_purchase_order(_invoice(po_number="PO-9999"), [_po()])
    assert outcome.matched is False
    assert outcome.purchase_order_id is None


def test_lines_missing_on_each_side_are_reported():
    invoice = _invoice(
        po_number="PO-1001",
        total_amount=Decimal("500.00"),
        line_items=[
            {
                "line_number": 1,
                "description": "Widget",
                "quantity": Decimal("10"),
                "unit_price": Decimal("50.00"),
                "line_total": Decimal("500.00"),
            },
            {
                "line_number": 2,
                "description": "Extra Gadget",
                "quantity": Decimal("1"),
                "unit_price": Decimal("25.00"),
                "line_total": Decimal("25.00"),
            },
        ],
    )
    po = _po(
        line_items=[
            POLineCandidate(
                line_number=1,
                description="Widget",
                quantity=Decimal("10"),
                unit_price=Decimal("50.00"),
                line_total=Decimal("500.00"),
            ),
            POLineCandidate(
                line_number=3,
                description="Never Invoiced",
                quantity=Decimal("2"),
                unit_price=Decimal("10.00"),
                line_total=Decimal("20.00"),
            ),
        ]
    )
    outcome = match_purchase_order(invoice, [po])
    rules = {f["rule_code"] for f in outcome.findings}
    assert "po.line_not_on_po" in rules
    assert "po.line_not_invoiced" in rules


def test_custom_tolerance_can_flag_small_price_delta():
    strict = MatchTolerance(price_pct=Decimal("0.0"), amount_abs=Decimal("0.0001"))
    invoice = _invoice(
        total_amount=Decimal("510.00"),
        line_items=[
            {
                "line_number": 1,
                "description": "Widget",
                "quantity": Decimal("10"),
                "unit_price": Decimal("51.00"),
                "line_total": Decimal("510.00"),
            }
        ],
    )
    outcome = match_purchase_order(invoice, [_po()], strict)
    rules = {f["rule_code"] for f in outcome.findings}
    assert "po.price_mismatch" in rules
