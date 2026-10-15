"""Feature engineering and explanation for invoice anomaly detection.

Everything here is pure and deterministic: given an invoice and that supplier's
prior history we produce a numeric feature vector plus human-readable reasons.
No machine-learning library is imported, so the logic is cheap to unit test.

The features deliberately describe an invoice *relative to its supplier's own
history* (rather than an absolute amount), which is what lets the model surface
unusual spend without penalising simply large suppliers.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

FEATURE_NAMES = (
    "amount_to_supplier_median",
    "amount_zscore",
    "amount_to_supplier_max",
    "days_since_last_invoice",
    "invoices_last_7_days",
    "invoices_last_30_days",
    "supplier_invoice_count_log",
    "amount_vs_po_ratio",
    "avg_unit_price_to_median",
    "line_item_count",
)

NO_PRIOR_DATE = 365.0

# Reason thresholds (kept here so the explanation and the tests share them).
AMOUNT_MEDIAN_MULTIPLE = 2.0
AMOUNT_ZSCORE = 3.0
AMOUNT_MAX_MULTIPLE = 1.5
BURST_7D = 4
FREQUENCY_30D = 8
RECENT_DAYS = 2
PO_DEVIATION_PCT = 20.0
UNIT_PRICE_MULTIPLE = 2.0


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).split("T")[0])
    except Exception:
        return None


# Public alias for other modules (kept once so the parsing rules stay identical).
parse_date = _as_date


def average_unit_price(line_items: list[dict[str, Any]] | None) -> Decimal | None:
    """Average of the per-line unit prices, ignoring lines without one."""
    prices = [
        price
        for item in (line_items or [])
        if (price := _decimal(item.get("unit_price") if isinstance(item, dict) else None))
        is not None
    ]
    if not prices:
        return None
    return sum(prices) / Decimal(len(prices))


@dataclass
class HistoryStats:
    count: int = 0
    median_total: Decimal | None = None
    mean_total: Decimal | None = None
    std_total: Decimal | None = None
    max_total: Decimal | None = None
    median_unit_price: Decimal | None = None
    dates: list[date] = field(default_factory=list)


def compute_history_stats(history: list[dict[str, Any]]) -> HistoryStats:
    """Aggregate prior invoices for a single supplier into summary statistics."""
    totals = [t for item in history if (t := _decimal(item.get("total_amount"))) is not None]
    unit_prices = [
        up
        for item in history
        if (up := average_unit_price(item.get("line_items"))) is not None
    ]
    dates = sorted(
        d for item in history if (d := _as_date(item.get("invoice_date"))) is not None
    )
    stats = HistoryStats(count=len(totals), dates=dates)
    if totals:
        stats.median_total = Decimal(str(statistics.median(totals)))
        stats.mean_total = Decimal(str(statistics.fmean(totals)))
        stats.max_total = max(totals)
        stats.std_total = (
            Decimal(str(statistics.pstdev(totals))) if len(totals) >= 2 else Decimal("0")
        )
    if unit_prices:
        stats.median_unit_price = Decimal(str(statistics.median(unit_prices)))
    return stats


def _safe_ratio(numerator: Decimal | None, denominator: Decimal | None) -> float:
    if numerator is None or denominator is None or denominator == 0:
        return 1.0
    return float(numerator / denominator)


def extract_features(
    *,
    amount: Any,
    invoice_date: Any,
    line_items: list[dict[str, Any]] | None,
    history: list[dict[str, Any]] | None = None,
    po_total: Any = None,
    window_days: int = 30,
) -> dict[str, float]:
    """Build the anomaly feature vector for one invoice.

    ``history`` contains this supplier's *prior* invoices (same schema as the
    synthetic generator / serialized invoice records). Cold-start invoices fall
    back to neutral values so the model never sees ``NaN``.
    """
    history = history or []
    stats = compute_history_stats(history)
    total = _decimal(amount)
    inv_date = _as_date(invoice_date)
    po = _decimal(po_total)

    features = {
        "amount_to_supplier_median": _safe_ratio(total, stats.median_total),
        "amount_zscore": 0.0,
        "amount_to_supplier_max": _safe_ratio(total, stats.max_total),
        "days_since_last_invoice": NO_PRIOR_DATE,
        "invoices_last_7_days": 0.0,
        "invoices_last_30_days": 0.0,
        "supplier_invoice_count_log": math.log1p(stats.count),
        "amount_vs_po_ratio": _safe_ratio(total, po),
        "avg_unit_price_to_median": 1.0,
        "line_item_count": float(len(line_items or [])),
    }

    if total is not None and stats.std_total and stats.std_total > 0:
        features["amount_zscore"] = float((total - stats.mean_total) / stats.std_total)

    if stats.dates and inv_date is not None:
        last = max(stats.dates)
        features["days_since_last_invoice"] = float(max(0, (inv_date - last).days))
        features["invoices_last_7_days"] = float(
            sum(1 for d in stats.dates if 0 <= (inv_date - d).days <= 7)
        )
        features["invoices_last_30_days"] = float(
            sum(1 for d in stats.dates if 0 <= (inv_date - d).days <= window_days)
        )

    avg_unit = average_unit_price(line_items)
    if avg_unit is not None and stats.median_unit_price:
        features["avg_unit_price_to_median"] = float(avg_unit / stats.median_unit_price)

    return features


def to_vector(features: dict[str, float]) -> list[float]:
    """Return the feature vector in the canonical :data:`FEATURE_NAMES` order."""
    return [float(features.get(name, 0.0)) for name in FEATURE_NAMES]


def explain(features: dict[str, float]) -> list[dict[str, Any]]:
    """Turn a feature vector into the reasons a human reviewer can act on."""
    reasons: list[dict[str, Any]] = []

    ratio = features.get("amount_to_supplier_median", 1.0)
    if ratio >= AMOUNT_MEDIAN_MULTIPLE:
        reasons.append(
            {
                "code": "amount_vs_median",
                "message": f"amount is {ratio:.1f}× the supplier median",
                "detail": {"amount_to_supplier_median": round(ratio, 3)},
            }
        )

    zscore = features.get("amount_zscore", 0.0)
    if zscore >= AMOUNT_ZSCORE:
        reasons.append(
            {
                "code": "amount_zscore",
                "message": (
                    f"amount is {zscore:.1f} standard deviations above the "
                    "supplier's typical spend"
                ),
                "detail": {"amount_zscore": round(zscore, 3)},
            }
        )

    max_ratio = features.get("amount_to_supplier_max", 1.0)
    if max_ratio >= AMOUNT_MAX_MULTIPLE:
        reasons.append(
            {
                "code": "amount_vs_max",
                "message": f"amount is {max_ratio:.1f}× the supplier's largest prior invoice",
                "detail": {"amount_to_supplier_max": round(max_ratio, 3)},
            }
        )

    frequency = features.get("invoices_last_30_days", 0.0)
    if frequency >= FREQUENCY_30D:
        reasons.append(
            {
                "code": "frequency",
                "message": (
                    f"unusually high frequency: {int(frequency)} invoices from this "
                    "supplier in the last 30 days"
                ),
                "detail": {"invoices_last_30_days": int(frequency)},
            }
        )

    burst = features.get("invoices_last_7_days", 0.0)
    if burst >= BURST_7D:
        reasons.append(
            {
                "code": "burst",
                "message": (
                    f"burst detected: {int(burst)} invoices from this supplier in the "
                    "last 7 days"
                ),
                "detail": {"invoices_last_7_days": int(burst)},
            }
        )

    days_since = features.get("days_since_last_invoice", NO_PRIOR_DATE)
    if day_gap_applicable(days_since, features):
        reasons.append(
            {
                "code": "recent_invoice",
                "message": (
                    f"only {int(days_since)} day(s) since the supplier's previous invoice"
                ),
                "detail": {"days_since_last_invoice": int(days_since)},
            }
        )

    po_ratio = features.get("amount_vs_po_ratio", 1.0)
    if abs(po_ratio - 1.0) * 100.0 >= PO_DEVIATION_PCT:
        direction = "above" if po_ratio > 1 else "below"
        reasons.append(
            {
                "code": "po_deviation",
                "message": (
                    f"amount is {abs(po_ratio - 1.0) * 100:.0f}% {direction} the linked "
                    "purchase order total"
                ),
                "detail": {"amount_vs_po_ratio": round(po_ratio, 3)},
            }
        )

    unit_ratio = features.get("avg_unit_price_to_median", 1.0)
    if unit_ratio >= UNIT_PRICE_MULTIPLE:
        reasons.append(
            {
                "code": "unit_price",
                "message": f"average unit price is {unit_ratio:.1f}× the supplier's typical price",
                "detail": {"avg_unit_price_to_median": round(unit_ratio, 3)},
            }
        )

    return reasons


def day_gap_applicable(days_since: float, features: dict[str, float]) -> bool:
    """Only call out a short gap once the supplier has an established cadence."""
    return (
        days_since <= RECENT_DAYS
        and days_since < NO_PRIOR_DATE
        and features.get("supplier_invoice_count_log", 0.0) >= math.log1p(5)
    )


__all__ = [
    "AMOUNT_MEDIAN_MULTIPLE",
    "FEATURE_NAMES",
    "NO_PRIOR_DATE",
    "HistoryStats",
    "average_unit_price",
    "compute_history_stats",
    "explain",
    "extract_features",
    "parse_date",
    "to_vector",
]
