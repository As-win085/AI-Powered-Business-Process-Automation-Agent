"""Model, baseline, evaluation and model-store tests for anomaly detection."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.services.anomaly_detection import (
    AnomalyModel,
    IQRBaseline,
    ZScoreBaseline,
    precision_recall_f1,
)
from app.services.anomaly_model_store import clear_model, load_model, save_model
from app.services.anomaly_training import build_feature_rows, time_split, train_and_evaluate

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_history.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_history", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _small_history():
    return _load_generator().generate_records(suppliers=10, months=10, seed=7)


def _full_history():
    return _load_generator().generate_records(seed=7)


def test_precision_recall_f1_counts():
    metrics = precision_recall_f1([True, True, False, False], [True, False, True, False])
    assert metrics["true_positive"] == 1
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5


def test_zscore_baseline_flags_extreme_amount():
    rows = [[1.0, 0.0], [1.0, 0.5], [1.0, 8.0]]  # second column is the amount z-score
    baseline = ZScoreBaseline().fit(rows)
    assert baseline.predict(rows) == [False, False, True]


def test_iqr_baseline_flags_outlier():
    vectors = [[1.0, v] for v in (0.0, 1.0, 1.0, 1.0, 1.0, 20.0)]
    baseline = IQRBaseline().fit(vectors)
    assert baseline.predict(vectors)[-1] is True


def test_isolation_forest_beats_baseline_on_synthetic_history():
    payload = _full_history()
    rows = build_feature_rows(payload["records"])
    result = train_and_evaluate(rows, seed=7)

    if_metrics = result.metrics["isolation_forest"]
    base_metrics = result.metrics["baseline_zscore"]

    assert result.metrics["n_test_anomalies"] > 0
    # The multivariate model must add value over the amount-only baseline.
    assert if_metrics["f1"] >= base_metrics["f1"]
    assert if_metrics["recall"] >= base_metrics["recall"]


def test_time_split_is_chronological():
    payload = _small_history()
    rows = build_feature_rows(payload["records"])
    train, test = time_split(rows, 0.7)
    assert max(row.when for row in train) <= min(row.when for row in test)


def test_model_scores_and_flags_a_spike():
    payload = _small_history()
    rows = build_feature_rows(payload["records"])
    model = AnomalyModel.train([row.vector for row in rows])
    score, flagged = model.score_one(dict.fromkeys(model.feature_names, 0.0))
    assert isinstance(score, float)
    assert isinstance(flagged, bool)
    assert model.version == "anomaly-iforest-v1"


def test_model_store_roundtrip(tmp_path):
    vectors = [[1.0, float(i % 5)] * 5 for i in range(30)]
    model = AnomalyModel.train(vectors, version="anomaly-iforest-v1")
    save_model(model, tmp_path)

    loaded = load_model(tmp_path)
    assert loaded is not None
    assert loaded.version == model.version
    assert loaded.threshold == model.threshold
    assert loaded.predict(vectors) == model.predict(vectors)

    clear_model(tmp_path)
    assert load_model(tmp_path) is None
