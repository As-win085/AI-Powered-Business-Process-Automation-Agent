"""Training and evaluation helpers for the anomaly detector.

Feature rows are built in chronological order using only each supplier's *prior*
invoices, then split by time (older rows train, newer rows test) so evaluation
never leaks future information. The Isolation Forest is compared against the
single-feature z-score baseline on the held-out period.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.anomaly_detection import (
    AnomalyModel,
    ZScoreBaseline,
    precision_recall_f1,
)
from app.services.anomaly_features import extract_features, parse_date, to_vector


@dataclass
class FeatureRow:
    record: dict[str, Any]
    features: dict[str, float]
    vector: list[float]
    label: bool
    when: date | None


@dataclass
class TrainingResult:
    model: AnomalyModel
    metrics: dict[str, Any]


def build_feature_rows(
    records: list[dict[str, Any]], *, window_days: int = 30
) -> list[FeatureRow]:
    """Compute supplier-relative features for every record, chronologically."""
    ordered = sorted(
        records, key=lambda r: parse_date(r.get("invoice_date")) or date.min
    )
    history: dict[str, list[dict[str, Any]]] = {}
    rows: list[FeatureRow] = []
    for record in ordered:
        supplier = str(record.get("supplier") or record.get("supplier_name") or "")
        prior = history.setdefault(supplier, [])
        features = extract_features(
            amount=record.get("total_amount"),
            invoice_date=record.get("invoice_date"),
            line_items=record.get("line_items"),
            history=prior,
            po_total=record.get("po_total"),
            window_days=window_days,
        )
        rows.append(
            FeatureRow(
                record=record,
                features=features,
                vector=to_vector(features),
                label=bool(record.get("is_anomaly", False)),
                when=parse_date(record.get("invoice_date")),
            )
        )
        prior.append(record)
    return rows


def time_split(
    rows: list[FeatureRow], ratio: float = 0.7
) -> tuple[list[FeatureRow], list[FeatureRow]]:
    if not rows:
        raise ValueError("no feature rows to split")
    cut = int(len(rows) * ratio)
    cut = max(1, min(cut, len(rows) - 1)) if len(rows) > 1 else len(rows)
    return rows[:cut], rows[cut:]


def train_and_evaluate(
    rows: list[FeatureRow],
    *,
    contamination: float = 0.05,
    flag_percentile: float = 90.0,
    seed: int = 42,
    version: str = "anomaly-iforest-v1",
    ratio: float = 0.7,
) -> TrainingResult:
    train, test = time_split(rows, ratio)
    model = AnomalyModel.train(
        [row.vector for row in train],
        contamination=contamination,
        flag_percentile=flag_percentile,
        version=version,
        seed=seed,
    )

    y_test = [row.label for row in test]
    test_vectors = [row.vector for row in test]

    if_metrics = precision_recall_f1(y_test, model.predict(test_vectors))

    baseline = ZScoreBaseline().fit([row.vector for row in train])
    baseline_metrics = precision_recall_f1(y_test, baseline.predict(test_vectors))

    metrics = {
        "n_train": len(train),
        "n_test": len(test),
        "n_test_anomalies": sum(1 for row in test if row.label),
        "threshold": round(model.threshold, 6),
        "isolation_forest": if_metrics,
        "baseline_zscore": baseline_metrics,
    }
    return TrainingResult(model=model, metrics=metrics)


__all__ = ["FeatureRow", "TrainingResult", "build_feature_rows", "time_split", "train_and_evaluate"]
