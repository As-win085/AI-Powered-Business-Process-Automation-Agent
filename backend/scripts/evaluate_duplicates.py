"""Evaluate duplicate detection precision/recall on the synthetic dataset.

The 40 ground-truth invoices form the existing corpus. For each record we inject
a deliberate business duplicate and a deliberate near duplicate, then measure
whether detection finds the correct matched invoice (true positives) or misses
it (false negatives). A random unrelated pairing provides the negative control
that surfaces false positives.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.duplicate_detection import (  # noqa: E402
    DuplicateCandidate,
    detect_duplicates,
)

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "synthetic_invoices"


def _load_ground_truth(data_dir: Path) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((data_dir / "ground_truth").glob("*.json"))
    ]


def _to_candidate(record: dict, cid: str) -> DuplicateCandidate:
    supplier = record.get("supplier") or {}
    total = record.get("total")
    return DuplicateCandidate(
        invoice_id=cid,
        supplier_name=supplier.get("name"),
        invoice_number=record.get("invoice_number"),
        total_amount=Decimal(str(total)) if total is not None else None,
        invoice_date=(
            date.fromisoformat(record["invoice_date"])
            if record.get("invoice_date")
            else None
        ),
        line_items=record.get("line_items") or [],
    )


def _perturb_supplier(name: str | None) -> str:
    name = name or ""
    if "GmbH" in name:
        return name.replace("GmbH", "G.m.b.H.")
    if len(name) > 4:
        return name[:-1]
    return name


def evaluate(data_dir: Path, seed: int = 7) -> dict:
    rng = random.Random(seed)
    records = _load_ground_truth(data_dir)
    if not records:
        raise SystemExit(f"No ground-truth records found under {data_dir}")

    candidates = [_to_candidate(r, f"c{idx}") for idx, r in enumerate(records)]
    by_id = {c.invoice_id: c for c in candidates}

    true_positives = false_positives = false_negatives = 0

    for idx, _record in enumerate(records):
        cid = f"c{idx}"
        original = by_id[cid]

        # Business duplicate: same supplier + number under different formatting.
        business = DuplicateCandidate(
            invoice_id="probe",
            supplier_name=(original.supplier_name or "").upper(),
            invoice_number=(
                f"{original.invoice_number}-00" if original.invoice_number else None
            ),
            total_amount=original.total_amount,
            invoice_date=original.invoice_date,
            line_items=original.line_items,
        )
        results = detect_duplicates(business, candidates)
        if results and results[0]["matched_invoice_id"] == cid:
            true_positives += 1
        else:
            false_negatives += 1

        # Near duplicate: perturbed supplier name, identical amounts and lines.
        near = DuplicateCandidate(
            invoice_id="probe",
            supplier_name=_perturb_supplier(original.supplier_name),
            invoice_number=None,
            total_amount=original.total_amount,
            invoice_date=original.invoice_date,
            line_items=original.line_items,
        )
        results = detect_duplicates(near, candidates)
        if results and results[0]["matched_invoice_id"] == cid:
            true_positives += 1
        else:
            false_negatives += 1

        # Negative control: a random unrelated invoice must not match this one.
        others = [c for c in candidates if c.invoice_id != cid]
        if others:
            other = rng.choice(others)
            neg = DuplicateCandidate(
                invoice_id="probe",
                supplier_name=other.supplier_name,
                invoice_number=other.invoice_number,
                total_amount=other.total_amount,
                invoice_date=other.invoice_date,
                line_items=other.line_items,
            )
            if detect_duplicates(neg, [original]):
                false_positives += 1

    denominator_p = true_positives + false_positives
    denominator_r = true_positives + false_negatives
    return {
        "records": len(records),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(true_positives / denominator_p, 4) if denominator_p else 0.0,
        "recall": round(true_positives / denominator_r, 4) if denominator_r else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.data_dir, seed=args.seed), indent=2))


if __name__ == "__main__":
    main()
