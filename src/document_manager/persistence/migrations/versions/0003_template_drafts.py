"""Add company-scoped, independently editable template drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_template_drafts"
down_revision = "0002_business_data"


def upgrade() -> None:
    op.create_table(
        "template_drafts",
        sa.Column("company_id", sa.Integer, primary_key=True),
        sa.Column("template_id", sa.Integer, primary_key=True),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("document_json", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "template_id"], ["templates.company_id", "templates.id"],
            name="fk_draft_company_template", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("revision > 0", name="ck_draft_revision"),
    )


def downgrade() -> None:
    op.drop_table("template_drafts")
