"""Pure unit tests for anomaly feature engineering and explanation."""
from __future__ import annotations

from datetime import date, timedelta

from app.services.anomaly_features import (
    FEATURE_NAMES,
    NO_PRIOR_DATE,
    average_unit_price,
    compute_history_stats,
    explain,
    extract_features,
    parse_date,
    to_vector,
)


def _history(amounts, *, start=date(2024, 1, 1), unit_price=10.0):
    return [
        {
            "total_amount": amount,
            "invoice_date": (start + timedelta(days=30 * index)).isoformat(),
            "line_items": [{"unit_price": unit_price, "line_total": amount}],
        }
        for index, amount in enumerate(amounts)
    ]


def test_parse_date_handles_iso_and_datetime():
    assert parse_date("2024-03-05") == date(2024, 3, 5)
    assert parse_date("2024-03-05T10:00:00") == date(2024, 3, 5)
    assert parse_date(None) is None
    assert parse_date("not-a-date") is None


def test_average_unit_price_ignores_missing():
    assert average_unit_price([{"unit_price": 10}, {"unit_price": 20}]) == 15
    assert average_unit_price([{"description": "x"}]) is None
    assert average_unit_price(None) is None


def test_history_stats_summarises_totals():
    stats = compute_history_stats(_history([100, 200, 300]))
    assert stats.count == 3
    assert float(stats.median_total) == 200
    assert float(stats.max_total) == 300
    assert len(stats.dates) == 3


def test_extract_features_cold_start_is_neutral():
    features = extract_features(
        amount=1000,
        invoice_date=date(2024, 6, 1),
        line_items=[],
        history=[],
    )
    assert features["amount_to_supplier_median"] == 1.0
    assert features["amount_zscore"] == 0.0
    assert features["amount_to_supplier_max"] == 1.0
    assert features["days_since_last_invoice"] == NO_PRIOR_DATE
    assert features["invoices_last_30_days"] == 0.0
    assert to_vector(features) == [features[name] for name in FEATURE_NAMES]


def test_amount_spike_produces_high_ratio_and_reason():
    history = _history([1000, 1100, 900, 1050, 950], start=date(2024, 1, 1))
    features = extract_features(
        amount=8000,
        invoice_date=date(2024, 7, 1),
        line_items=[{"unit_price": 10}],
        history=history,
    )
    assert features["amount_to_supplier_median"] >= 5
    assert features["amount_zscore"] >= 3
    codes = {reason["code"] for reason in explain(features)}
    assert "amount_vs_median" in codes


def test_frequency_burst_sets_short_window_counters():
    start = date(2024, 5, 1)
    history = [
        {
            "total_amount": 1000,
            "invoice_date": (start + timedelta(days=offset)).isoformat(),
            "line_items": [],
        }
        for offset in (0, 1, 2, 3, 4, 5)
    ]
    features = extract_features(
        amount=1000,
        invoice_date=start + timedelta(days=6),
        line_items=[],
        history=history,
    )
    assert features["invoices_last_7_days"] >= 5
    assert features["days_since_last_invoice"] == 1.0
    codes = {reason["code"] for reason in explain(features)}
    assert "burst" in codes


def test_po_deviation_reason():
    features = extract_features(
        amount=1500,
        invoice_date=date(2024, 6, 1),
        line_items=[],
        history=_history([1000, 1000, 1000]),
        po_total=1000,
    )
    assert abs(features["amount_vs_po_ratio"] - 1.5) < 0.001
    codes = {reason["code"] for reason in explain(features)}
    assert "po_deviation" in codes


def test_unit_price_multiple_reason():
    history = _history([1000, 1000, 1000], unit_price=5.0)
    features = extract_features(
        amount=1000,
        invoice_date=date(2024, 6, 1),
        line_items=[{"unit_price": 50.0}],
        history=history,
    )
    assert features["avg_unit_price_to_median"] == 10.0
    codes = {reason["code"] for reason in explain(features)}
    assert "unit_price" in codes


def test_to_vector_is_stable_length():
    features = extract_features(
        amount=1, invoice_date=None, line_items=[], history=[]
    )
    assert len(to_vector(features)) == len(FEATURE_NAMES)
