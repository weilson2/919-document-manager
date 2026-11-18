"""Add company settings and company-scoped business records."""

import sqlalchemy as sa
from alembic import op

revision = "0002_business_data"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def company_record_columns():
    return (
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )


def archive_columns():
    return (
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("archived_at", sa.DateTime),
    )


def identity_columns():
    return (
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("identification_type", sa.String(30), nullable=False),
        sa.Column("identification_number", sa.String(80, collation="NOCASE"), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("address", sa.Text),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )


def nonnegative_money(column, name):
    return sa.CheckConstraint(f"typeof({column}) = 'integer' AND {column} >= 0", name=name)


def upgrade() -> None:
    op.add_column("companies", sa.Column("contact_name", sa.String(200)))
    op.add_column("companies", sa.Column("phone", sa.String(40)))
    op.add_column("companies", sa.Column("email", sa.String(254)))
    op.add_column("companies", sa.Column("logo", sa.LargeBinary))
    op.add_column("companies", sa.Column("document_settings", sa.JSON, server_default=sa.text("'{}'"), nullable=False))

    op.create_table(
        "tenants",
        *company_record_columns(),
        *archive_columns(),
        *identity_columns(),
        sa.Column("stall_number", sa.String(80), nullable=False),
        sa.Column("rental_type", sa.String(20), nullable=False),
        sa.Column("rental_sen", sa.Integer, nullable=False),
        sa.Column("deposit_sen", sa.Integer, nullable=False),
        sa.Column("end_date", sa.Date),
        sa.UniqueConstraint("company_id", "identification_type", "identification_number", name="uq_tenant_identity"),
        sa.CheckConstraint("rental_type IN ('daily', 'monthly')", name="ck_tenant_rental_type"),
        sa.CheckConstraint("status IN ('active', 'inactive', 'ended')", name="ck_tenant_status"),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_tenant_dates"),
        nonnegative_money("rental_sen", "ck_tenant_rental_sen"),
        nonnegative_money("deposit_sen", "ck_tenant_deposit_sen"),
    )
    op.create_table(
        "employees",
        *company_record_columns(),
        *archive_columns(),
        *identity_columns(),
        sa.Column("employee_number", sa.String(80, collation="NOCASE"), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("position", sa.String(150), nullable=False),
        sa.Column("salary_type", sa.String(20), nullable=False),
        sa.Column("salary_sen", sa.Integer, nullable=False),
        sa.Column("birth_date", sa.Date),
        sa.Column("citizenship", sa.String(30)),
        sa.Column("tax_residency", sa.String(30)),
        sa.Column("employment_type", sa.String(30)),
        sa.UniqueConstraint("company_id", "employee_number", name="uq_employee_number"),
        sa.UniqueConstraint("company_id", "identification_type", "identification_number", name="uq_employee_identity"),
        sa.CheckConstraint("salary_type IN ('monthly', 'daily', 'hourly')", name="ck_employee_salary_type"),
        sa.CheckConstraint("status IN ('active', 'inactive', 'ended')", name="ck_employee_status"),
        nonnegative_money("salary_sen", "ck_employee_salary_sen"),
    )
    op.create_table(
        "template_categories",
        *company_record_columns(),
        sa.Column("name", sa.String(120, collation="NOCASE"), nullable=False),
        sa.UniqueConstraint("company_id", "id", name="uq_category_company_id"),
        sa.UniqueConstraint("company_id", "name", name="uq_category_name"),
    )
    op.create_table(
        "templates",
        *company_record_columns(),
        *archive_columns(),
        sa.Column("name", sa.String(160, collation="NOCASE"), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("category_id", sa.Integer),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.UniqueConstraint("company_id", "id", name="uq_template_company_id"),
        sa.UniqueConstraint("company_id", "name", name="uq_template_name"),
        sa.ForeignKeyConstraint(
            ["company_id", "category_id"], ["template_categories.company_id", "template_categories.id"],
            name="fk_template_company_category", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_template_status"),
    )
    op.create_table(
        "template_versions",
        *company_record_columns(),
        sa.Column("template_id", sa.Integer, nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("metadata_snapshot", sa.JSON, nullable=False),
        sa.Column("document_json", sa.JSON),
        sa.UniqueConstraint("company_id", "template_id", "version_number", name="uq_template_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "template_id"], ["templates.company_id", "templates.id"],
            name="fk_version_company_template", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version_number > 0", name="ck_template_version_number"),
    )
    op.create_table(
        "business_activity",
        *company_record_columns(),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("subject_type", sa.String(30), nullable=False),
        sa.Column("subject_id", sa.Integer, nullable=False),
        sa.Column("subject_label", sa.String(200), nullable=False),
    )
    for table in ("tenants", "employees", "templates"):
        op.create_index(f"ix_{table}_company_archive", table, ["company_id", "archived_at"])
    op.create_index("ix_activity_company_id", "business_activity", ["company_id", "id"])
    for action in ("update", "delete"):
        op.execute(
            f"CREATE TRIGGER template_versions_no_{action} BEFORE {action} ON template_versions "
            "BEGIN SELECT RAISE(ABORT, 'Published template versions are immutable'); END"
        )
    op.execute(
        "CREATE TRIGGER template_versions_no_replace BEFORE INSERT ON template_versions "
        "WHEN EXISTS (SELECT 1 FROM template_versions WHERE id = NEW.id OR "
        "(company_id = NEW.company_id AND template_id = NEW.template_id AND version_number = NEW.version_number)) "
        "BEGIN SELECT RAISE(ABORT, 'Published template versions are immutable'); END"
    )


def downgrade() -> None:
    for table in ("business_activity", "template_versions", "templates", "template_categories", "employees", "tenants"):
        op.drop_table(table)
    for column in ("document_settings", "logo", "email", "phone", "contact_name"):
        op.drop_column("companies", column)
