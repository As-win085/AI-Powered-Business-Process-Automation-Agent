"""anomaly detection scores

Revision ID: 0006_anomaly_detection
Revises: 0005_purchase_order_matching
Create Date: 2026-10-15

Stores the unsupervised anomaly score, the model version that produced it, the
review-recommended flag and the human-readable contributing reasons on each
invoice.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_anomaly_detection"
down_revision = "0005_purchase_order_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices", sa.Column("anomaly_score", sa.Numeric(precision=9, scale=6), nullable=True)
    )
    op.add_column(
        "invoices", sa.Column("anomaly_model_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "invoices",
        sa.Column(
            "anomaly_flagged", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "invoices",
        sa.Column("anomaly_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_invoices_tenant_anomaly", "invoices", ["tenant_id", "anomaly_flagged"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_tenant_anomaly", table_name="invoices")
    op.drop_column("invoices", "anomaly_reasons")
    op.drop_column("invoices", "anomaly_flagged")
    op.drop_column("invoices", "anomaly_model_version")
    op.drop_column("invoices", "anomaly_score")
