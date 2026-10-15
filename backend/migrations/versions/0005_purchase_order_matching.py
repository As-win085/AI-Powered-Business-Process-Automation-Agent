"""purchase order matching

Revision ID: 0005_purchase_order_matching
Revises: 0004_approval_workflow
Create Date: 2026-10-15

Adds the invoice-level PO number captured during extraction/review so an
invoice can be matched against a stored purchase order, plus an index to make
the normalized lookup efficient.
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_purchase_order_matching"
down_revision = "0004_approval_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices", sa.Column("po_number", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "invoices", sa.Column("normalized_po_number", sa.String(length=128), nullable=True)
    )
    op.create_index(
        "ix_invoices_normalized_po_number", "invoices", ["normalized_po_number"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_normalized_po_number", table_name="invoices")
    op.drop_column("invoices", "normalized_po_number")
    op.drop_column("invoices", "po_number")
