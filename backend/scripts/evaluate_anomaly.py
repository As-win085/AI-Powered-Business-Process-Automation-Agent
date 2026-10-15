"""Evaluate the anomaly detector against the synthetic, labelled history.

Compares the multivariate Isolation Forest with the naive supplier-relative
z-score ("3-sigma on amount") baseline using a time-based train/test split and
reports precision/recall/F1 plus a per-anomaly-type breakdown.

The labels are synthetic by construction - this measures whether the model learns
the injected patterns and beats a simple baseline, not real-world fraud recall.

Usage:
    python scripts/evaluate_anomaly.py [--history data/synthetic_history/history.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import get_settings  # noqa: E402
from app.services.anomaly_detection import ZScoreBaseline  # noqa: E402
from app.services.anomaly_training import (  # noqa: E402
    build_feature_rows,
    time_split,
    train_and_evaluate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORY = REPO_ROOT / "data" / "synthetic_history" / "history.json"


def _load_history(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    from generate_history import generate_records

    return generate_records()


def _per_type_breakdown(
    test_rows, if_predictions, baseline_predictions
) -> dict[str, dict[str, int]]:
    breakdown: dict[str, dict[str, int]] = {}
    for row, if_hit, base_hit in zip(test_rows, if_predictions, baseline_predictions, strict=True):
        if not row.label:
            continue
        anomaly_type = row.record.get("anomaly_type") or "unknown"
        bucket = breakdown.setdefault(
            anomaly_type, {"count": 0, "if_caught": 0, "baseline_caught": 0}
        )
        bucket["count"] += 1
        bucket["if_caught"] += int(if_hit)
        bucket["baseline_caught"] += int(base_hit)
    return breakdown


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ratio", type=float, default=0.7)
    parser.add_argument("--contamination", type=float, default=settings.anomaly_contamination)
    parser.add_argument(
        "--flag-percentile", type=float, default=settings.anomaly_flag_percentile
    )
    args = parser.parse_args()

    payload = _load_history(args.history)
    rows = build_feature_rows(
        payload["records"], window_days=settings.anomaly_feature_window_days
    )
    result = train_and_evaluate(
        rows,
        contamination=args.contamination,
        flag_percentile=args.flag_percentile,
        seed=args.seed,
        ratio=args.ratio,
    )

    _, test = time_split(rows, args.ratio)
    test_vectors = [row.vector for row in test]
    baseline = ZScoreBaseline().fit([row.vector for row in rows[: int(len(rows) * args.ratio)]])
    if_predictions = result.model.predict(test_vectors)
    baseline_predictions = baseline.predict(test_vectors)

    report = {
        "history": {
            "count": payload["summary"]["count"],
            "anomalies": payload["summary"]["anomaly_count"],
        },
        "split": {
            "train": result.metrics["n_train"],
            "test": result.metrics["n_test"],
            "test_anomalies": result.metrics["n_test_anomalies"],
        },
        "metrics": result.metrics,
        "per_type": _per_type_breakdown(test, if_predictions, baseline_predictions),
    }

    if_m = result.metrics["isolation_forest"]
    base_m = result.metrics["baseline_zscore"]
    print("Anomaly detection evaluation (synthetic labels)")
    print(f"  train={report['split']['train']}  test={report['split']['test']}  "
          f"test_anomalies={report['split']['test_anomalies']}")
    print()
    print(f"  {'detector':<20}{'precision':>10}{'recall':>9}{'f1':>8}")
    print(f"  {'isolation_forest':<20}{if_m['precision']:>10}{if_m['recall']:>9}{if_m['f1']:>8}")
    print(
        f"  {'baseline_zscore':<20}{base_m['precision']:>10}"
        f"{base_m['recall']:>9}{base_m['f1']:>8}"
    )
    print()
    print("  per anomaly type (caught / total):")
    for anomaly_type, counts in sorted(report["per_type"].items()):
        print(
            f"    {anomaly_type:<16} total={counts['count']:<3} "
            f"isolation_forest={counts['if_caught']} baseline={counts['baseline_caught']}"
        )
    print()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
