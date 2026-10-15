"""approval workflow state machine

Revision ID: 0004_approval_workflow
Revises: 0003_document_text
Create Date: 2026-10-15

Extends the invoice state check constraint with the explicit ``validated`` and
``pending_approval`` states used by the approval workflow, and adds a partial
unique index so an invoice can have at most one open approval at a time.
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_approval_workflow"
down_revision = "0003_document_text"
branch_labels = None
depends_on = None

_NEW_STATES = (
    "'uploaded', 'queued', 'processing', 'needs_review', 'validated', "
    "'pending_approval', 'ready_for_approval', 'approved', 'rejected', "
    "'correction_requested', 'failed'"
)
_OLD_STATES = (
    "'uploaded', 'queued', 'processing', 'needs_review', 'ready_for_approval', "
    "'approved', 'rejected', 'correction_requested', 'failed'"
)


def upgrade() -> None:
    op.drop_constraint("ck_invoices_state", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_state", "invoices", f"state in ({_NEW_STATES})"
    )

    op.create_index(
        "uq_approvals_pending_invoice",
        "approvals",
        ["tenant_id", "invoice_id"],
        unique=True,
        postgresql_where=sa.text("decision = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_approvals_pending_invoice", table_name="approvals")

    op.drop_constraint("ck_invoices_state", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_state", "invoices", f"state in ({_OLD_STATES})"
    )
