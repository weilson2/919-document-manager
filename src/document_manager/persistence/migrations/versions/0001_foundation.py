"""Create company profiles and seed the initial company settings."""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    companies = op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("registration_number", sa.String(100), nullable=False, unique=True),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    settings = op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("active_company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["active_company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("id = 1", name="ck_settings_singleton"),
    )
    op.bulk_insert(
        companies,
        [{
            "id": 1,
            "name": "919 RESTAURANT",
            "registration_number": "202603013939 (CT0159652-K)",
            "address": "1 G2 BLK D,\nJALAN INDAH 12/2,\nTAMAN INDAH,\n84000 MUAR,\nJOHOR, MALAYSIA.",
        }],
    )
    op.bulk_insert(settings, [{"id": 1, "active_company_id": 1}])


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("companies")
