"""Pure purchase-order matching logic.

An invoice is matched to a purchase order by its extracted PO number, falling
back to supplier + amount when no PO number is present. Matched invoices then
have their header and line items compared against the PO within configurable
tolerances. Every difference is a *finding* for human review; the AI never
authorizes payment and a mismatch never auto-rejects an invoice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz

from app.services.duplicate_detection import (
    normalize_invoice_number as normalize_po_number,
)
from app.services.duplicate_detection import normalize_supplier_name

LINE_DESCRIPTION_THRESHOLD = 60.0


@dataclass
class MatchTolerance:
    amount_abs: Decimal = Decimal("0.01")
    amount_pct: Decimal = Decimal("0.01")
    price_pct: Decimal = Decimal("0.02")
    quantity_pct: Decimal = Decimal("0.0")
    supplier_amount_pct: Decimal = Decimal("0.01")


@dataclass
class POLineCandidate:
    line_number: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


@dataclass
class POCandidate:
    purchase_order_id: str
    po_number: str | None = None
    supplier_name: str | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    line_items: list[POLineCandidate] = field(default_factory=list)


@dataclass
class InvoiceForMatch:
    invoice_id: str
    po_number: str | None = None
    supplier_name: str | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    line_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MatchOutcome:
    matched: bool
    purchase_order_id: str | None
    po_number: str | None
    method: str | None
    findings: list[dict[str, Any]] = field(default_factory=list)


def _decimal(val: Any) -> Decimal | None:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return None


def _within(
    actual: Decimal | None,
    expected: Decimal | None,
    *,
    abs_tol: Decimal,
    pct: Decimal,
) -> bool | None:
    """Return ``None`` when either side is unknown, else whether within tolerance."""
    if actual is None or expected is None:
        return None
    diff = abs(actual - expected)
    if diff <= abs_tol:
        return True
    if pct > 0:
        return diff <= abs(expected) * pct
    return False


def _similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return float(fuzz.token_set_ratio(a, b))


def _finding(
    rule_code: str, severity: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "rule_code": rule_code,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def _pair_lines(
    invoice_lines: list[dict[str, Any]],
    po_lines: list[POLineCandidate],
) -> tuple[
    list[tuple[dict[str, Any], POLineCandidate]],
    list[dict[str, Any]],
    list[POLineCandidate],
]:
    """Pair invoice lines with PO lines by line number, then description."""
    remaining_po = list(po_lines)
    remaining_invoice = list(invoice_lines)
    pairs: list[tuple[dict[str, Any], POLineCandidate]] = []

    for inv in list(remaining_invoice):
        inv_number = inv.get("line_number")
        if inv_number is None:
            continue
        for po_line in list(remaining_po):
            if po_line.line_number == inv_number:
                pairs.append((inv, po_line))
                remaining_invoice.remove(inv)
                remaining_po.remove(po_line)
                break

    for inv in list(remaining_invoice):
        best: POLineCandidate | None = None
        best_score = LINE_DESCRIPTION_THRESHOLD
        for po_line in remaining_po:
            score = _similarity(inv.get("description"), po_line.description)
            if score >= best_score:
                best, best_score = po_line, score
        if best is not None:
            pairs.append((inv, best))
            remaining_invoice.remove(inv)
            remaining_po.remove(best)

    return pairs, remaining_invoice, remaining_po


def _compare_header(
    invoice: InvoiceForMatch, po: POCandidate, tolerance: MatchTolerance
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if invoice.currency and po.currency and invoice.currency.upper() != po.currency.upper():
        findings.append(
            _finding(
                "po.currency_mismatch",
                "warning",
                f"Invoice currency {invoice.currency} does not match PO currency "
                f"{po.currency}",
                {"invoice_currency": invoice.currency, "po_currency": po.currency},
            )
        )
    within = _within(
        _decimal(invoice.total_amount),
        _decimal(po.total_amount),
        abs_tol=tolerance.amount_abs,
        pct=tolerance.amount_pct,
    )
    if within is False:
        findings.append(
            _finding(
                "po.total_mismatch",
                "error",
                f"Invoice total {invoice.total_amount} differs from PO total "
                f"{po.total_amount}",
                {
                    "invoice_total": str(invoice.total_amount),
                    "po_total": str(po.total_amount),
                },
            )
        )
    return findings


def _compare_lines(
    pairs: list[tuple[dict[str, Any], POLineCandidate]],
    unmatched_invoice: list[dict[str, Any]],
    unmatched_po: list[POLineCandidate],
    tolerance: MatchTolerance,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for inv, po_line in pairs:
        label = inv.get("description") or po_line.description or f"line {po_line.line_number}"
        quantity_ok = _within(
            _decimal(inv.get("quantity")),
            _decimal(po_line.quantity),
            abs_tol=Decimal("0"),
            pct=tolerance.quantity_pct,
        )
        if quantity_ok is False:
            findings.append(
                _finding(
                    "po.quantity_mismatch",
                    "warning",
                    f"Quantity for {label!r} differs from the PO",
                    {
                        "description": label,
                        "invoice_quantity": str(inv.get("quantity")),
                        "po_quantity": str(po_line.quantity),
                    },
                )
            )
        price_ok = _within(
            _decimal(inv.get("unit_price")),
            _decimal(po_line.unit_price),
            abs_tol=tolerance.amount_abs,
            pct=tolerance.price_pct,
        )
        if price_ok is False:
            findings.append(
                _finding(
                    "po.price_mismatch",
                    "warning",
                    f"Unit price for {label!r} differs from the PO",
                    {
                        "description": label,
                        "invoice_unit_price": str(inv.get("unit_price")),
                        "po_unit_price": str(po_line.unit_price),
                    },
                )
            )
        line_total_ok = _within(
            _decimal(inv.get("line_total")),
            _decimal(po_line.line_total),
            abs_tol=tolerance.amount_abs,
            pct=tolerance.price_pct,
        )
        if line_total_ok is False:
            findings.append(
                _finding(
                    "po.line_total_mismatch",
                    "warning",
                    f"Line total for {label!r} differs from the PO",
                    {
                        "description": label,
                        "invoice_line_total": str(inv.get("line_total")),
                        "po_line_total": str(po_line.line_total),
                    },
                )
            )

    for inv in unmatched_invoice:
        findings.append(
            _finding(
                "po.line_not_on_po",
                "warning",
                f"Invoice line {inv.get('description') or inv.get('line_number')!r} "
                "was not found on the purchase order",
                {"description": inv.get("description"), "line_number": inv.get("line_number")},
            )
        )
    for po_line in unmatched_po:
        findings.append(
            _finding(
                "po.line_not_invoiced",
                "info",
                f"PO line {po_line.description or po_line.line_number!r} was not "
                "invoiced",
                {"description": po_line.description, "line_number": po_line.line_number},
            )
        )
    return findings


def _select_candidate(
    invoice: InvoiceForMatch,
    candidates: list[POCandidate],
    tolerance: MatchTolerance,
) -> tuple[POCandidate | None, str | None]:
    invoice_po = normalize_po_number(invoice.po_number)
    if invoice_po:
        for candidate in candidates:
            if normalize_po_number(candidate.po_number) == invoice_po:
                return candidate, "po_number"
        # An explicit PO number that matches nothing is a mismatch; do not fall
        # back to supplier/amount guessing.
        return None, None

    supplier = normalize_supplier_name(invoice.supplier_name)
    if supplier:
        for candidate in candidates:
            if normalize_supplier_name(candidate.supplier_name) != supplier:
                continue
            within = _within(
                _decimal(invoice.total_amount),
                _decimal(candidate.total_amount),
                abs_tol=tolerance.amount_abs,
                pct=tolerance.supplier_amount_pct,
            )
            if within is not False:
                return candidate, "supplier_amount"
    return None, None


def match_purchase_order(
    invoice: InvoiceForMatch,
    candidates: list[POCandidate],
    tolerance: MatchTolerance | None = None,
) -> MatchOutcome:
    """Match ``invoice`` against ``candidates`` and return findings for review."""
    tolerance = tolerance or MatchTolerance()
    if not candidates:
        return MatchOutcome(
            matched=False,
            purchase_order_id=None,
            po_number=invoice.po_number,
            method=None,
            findings=[
                _finding(
                    "po.not_found",
                    "warning",
                    "No purchase order is available to match against",
                    {"po_number": invoice.po_number},
                )
            ],
        )

    candidate, method = _select_candidate(invoice, candidates, tolerance)
    if candidate is None:
        return MatchOutcome(
            matched=False,
            purchase_order_id=None,
            po_number=invoice.po_number,
            method=None,
            findings=[
                _finding(
                    "po.not_found",
                    "warning",
                    "No matching purchase order was found for this invoice",
                    {
                        "po_number": invoice.po_number,
                        "supplier_name": invoice.supplier_name,
                        "total_amount": str(invoice.total_amount),
                    },
                )
            ],
        )

    findings = _compare_header(invoice, candidate, tolerance)
    pairs, unmatched_invoice, unmatched_po = _pair_lines(
        invoice.line_items, candidate.line_items
    )
    findings.extend(
        _compare_lines(pairs, unmatched_invoice, unmatched_po, tolerance)
    )

    if not findings:
        findings.append(
            _finding(
                "po.matched",
                "info",
                f"Invoice matched purchase order {candidate.po_number}",
                {"method": method, "purchase_order_id": candidate.purchase_order_id},
            )
        )

    return MatchOutcome(
        matched=True,
        purchase_order_id=candidate.purchase_order_id,
        po_number=candidate.po_number,
        method=method,
        findings=findings,
    )


__all__ = [
    "InvoiceForMatch",
    "MatchOutcome",
    "MatchTolerance",
    "POCandidate",
    "POLineCandidate",
    "match_purchase_order",
]
