"""Configurable approval routing policy.

The policy maps an invoice amount to the role that must approve it. Thresholds
and role names are supplied by the caller (backed by application settings) so
the rule stays a pure, unit-testable function.

Default bands:
    amount <  manager_threshold                  -> manager role
    manager_threshold <= amount < director_threshold -> finance role
    amount >= director_threshold                 -> director role
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ApprovalPolicy:
    manager_threshold: Decimal = Decimal("1000")
    director_threshold: Decimal = Decimal("10000")
    manager_role: str = "approver"
    finance_role: str = "finance"
    director_role: str = "admin"

    @classmethod
    def from_settings(cls, settings: Any) -> ApprovalPolicy:
        return cls(
            manager_threshold=Decimal(str(settings.approval_manager_threshold)),
            director_threshold=Decimal(str(settings.approval_director_threshold)),
            manager_role=settings.approval_manager_role,
            finance_role=settings.approval_finance_role,
            director_role=settings.approval_director_role,
        )


def _to_decimal(amount: Any) -> Decimal | None:
    if amount is None:
        return None
    if isinstance(amount, Decimal):
        return amount
    try:
        return Decimal(str(amount))
    except Exception:
        return None


def resolve_approver_role(amount: Any, policy: ApprovalPolicy) -> str:
    """Return the role name that must approve an invoice of ``amount``.

    Amounts are compared on absolute value so credit notes route by size the
    same way positive invoices do. A missing amount uses the manager band (the
    lowest required authority) and the workflow still blocks self-approval.
    """
    value = _to_decimal(amount)
    if value is None:
        return policy.manager_role
    magnitude = abs(value)
    if magnitude < policy.manager_threshold:
        return policy.manager_role
    if magnitude < policy.director_threshold:
        return policy.finance_role
    return policy.director_role
