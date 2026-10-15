"""Evaluation-level tests for duplicate detection on the synthetic dataset."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_duplicates.py"
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic_invoices"


def _load_module():
    spec = importlib.util.spec_from_file_location("evaluate_duplicates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not DATA_DIR.exists(), reason="synthetic dataset not generated")
def test_evaluation_reports_high_precision_and_recall():
    module = _load_module()
    report = module.evaluate(DATA_DIR, seed=7)
    assert report["records"] > 0
    assert report["precision"] >= 0.9
    assert report["recall"] >= 0.9


@pytest.mark.skipif(not DATA_DIR.exists(), reason="synthetic dataset not generated")
def test_evaluation_counts_are_consistent():
    module = _load_module()
    report = module.evaluate(DATA_DIR, seed=1)
    assert report["true_positives"] == 2 * report["records"]
    assert report["precision"] == 1.0
