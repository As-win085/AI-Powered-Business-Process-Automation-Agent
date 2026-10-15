"""Persistence for trained anomaly models (joblib estimator + JSON metadata).

Models live under the configured storage root (``storage/models/anomaly``) so a
private/local deployment keeps artefacts inside its own storage boundary. The
estimator is written with joblib and a small ``latest.json`` pointer records
which version is current.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.services.anomaly_detection import AnomalyModel

_LATEST = "latest.json"


def model_dir(directory: Path | None = None) -> Path:
    return Path(directory) if directory is not None else settings.anomaly_model_dir


def save_model(model: AnomalyModel, directory: Path | None = None) -> Path:
    """Persist ``model`` and return the estimator file path."""
    import joblib

    target = model_dir(directory)
    target.mkdir(parents=True, exist_ok=True)

    estimator_path = target / f"model-{model.version}.joblib"
    joblib.dump(model.estimator, estimator_path)

    pointer = {
        "version": model.version,
        "file": estimator_path.name,
        "saved_at": datetime.now(UTC).isoformat(),
        "metadata": model.serialize(),
    }
    (target / _LATEST).write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    return estimator_path


def load_model(directory: Path | None = None) -> AnomalyModel | None:
    """Load the current model, or ``None`` when nothing has been trained yet."""
    import joblib

    target = model_dir(directory)
    pointer_path = target / _LATEST
    if not pointer_path.exists():
        return None

    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    estimator_path = target / pointer["file"]
    if not estimator_path.exists():
        return None

    metadata = pointer.get("metadata", {})
    estimator = joblib.load(estimator_path)
    return AnomalyModel(
        estimator=estimator,
        threshold=float(metadata.get("score_threshold", 0.0)),
        version=pointer.get("version", metadata.get("version", "unknown")),
        metadata=metadata,
    )


def clear_model(directory: Path | None = None) -> None:
    target = model_dir(directory)
    if not target.exists():
        return
    for path in target.glob("*"):
        if path.is_file():
            path.unlink()


__all__ = ["clear_model", "load_model", "model_dir", "save_model"]
