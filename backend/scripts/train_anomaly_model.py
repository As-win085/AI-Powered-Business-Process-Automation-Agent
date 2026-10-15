"""Train the Isolation Forest anomaly model on synthetic history and save it.

Usage:
    python scripts/train_anomaly_model.py [--history data/synthetic_history/history.json]

If the history file is missing it is generated first (deterministic seed). The
trained estimator is written to ``storage/models/anomaly`` (inside the storage
root) together with a version + metadata pointer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import get_settings  # noqa: E402
from app.services.anomaly_model_store import save_model  # noqa: E402
from app.services.anomaly_training import build_feature_rows, train_and_evaluate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORY = REPO_ROOT / "data" / "synthetic_history" / "history.json"


def _load_history(path: Path, *, regenerate: bool) -> dict:
    if path.exists() and not regenerate:
        return json.loads(path.read_text(encoding="utf-8"))

    from generate_history import generate_records

    payload = generate_records()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ratio", type=float, default=0.7, help="train fraction (time split)")
    parser.add_argument("--contamination", type=float, default=settings.anomaly_contamination)
    parser.add_argument(
        "--flag-percentile", type=float, default=settings.anomaly_flag_percentile
    )
    parser.add_argument("--regenerate", action="store_true", help="regenerate history first")
    parser.add_argument("--output-dir", type=Path, default=None, help="model directory")
    args = parser.parse_args()

    payload = _load_history(args.history, regenerate=args.regenerate)
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

    path = save_model(result.model, args.output_dir)
    print(f"Trained {result.model.version} on {result.metrics['n_train']} rows")
    print(f"Saved estimator to {path}")
    print(json.dumps(result.metrics, indent=2))


if __name__ == "__main__":
    main()
