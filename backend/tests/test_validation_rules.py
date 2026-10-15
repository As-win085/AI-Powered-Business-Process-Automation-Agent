from datetime import date, timedelta

from app.services import validation_rules as rules


def test_required_fields_present():
    res = rules.required_fields_present({})
    assert res[1] == "error"
    complete = {
        "invoice_number": "1",
        "invoice_date": date.today(),
        "supplier_name": "s",
        "currency": "USD",
        "subtotal": 1,
        "tax_amount": 1,
        "total_amount": 2,
    }
    assert rules.required_fields_present(complete)[1] == "ok"


def test_totals_consistent_rounding_and_negative():
    assert rules.totals_consistent({"subtotal": 0.1, "tax_amount": 0.1, "total_amount": 0.2})[
        1
    ] == "ok"
    assert rules.totals_consistent({"subtotal": -5, "tax_amount": 0, "total_amount": -5})[
        1
    ] == "ok"
    wrong = {"subtotal": 1, "tax_amount": 1, "total_amount": 2.02}
    assert rules.totals_consistent(wrong)[1] == "error"


def test_line_totals_sum():
    items = {"line_items": [{"line_total": 10}], "subtotal": 10}
    mismatch = {"line_items": [{"line_total": 10}], "subtotal": 10.01}
    missing = {"line_items": [{"line_total": None}], "subtotal": 10}
    assert rules.line_totals_sum(items)[1] == "ok"
    assert rules.line_totals_sum(mismatch)[1] == "error"
    assert rules.line_totals_sum(missing)[1] == "warn"


def test_valid_currency_and_date():
    today = date.today()
    assert rules.valid_currency_and_date({"currency": "USD", "invoice_date": today})[1] == "ok"
    assert rules.valid_currency_and_date({"currency": "US", "invoice_date": today})[1] == "error"
    future = today + timedelta(days=1)
    assert rules.valid_currency_and_date({"currency": "USD", "invoice_date": future})[1] == "error"


def test_supplier_exists_or_flagged():
    assert rules.supplier_exists_or_flagged({})[1] == "warn"
    assert rules.supplier_exists_or_flagged({"supplier_name": "x"})[1] == "ok"
