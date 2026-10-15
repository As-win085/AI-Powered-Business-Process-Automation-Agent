"""Unit tests for the invoice workflow state machine."""
import pytest

from app.core.exceptions import ConflictError
from app.core.workflow import (
    ALLOWED_TRANSITIONS,
    FINAL_STATES,
    InvoiceState,
    assert_transition,
    can_transition,
)


def test_happy_path_upload_to_approved():
    path = [
        (InvoiceState.UPLOADED, InvoiceState.PROCESSING),
        (InvoiceState.PROCESSING, InvoiceState.NEEDS_REVIEW),
        (InvoiceState.NEEDS_REVIEW, InvoiceState.VALIDATED),
        (InvoiceState.VALIDATED, InvoiceState.PENDING_APPROVAL),
        (InvoiceState.PENDING_APPROVAL, InvoiceState.APPROVED),
    ]
    for current, target in path:
        assert can_transition(current, target), f"{current} -> {target} should be allowed"


def test_approval_outcomes():
    assert can_transition(InvoiceState.PENDING_APPROVAL, InvoiceState.REJECTED)
    assert can_transition(InvoiceState.PENDING_APPROVAL, InvoiceState.CORRECTION_REQUESTED)


def test_correction_loop_reopens_review():
    assert can_transition(InvoiceState.CORRECTION_REQUESTED, InvoiceState.NEEDS_REVIEW)
    assert can_transition(InvoiceState.NEEDS_REVIEW, InvoiceState.PENDING_APPROVAL)


def test_illegal_transitions_rejected():
    for current, target in [
        (InvoiceState.UPLOADED, InvoiceState.APPROVED),
        (InvoiceState.APPROVED, InvoiceState.PENDING_APPROVAL),
        (InvoiceState.REJECTED, InvoiceState.APPROVED),
        (InvoiceState.PENDING_APPROVAL, InvoiceState.VALIDATED),
    ]:
        assert not can_transition(current, target)


def test_unknown_states_are_not_transitions():
    assert not can_transition("bogus", InvoiceState.APPROVED)
    assert not can_transition(InvoiceState.UPLOADED, "bogus")


def test_final_states_have_no_outgoing_transitions():
    assert {InvoiceState.APPROVED, InvoiceState.REJECTED} == FINAL_STATES
    for state in ALLOWED_TRANSITIONS:
        if state in FINAL_STATES:
            assert not ALLOWED_TRANSITIONS[state]


def test_assert_transition_raises_conflict():
    assert_transition("validated", "pending_approval")
    with pytest.raises(ConflictError):
        assert_transition("approved", "pending_approval")
