"""Validation engine for invoices."""
from __future__ import annotations

from typing import Any

from app.services import validation_rules as rules

RULES = [
    rules.required_fields_present,
    rules.totals_consistent,
    rules.line_totals_sum,
    rules.valid_currency_and_date,
    rules.supplier_exists_or_flagged,
]


class ValidationEngine:
    def __init__(self, rule_funcs=None):
        self.rule_funcs = rule_funcs or RULES

    def validate(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        for fn in self.rule_funcs:
            try:
                name, severity, details = fn(data)
                results.append(
                    {
                        "rule": name,
                        "severity": severity,
                        "details": details,
                        "pass": severity == "ok",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "rule": getattr(fn, "__name__", "rule"),
                        "severity": "error",
                        "details": {"error": str(exc)},
                        "pass": False,
                    }
                )
        return results

