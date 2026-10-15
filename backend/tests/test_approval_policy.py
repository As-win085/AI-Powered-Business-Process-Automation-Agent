"""Unit tests for the configurable approval routing policy."""
from decimal import Decimal

from app.services.approval_policy import ApprovalPolicy, resolve_approver_role

POLICY = ApprovalPolicy(
    manager_threshold=Decimal("1000"),
    director_threshold=Decimal("10000"),
    manager_role="approver",
    finance_role="finance",
    director_role="admin",
)


def test_under_manager_threshold_routes_to_manager():
    assert resolve_approver_role(Decimal("0"), POLICY) == "approver"
    assert resolve_approver_role(Decimal("999.99"), POLICY) == "approver"


def test_manager_band_boundary_is_finance():
    assert resolve_approver_role(Decimal("1000"), POLICY) == "finance"
    assert resolve_approver_role(Decimal("9999.99"), POLICY) == "finance"


def test_at_or_above_director_threshold_routes_to_director():
    assert resolve_approver_role(Decimal("10000"), POLICY) == "admin"
    assert resolve_approver_role(Decimal("250000"), POLICY) == "admin"


def test_missing_amount_uses_lowest_authority():
    assert resolve_approver_role(None, POLICY) == "approver"


def test_credit_notes_route_by_magnitude():
    assert resolve_approver_role(Decimal("-50000"), POLICY) == "admin"
    assert resolve_approver_role(Decimal("-5"), POLICY) == "approver"


def test_thresholds_are_configurable():
    policy = ApprovalPolicy(
        manager_threshold=Decimal("100"),
        director_threshold=Decimal("200"),
        manager_role="finance",
        finance_role="finance",
        director_role="admin",
    )
    assert resolve_approver_role(Decimal("50"), policy) == "finance"
    assert resolve_approver_role(Decimal("150"), policy) == "finance"
    assert resolve_approver_role(Decimal("500"), policy) == "admin"
