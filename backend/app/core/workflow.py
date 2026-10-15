"""Canonical invoice workflow state machine.

Every state change in the invoice lifecycle must go through
:func:`assert_transition`. Transitions that are not explicitly listed here are
rejected, so the set below is the single source of truth for the workflow.

    uploaded -> processing -> needs_review -> validated -> pending_approval
              -> approved / rejected / correction_requested
"""

from __future__ import annotations

from enum import StrEnum

from app.core.exceptions import ConflictError


class InvoiceState(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    VALIDATED = "validated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTION_REQUESTED = "correction_requested"
    FAILED = "failed"

    # Retained for backward compatibility with earlier milestones.
    READY_FOR_APPROVAL = "ready_for_approval"


#: The one place that defines which invoice state changes are legal.
ALLOWED_TRANSITIONS: dict[InvoiceState, frozenset[InvoiceState]] = {
    InvoiceState.UPLOADED: frozenset(
        {InvoiceState.QUEUED, InvoiceState.PROCESSING, InvoiceState.FAILED}
    ),
    InvoiceState.QUEUED: frozenset({InvoiceState.PROCESSING, InvoiceState.FAILED}),
    InvoiceState.PROCESSING: frozenset(
        {InvoiceState.NEEDS_REVIEW, InvoiceState.FAILED}
    ),
    InvoiceState.NEEDS_REVIEW: frozenset(
        {
            InvoiceState.VALIDATED,
            InvoiceState.PENDING_APPROVAL,
            InvoiceState.CORRECTION_REQUESTED,
            InvoiceState.PROCESSING,
            InvoiceState.FAILED,
        }
    ),
    InvoiceState.VALIDATED: frozenset({InvoiceState.PENDING_APPROVAL}),
    InvoiceState.READY_FOR_APPROVAL: frozenset({InvoiceState.PENDING_APPROVAL}),
    InvoiceState.PENDING_APPROVAL: frozenset(
        {
            InvoiceState.APPROVED,
            InvoiceState.REJECTED,
            InvoiceState.CORRECTION_REQUESTED,
        }
    ),
    InvoiceState.CORRECTION_REQUESTED: frozenset({InvoiceState.NEEDS_REVIEW}),
    InvoiceState.FAILED: frozenset({InvoiceState.QUEUED, InvoiceState.PROCESSING}),
    InvoiceState.APPROVED: frozenset(),
    InvoiceState.REJECTED: frozenset(),
}

FINAL_STATES: frozenset[InvoiceState] = frozenset(
    {InvoiceState.APPROVED, InvoiceState.REJECTED}
)


def can_transition(current: str | InvoiceState, target: str | InvoiceState) -> bool:
    """Return True only when ``current -> target`` is an allowed transition."""
    try:
        current_state = InvoiceState(current)
        target_state = InvoiceState(target)
    except ValueError:
        return False
    return target_state in ALLOWED_TRANSITIONS.get(current_state, frozenset())


def assert_transition(current: str | InvoiceState, target: str | InvoiceState) -> None:
    """Raise :class:`ConflictError` when a transition is not permitted."""
    if not can_transition(current, target):
        raise ConflictError(f"Illegal invoice transition: {current} -> {target}")
