"""Add local user credentials and auditable payroll snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0005_payroll_and_access"
down_revision = "0004_document_history"


def upgrade() -> None:
    op.create_table(
        "local_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(60), nullable=False, unique=True),
        sa.Column("password_hash", sa.LargeBinary, nullable=False),
        sa.Column("password_salt", sa.LargeBinary, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'payroll', 'clerk')", name="ck_local_user_role"),
    )
    op.create_table(
        "payroll_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("local_users.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("period", sa.Date, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("inputs", sa.JSON, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("employee_snapshot", sa.JSON, nullable=False),
        sa.UniqueConstraint("company_id", "employee_id", "period", "revision", name="uq_payroll_run_revision"),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_company_id"),
        sa.CheckConstraint("revision > 0", name="ck_payroll_run_revision"),
        sa.CheckConstraint("status IN ('draft', 'approved')", name="ck_payroll_status"),
    )
    op.create_table(
        "payroll_documents",
        sa.Column("company_id", sa.Integer, primary_key=True),
        sa.Column("document_id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "document_id"], ["generated_documents.company_id", "generated_documents.id"],
            name="fk_payroll_document_history", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "run_id"], ["payroll_runs.company_id", "payroll_runs.id"],
            name="fk_payroll_document_run", ondelete="RESTRICT",
        ),
    )
    for table in ("payroll_runs", "payroll_documents"):
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                       "BEGIN SELECT RAISE(ABORT, 'Payroll snapshots are immutable'); END")
    op.execute(
        "CREATE TRIGGER payroll_runs_no_replace BEFORE INSERT ON payroll_runs "
        "WHEN EXISTS (SELECT 1 FROM payroll_runs WHERE id=NEW.id OR "
        "(company_id=NEW.company_id AND employee_id=NEW.employee_id AND period=NEW.period AND revision=NEW.revision)) "
        "BEGIN SELECT RAISE(ABORT, 'Payroll snapshots are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER payroll_runs_employee_scope BEFORE INSERT ON payroll_runs "
        "WHEN NOT EXISTS (SELECT 1 FROM employees WHERE id=NEW.employee_id AND company_id=NEW.company_id) "
        "BEGIN SELECT RAISE(ABORT, 'Employee belongs to another company'); END"
    )
    op.execute(
        "CREATE TRIGGER payroll_documents_no_replace BEFORE INSERT ON payroll_documents "
        "WHEN EXISTS (SELECT 1 FROM payroll_documents WHERE company_id=NEW.company_id AND document_id=NEW.document_id) "
        "BEGIN SELECT RAISE(ABORT, 'Payroll snapshots are immutable'); END"
    )


def downgrade() -> None:
    for table in ("payroll_documents", "payroll_runs", "local_users"):
        op.drop_table(table)
