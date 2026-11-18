"""Create immutable generated documents and an export ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0004_document_history"
down_revision = "0003_template_drafts"


def upgrade() -> None:
    op.create_table(
        "generated_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("archived_at", sa.DateTime),
        sa.Column("template_id", sa.Integer, nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("number", sa.String(45), nullable=False),
        sa.Column("category_key", sa.String(32), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("subject_kind", sa.String(20)),
        sa.Column("subject_id", sa.Integer),
        sa.Column("subject_name", sa.String(200), nullable=False),
        sa.Column("input_values", sa.JSON, nullable=False),
        sa.Column("resolved_values", sa.JSON, nullable=False),
        sa.Column("pdf", sa.LargeBinary, nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.UniqueConstraint("company_id", "id", name="uq_generated_company_id"),
        sa.UniqueConstraint("company_id", "number", name="uq_generated_number"),
        sa.ForeignKeyConstraint(
            ["company_id", "template_id", "version_number"],
            ["template_versions.company_id", "template_versions.template_id", "template_versions.version_number"],
            name="fk_document_company_version", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_generated_company_archive", "generated_documents", ["company_id", "archived_at"])
    op.create_table(
        "document_exports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("document_id", sa.Integer, nullable=False),
        sa.Column("filename", sa.String(260), nullable=False),
        sa.Column("byte_count", sa.Integer, nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "document_id"], ["generated_documents.company_id", "generated_documents.id"],
            name="fk_export_company_document", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_exports_company_document", "document_exports", ["company_id", "document_id"])
    op.execute(
        "CREATE TRIGGER generated_documents_protected BEFORE UPDATE OF id, company_id, created_at, template_id, "
        "version_number, number, category_key, title, subject_kind, subject_id, subject_name, input_values, "
        "resolved_values, pdf, checksum ON generated_documents "
        "BEGIN SELECT RAISE(ABORT, 'Generated document snapshots are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER generated_documents_no_delete BEFORE DELETE ON generated_documents "
        "BEGIN SELECT RAISE(ABORT, 'Generated document snapshots are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER generated_documents_no_replace BEFORE INSERT ON generated_documents "
        "WHEN EXISTS (SELECT 1 FROM generated_documents WHERE id = NEW.id OR "
        "(company_id = NEW.company_id AND number = NEW.number)) "
        "BEGIN SELECT RAISE(ABORT, 'Generated document snapshots are immutable'); END"
    )


def downgrade() -> None:
    op.drop_table("document_exports")
    op.drop_table("generated_documents")
