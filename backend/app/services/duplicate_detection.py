"""Duplicate detection service.

Three layers:
- exact: identical file hash (already computed at upload time)
- business: normalized supplier + normalized invoice number match
- near: RapidFuzz on supplier name plus amount/date proximity and line-item similarity

All detections are warnings for human review. Nothing is ever auto-rejected.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz

BUSINESS_SCORE = 100.0
NEAR_DUPLICATE_THRESHOLD = 80.0


def normalize_invoice_number(num: str | None) -> str | None:
    """Strip punctuation, spaces, case and leading zeros from an invoice number.

    Leading zeros are removed inside each numeric run so that ``INV-00123`` and
    ``INV-123`` normalize identically, while letter prefixes are preserved.
    """
    if num is None:
        return None
    text = unicodedata.normalize("NFKD", str(num)).casefold()
    text = re.sub(r"[^a-z0-9]", "", text)
    parts = re.findall(r"[a-z]+|\d+", text)
    if not parts:
        return None
    normalized = "".join(part.lstrip("0") or "0" if part.isdigit() else part for part in parts)
    return normalized or None


def normalize_supplier_name(name: str | None) -> str | None:
    """Casefold and collapse whitespace/punctuation in a supplier name."""
    if name is None:
        return None
    text = unicodedata.normalize("NFKD", str(name)).casefold()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _decimal(val: Any) -> Decimal | None:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return None


def _as_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val).split("T")[0])
    except Exception:
        return None


@dataclass
class DuplicateCandidate:
    """A previously stored invoice compared against the incoming invoice."""

    invoice_id: str
    supplier_name: str | None = None
    invoice_number: str | None = None
    total_amount: Decimal | None = None
    invoice_date: date | None = None
    line_items: list[Any] = field(default_factory=list)


def _amount_proximity(a: Decimal | None, b: Decimal | None) -> float:
    if a is None or b is None:
        return 0.0
    if a == b:
        return 100.0
    largest = max(abs(a), abs(b))
    if largest == 0:
        return 100.0
    diff = abs(a - b)
    ratio = 1.0 - float(diff / largest)
    return max(0.0, ratio * 100.0)


def _date_proximity(a: date | None, b: date | None, window_days: int = 30) -> float:
    if a is None or b is None:
        return 0.0
    delta = abs((a - b).days)
    if delta >= window_days:
        return 0.0
    return (1.0 - delta / window_days) * 100.0


def _line_item_similarity(
    a: list[Any], b: list[Any], threshold: float = 90.0
) -> float:
    def descriptions(items: list[Any]) -> list[str]:
        out = []
        for item in items:
            desc = (
                item.get("description")
                if isinstance(item, dict)
                else getattr(item, "description", None)
            )
            if desc:
                out.append(str(desc).strip().casefold())
        return out

    left = descriptions(a)
    right = descriptions(b)
    if not left or not right:
        return 0.0
    matched = 0
    used: set[int] = set()
    for ldesc in left:
        for idx, rdesc in enumerate(right):
            if idx in used:
                continue
            if fuzz.token_set_ratio(ldesc, rdesc) >= threshold:
                matched += 1
                used.add(idx)
                break
    return (matched / max(len(left), len(right))) * 100.0


def near_duplicate_score(
    incoming: DuplicateCandidate,
    candidate: DuplicateCandidate,
    *,
    weights: dict[str, float] | None = None,
) -> float:
    """Weighted near-duplicate score in the range 0-100."""
    weights = dict(
        weights
        or {
            "supplier": 0.40,
            "amount": 0.30,
            "date": 0.15,
            "lines": 0.15,
        }
    )
    a_sup = normalize_supplier_name(incoming.supplier_name)
    b_sup = normalize_supplier_name(candidate.supplier_name)
    supplier_score = fuzz.token_set_ratio(a_sup, b_sup) if a_sup and b_sup else 0.0
    amount_score = _amount_proximity(incoming.total_amount, candidate.total_amount)
    date_score = _date_proximity(incoming.invoice_date, candidate.invoice_date)

    # Only weigh line items when at least one side actually has them; otherwise
    # redistribute the weight so identical invoices still score 100.
    if incoming.line_items or candidate.line_items:
        lines_score = _line_item_similarity(incoming.line_items, candidate.line_items)
    else:
        lines_score = 0.0
        weights.pop("lines", None)

    total_weight = sum(weights.values()) or 1.0
    return (
        supplier_score * weights["supplier"]
        + amount_score * weights["amount"]
        + date_score * weights["date"]
        + lines_score * weights.get("lines", 0.0)
    ) / total_weight


def _result(kind: str, score: float, matched_id: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": kind,
        "score": round(float(score), 2),
        "matched_invoice_id": matched_id,
        "warning": True,
        "details": details,
    }


def detect_duplicates(
    incoming: DuplicateCandidate,
    candidates: list[DuplicateCandidate],
    *,
    file_hash: str | None = None,
    candidate_hashes: dict[str, str] | None = None,
    near_threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Return every duplicate warning for ``incoming`` against ``candidates``.

    Results are warnings only; callers must never auto-reject on them.
    """
    results: list[dict[str, Any]] = []

    # 1. Exact file duplicate via SHA-256.
    if file_hash and candidate_hashes:
        for cid, chash in candidate_hashes.items():
            if chash == file_hash:
                results.append(_result("exact", 100.0, cid, {"file_hash": file_hash}))
                return results  # exact match supersedes softer signals

    norm_num = normalize_invoice_number(incoming.invoice_number)
    norm_sup = normalize_supplier_name(incoming.supplier_name)

    # 2. Business duplicate: normalized supplier + invoice number.
    if norm_num and norm_sup:
        for c in candidates:
            if (
                normalize_invoice_number(c.invoice_number) == norm_num
                and normalize_supplier_name(c.supplier_name) == norm_sup
            ):
                return [
                    _result(
                        "business",
                        BUSINESS_SCORE,
                        c.invoice_id,
                        {"invoice_number": norm_num, "supplier": norm_sup},
                    )
                ]

    # 3. Near duplicate: fuzzy signals, flagged for review only.
    for c in candidates:
        score = near_duplicate_score(incoming, c)
        if score >= near_threshold:
            results.append(
                _result(
                    "near",
                    score,
                    c.invoice_id,
                    {
                        "supplier_similarity": round(
                            fuzz.token_set_ratio(
                                normalize_supplier_name(incoming.supplier_name) or "",
                                normalize_supplier_name(c.supplier_name) or "",
                            ),
                            2,
                        ),
                        "amount_proximity": round(
                            _amount_proximity(incoming.total_amount, c.total_amount), 2
                        ),
                        "date_proximity": round(
                            _date_proximity(incoming.invoice_date, c.invoice_date), 2
                        ),
                        "line_item_similarity": round(
                            _line_item_similarity(incoming.line_items, c.line_items), 2
                        ),
                    },
                )
            )
    return sorted(results, key=lambda r: r["score"], reverse=True)

