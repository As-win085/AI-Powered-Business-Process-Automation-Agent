"""document text extraction

Revision ID: 0003_document_text
Revises: 0002_business_documents
Create Date: 2026-10-12

Adds the per-page extracted text table (with embedded/OCR provenance) and an
error column on documents to store the reason a document failed processing.
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_document_text"
down_revision = "0002_business_documents"
branch_labels = None
depends_on = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column("documents", sa.Column("error", sa.String(length=500), nullable=True))

    op.create_table(
        "document_text",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("engine", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint("source in ('embedded', 'ocr')", name="ck_document_text_source"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_text_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "page_number", name="uq_document_text_page"
        ),
    )
    op.create_index("ix_document_text_tenant_id", "document_text", ["tenant_id"])
    op.create_index("ix_document_text_document_id", "document_text", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_text_document_id", table_name="document_text")
    op.drop_index("ix_document_text_tenant_id", table_name="document_text")
    op.drop_table("document_text")
    op.drop_column("documents", "error")