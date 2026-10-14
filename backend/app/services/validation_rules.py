"""Validation rules for invoices."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any


def _decimal(val: Any) -> Decimal | None:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return None


def required_fields_present(data: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    missing = []
    required = ["invoice_number", "invoice_date", "supplier_name", "currency", "subtotal", "tax_amount", "total_amount"]
    for r in required:
        if data.get(r) is None or (isinstance(data.get(r), str) and data.get(r).strip() == ""):
            missing.append(r)
    if missing:
        return ("required_fields_present", "error", {"missing": missing})
    return ("required_fields_present", "ok", {})


def totals_consistent(data: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    subtotal = _decimal(data.get("subtotal"))
    tax = _decimal(data.get("tax_amount"))
    total = _decimal(data.get("total_amount"))
    if subtotal is None or tax is None or total is None:
        return ("totals_consistent", "warn", {"reason": "missing_values"})
    try:
        expected = subtotal + tax
        if abs(expected - total) > Decimal("0.01"):
            return ("totals_consistent", "error", {"expected": str(expected), "actual": str(total)})
    except Exception:
        return ("totals_consistent", "error", {})
    return ("totals_consistent", "ok", {})


def line_totals_sum(data: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    lines = data.get("line_items") or []
    if not lines:
        return ("line_totals_sum", "ok", {})
    sum_lines = Decimal("0")
    any_bad = False
    for li in lines:
        lt = _decimal(li.get("line_total") if isinstance(li, dict) else None)
        if lt is None:
            any_bad = True
            continue
        sum_lines += lt
    subtotal = _decimal(data.get("subtotal"))
    if subtotal is None:
        return ("line_totals_sum", "warn", {"reason": "missing_subtotal"})
    if any_bad:
        return ("line_totals_sum", "warn", {"reason": "missing_line_totals"})
    if abs(sum_lines - subtotal) > Decimal("0.01"):
        return ("line_totals_sum", "error", {"sum_lines": str(sum_lines), "subtotal": str(subtotal)})
    return ("line_totals_sum", "ok", {})


def valid_currency_and_date(data: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    currency = data.get("currency")
    if currency is None:
        return ("valid_currency_and_date", "error", {"reason": "missing_currency"})
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        return ("valid_currency_and_date", "error", {"reason": "invalid_currency"})
    inv_date = data.get("invoice_date")
    if inv_date is None:
        return ("valid_currency_and_date", "error", {"reason": "missing_date"})
    try:
        if isinstance(inv_date, str):
            d = date.fromisoformat(inv_date.split("T")[0])
        elif isinstance(inv_date, date):
            d = inv_date
        else:
            return ("valid_currency_and_date", "error", {"reason": "invalid_date"})
        if d > date.today():
            return ("valid_currency_and_date", "error", {"reason": "future_date"})
    except Exception:
        return ("valid_currency_and_date", "error", {"reason": "invalid_date"})
    return ("valid_currency_and_date", "ok", {})


def supplier_exists_or_flagged(data: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    # Pure rule: if supplier_name present, ok; else error
    if data.get("supplier_name"):
        return ("supplier_exists_or_flagged", "ok", {})
    return ("supplier_exists_or_flagged", "warn", {"reason": "missing_supplier"})

