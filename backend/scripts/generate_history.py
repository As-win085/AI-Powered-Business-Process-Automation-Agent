"""Generate a synthetic multi-month invoice history with injected anomalies.

This produces the data used to train and evaluate the unsupervised anomaly
detector. It is deliberately *not* real data: the anomaly labels exist only so the
evaluation script can report precision/recall. The generator models:

- ~20 suppliers with their own base spend, cadence and volatility
- 12+ months of invoices, so supplier-relative features have real history
- two injected anomaly types on top of the normal stream:
    * ``amount_spike``      - a single invoice 4-9x the supplier's base amount
    * ``frequency_spike``   - a burst of otherwise-normal invoices in one week

Usage:
    python scripts/generate_history.py [--suppliers 20] [--months 14] [--seed 7]
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

SUPPLIER_NAMES = [
    "Acme Industrial Supply",
    "Borealis Components GmbH",
    "Nimbus Trading Co.",
    "Vertex Manufacturing Inc",
    "Quanta Office Solutions",
    "Helios Food Distributors",
    "Zeppelin Electronics",
    "Onyx Construction Materials",
    "Silverline Logistics",
    "Atlas Power Systems",
    "Meridian Facilities Ltd",
    "Crestline Packaging",
    "Ironwood Tooling",
    "Aurora Medical Supplies",
    "Pinnacle Catering Group",
    "Sable Textiles",
    "Northwind Chemicals",
    "Lumen Lighting Co.",
    "Cobalt Software Services",
    "Harborview Freight",
]

CURRENCIES = ["USD", "EUR", "GBP"]


def _supplier_profiles(rng: random.Random, count: int) -> list[dict]:
    profiles = []
    for name in SUPPLIER_NAMES[:count]:
        base = rng.uniform(800.0, 9000.0)
        profiles.append(
            {
                "name": name,
                "base_amount": base,
                "monthly_frequency": rng.uniform(0.7, 3.0),
                "amount_cv": rng.uniform(0.10, 0.35),
                "unit_price": base / rng.uniform(10.0, 40.0),
                "currency": rng.choice(CURRENCIES),
            }
        )
    return profiles


def _month_start(start: date, offset: int) -> date:
    month_index = (start.month - 1) + offset
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _build_line_items(rng: random.Random, base: float, unit_price: float) -> list[dict]:
    line_count = rng.randint(1, 5)
    weights = [rng.uniform(0.5, 1.5) for _ in range(line_count)]
    total_weight = sum(weights)
    items = []
    for index, weight in enumerate(weights, start=1):
        line_total = base * weight / total_weight
        quantity = rng.randint(1, 10)
        items.append(
            {
                "line_number": index,
                "description": f"Item {index}",
                "quantity": quantity,
                "unit_price": round(line_total / quantity, 2),
                "line_total": round(line_total, 2),
            }
        )
    return items


def _make_record(
    rng: random.Random,
    profile: dict,
    invoice_date: date,
    sequence: int,
) -> dict:
    base = profile["base_amount"] * rng.lognormvariate(0.0, profile["amount_cv"])
    line_items = _build_line_items(rng, base, profile["unit_price"])
    subtotal = round(sum(item["line_total"] for item in line_items), 2)
    tax_rate = rng.uniform(0.05, 0.20)
    tax_amount = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax_amount, 2)
    po_total = (
        round(total * rng.uniform(0.98, 1.02), 2) if rng.random() < 0.6 else None
    )
    return {
        "invoice_id": f"HIST-{sequence:06d}",
        "invoice_number": f"INV-{invoice_date.year}{invoice_date.month:02d}-{sequence:04d}",
        "supplier": profile["name"],
        "invoice_date": invoice_date.isoformat(),
        "currency": profile["currency"],
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "total_amount": total,
        "po_total": po_total,
        "line_items": line_items,
        "is_anomaly": False,
        "anomaly_type": None,
    }


def _scale_amount(record: dict, factor: float) -> None:
    """Scale the monetary totals (but not unit prices) to create an amount spike."""
    record["subtotal"] = round(record["subtotal"] * factor, 2)
    record["tax_amount"] = round(record["tax_amount"] * factor, 2)
    record["total_amount"] = round(record["total_amount"] * factor, 2)
    for item in record["line_items"]:
        item["line_total"] = round(item["line_total"] * factor, 2)


def generate_records(
    *,
    seed: int = 7,
    suppliers: int = 20,
    months: int = 14,
    anomaly_spike_suppliers: float = 0.35,
    anomaly_burst_suppliers: float = 0.20,
) -> dict:
    """Return ``{"records": [...], "summary": {...}}`` (deterministic for a seed)."""
    rng = random.Random(seed)
    start = date(2024, 1, 1)
    profiles = _supplier_profiles(rng, suppliers)

    records: list[dict] = []
    sequence = 0
    for profile in profiles:
        for month in range(months):
            month_start = _month_start(start, month)
            count = max(0, round(rng.gauss(profile["monthly_frequency"], 0.6)))
            for _ in range(count):
                sequence += 1
                invoice_date = month_start + timedelta(days=rng.randint(0, 26))
                records.append(_make_record(rng, profile, invoice_date, sequence))

    amount_spikes = _inject_amount_spikes(
        rng, records, profiles, anomaly_spike_suppliers
    )
    frequency_spikes = _inject_frequency_spikes(
        rng, records, profiles, anomaly_burst_suppliers, sequence
    )

    records.sort(key=lambda record: record["invoice_date"])
    anomaly_count = sum(1 for record in records if record["is_anomaly"])
    summary = {
        "seed": seed,
        "suppliers": suppliers,
        "months": months,
        "count": len(records),
        "anomaly_count": anomaly_count,
        "amount_spike_count": amount_spikes,
        "frequency_spike_count": frequency_spikes,
        "start_date": records[0]["invoice_date"],
        "end_date": records[-1]["invoice_date"],
    }
    return {"records": records, "summary": summary}


def _inject_amount_spikes(
    rng: random.Random,
    records: list[dict],
    profiles: list[dict],
    fraction: float,
) -> int:
    chosen = rng.sample(profiles, max(1, round(len(profiles) * fraction)))
    injected = 0
    for profile in chosen:
        candidates = [r for r in records if r["supplier"] == profile["name"]]
        if not candidates:
            continue
        picks = rng.sample(candidates, min(2, max(1, len(candidates) // 6)))
        for record in picks:
            _scale_amount(record, rng.uniform(4.0, 9.0))
            record["is_anomaly"] = True
            record["anomaly_type"] = "amount_spike"
            injected += 1
    return injected


def _inject_frequency_spikes(
    rng: random.Random,
    records: list[dict],
    profiles: list[dict],
    fraction: float,
    sequence: int,
) -> int:
    chosen = rng.sample(profiles, max(1, round(len(profiles) * fraction)))
    injected = 0
    for profile in chosen:
        candidates = [r for r in records if r["supplier"] == profile["name"]]
        if not candidates:
            continue
        anchor = date.fromisoformat(rng.choice(candidates)["invoice_date"])
        burst_size = rng.randint(8, 12)
        for _ in range(burst_size):
            sequence += 1
            invoice_date = anchor + timedelta(days=rng.randint(-2, 2))
            record = _make_record(rng, profile, invoice_date, sequence)
            record["is_anomaly"] = True
            record["anomaly_type"] = "frequency_spike"
            records.append(record)
            injected += 1
    return injected


def generate(
    output_dir: Path,
    *,
    seed: int = 7,
    suppliers: int = 20,
    months: int = 14,
) -> dict:
    payload = generate_records(seed=seed, suppliers=suppliers, months=months)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "history.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary = payload["summary"]
    print(
        f"Wrote {summary['count']} invoices ({summary['anomaly_count']} anomalies: "
        f"{summary['amount_spike_count']} amount, {summary['frequency_spike_count']} "
        f"frequency) to {output_path}"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suppliers", type=int, default=20)
    parser.add_argument("--months", type=int, default=14)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "synthetic_history",
        help="output directory (default: <repo>/data/synthetic_history)",
    )
    args = parser.parse_args()
    generate(
        args.output_dir,
        seed=args.seed,
        suppliers=args.suppliers,
        months=args.months,
    )


if __name__ == "__main__":
    main()
