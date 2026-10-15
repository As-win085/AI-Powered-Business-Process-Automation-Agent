"""Unsupervised anomaly detectors plus a simple statistical baseline.

The primary detector is an :class:`~sklearn.ensemble.IsolationForest` fitted on
supplier-relative invoice features. We also ship a single-feature z-score
baseline so the evaluation script can show whether the multivariate model adds
value over a naive "3-sigma on amount" rule.

``numpy`` and ``scikit-learn`` are imported lazily inside the methods that need
them, so importing this module (and therefore the API) does not require the ML
stack to be installed for unrelated functionality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.anomaly_features import FEATURE_NAMES, to_vector

MODEL_VERSION = "anomaly-iforest-v1"

# Feature index used by the naive baseline: the amount z-score relative to the
# supplier's own history. Index 1 in FEATURE_NAMES.
_BASELINE_FEATURE = "amount_zscore"


def _np():
    import numpy as np

    return np


def precision_recall_f1(
    y_true: list[bool], y_pred: list[bool]
) -> dict[str, float | int]:
    """Confusion-matrix metrics without pulling in ``sklearn.metrics``."""
    true_positive = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t and p)
    false_positive = sum(1 for t, p in zip(y_true, y_pred, strict=True) if not t and p)
    false_negative = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t and not p)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


@dataclass
class AnomalyModel:
    """A fitted Isolation Forest with the metadata needed to score invoices."""

    estimator: Any
    threshold: float
    version: str = MODEL_VERSION
    feature_names: tuple[str, ...] = FEATURE_NAMES
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def train(
        cls,
        vectors: list[list[float]],
        *,
        contamination: float = 0.05,
        flag_percentile: float = 95.0,
        version: str = MODEL_VERSION,
        seed: int = 42,
        n_estimators: int = 200,
    ) -> AnomalyModel:
        if not vectors:
            raise ValueError("cannot train an anomaly model without feature vectors")
        np = _np()
        from sklearn.ensemble import IsolationForest

        matrix = np.asarray(vectors, dtype=float)
        estimator = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=seed,
            n_jobs=1,
        )
        estimator.fit(matrix)
        scores = cls._raw_scores(estimator, matrix)
        threshold = float(np.quantile(scores, flag_percentile / 100.0))
        metadata = {
            "version": version,
            "feature_names": list(FEATURE_NAMES),
            "contamination": contamination,
            "flag_percentile": flag_percentile,
            "seed": seed,
            "n_estimators": n_estimators,
            "n_train": int(matrix.shape[0]),
            "score_threshold": threshold,
        }
        return cls(
            estimator=estimator,
            threshold=threshold,
            version=version,
            metadata=metadata,
        )

    @staticmethod
    def _raw_scores(estimator: Any, matrix: Any) -> Any:
        # score_samples: lower == more anomalous, so negate to make higher mean
        # "more anomalous" (intuitive for thresholds and the API).
        return -estimator.score_samples(matrix)

    def score(self, vectors: list[list[float]]) -> list[float]:
        if not vectors:
            return []
        np = _np()
        scores = self._raw_scores(self.estimator, np.asarray(vectors, dtype=float))
        return [round(float(value), 6) for value in scores]

    def predict(self, vectors: list[list[float]]) -> list[bool]:
        return [value >= self.threshold for value in self.score(vectors)]

    def score_one(self, features: dict[str, float]) -> tuple[float, bool]:
        score = self.score([to_vector(features)])[0]
        return score, score >= self.threshold

    def serialize(self) -> dict[str, Any]:
        """Metadata payload persisted alongside the joblib estimator."""
        return dict(self.metadata)


class ZScoreBaseline:
    """Naive baseline: flag when a supplier-relative z-score exceeds a threshold.

    The default feature (``amount_zscore``) is already expressed in standard
    deviations from the supplier's own mean, so this is simply the familiar
    "3-sigma on amount" rule. It cannot see the frequency or PO features, which
    is exactly the gap the multivariate model is expected to close.
    """

    def __init__(self, feature_name: str = _BASELINE_FEATURE, threshold: float = 3.0) -> None:
        self.feature_name = feature_name
        self.threshold = threshold
        self.index = FEATURE_NAMES.index(feature_name)

    def fit(self, vectors: list[list[float]]) -> ZScoreBaseline:
        return self

    def score(self, vectors: list[list[float]]) -> list[float]:
        return [round(max(0.0, float(row[self.index])), 6) for row in vectors]

    def predict(self, vectors: list[list[float]]) -> list[bool]:
        return [value > self.threshold for value in self.score(vectors)]


class IQRBaseline:
    """Single-feature baseline: flag outside ``median Â± k * IQR`` fences."""

    def __init__(self, feature_name: str = _BASELINE_FEATURE, k: float = 3.0) -> None:
        self.feature_name = feature_name
        self.k = k
        self.index = FEATURE_NAMES.index(feature_name)
        self.q1 = 0.0
        self.q3 = 0.0

    def fit(self, vectors: list[list[float]]) -> IQRBaseline:
        np = _np()
        column = np.asarray(vectors, dtype=float)[:, self.index]
        self.q1 = float(np.quantile(column, 0.25))
        self.q3 = float(np.quantile(column, 0.75))
        return self

    @property
    def _lower(self) -> float:
        return self.q1 - self.k * (self.q3 - self.q1)

    @property
    def _upper(self) -> float:
        return self.q3 + self.k * (self.q3 - self.q1)

    def score(self, vectors: list[list[float]]) -> list[float]:
        np = _np()
        column = np.asarray(vectors, dtype=float)[:, self.index]
        span = (self.q3 - self.q1) or 1.0
        distances = []
        for value in column:
            value = float(value)
            if value > self._upper:
                distances.append((value - self._upper) / span)
            elif value < self._lower:
                distances.append((self._lower - value) / span)
            else:
                distances.append(0.0)
        return [round(value, 6) for value in distances]

    def predict(self, vectors: list[list[float]]) -> list[bool]:
        return [value > 0 for value in self.score(vectors)]


__all__ = [
    "MODEL_VERSION",
    "AnomalyModel",
    "IQRBaseline",
    "ZScoreBaseline",
    "precision_recall_f1",
]
