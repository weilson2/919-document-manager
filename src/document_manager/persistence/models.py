from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from document_manager.persistence.money import Money


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    registration_number: Mapped[str] = mapped_column(String(100), unique=True)
    address: Mapped[str] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    logo: Mapped[bytes | None] = mapped_column(LargeBinary)
    document_settings: Mapped[dict] = mapped_column(JSON, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class AppSetting(Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    active_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))


class CompanyRecord:
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ArchivableRecord(CompanyRecord):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)


class Tenant(ArchivableRecord, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("company_id", "identification_type", "identification_number", name="uq_tenant_identity"),
        Index("ix_tenants_company_archive", "company_id", "archived_at"),
        CheckConstraint("rental_type IN ('daily', 'monthly')", name="ck_tenant_rental_type"),
        CheckConstraint("status IN ('active', 'inactive', 'ended')", name="ck_tenant_status"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_tenant_dates"),
        CheckConstraint("typeof(rental_sen) = 'integer' AND rental_sen >= 0", name="ck_tenant_rental_sen"),
        CheckConstraint("typeof(deposit_sen) = 'integer' AND deposit_sen >= 0", name="ck_tenant_deposit_sen"),
    )

    name: Mapped[str] = mapped_column(String(200))
    identification_type: Mapped[str] = mapped_column(String(30))
    identification_number: Mapped[str] = mapped_column(String(80, collation="NOCASE"))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)
    stall_number: Mapped[str] = mapped_column(String(80))
    rental_type: Mapped[str] = mapped_column(String(20))
    rental_amount: Mapped[Decimal] = mapped_column("rental_sen", Money)
    deposit: Mapped[Decimal] = mapped_column("deposit_sen", Money)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))


class Employee(ArchivableRecord, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("company_id", "employee_number", name="uq_employee_number"),
        UniqueConstraint("company_id", "identification_type", "identification_number", name="uq_employee_identity"),
        Index("ix_employees_company_archive", "company_id", "archived_at"),
        CheckConstraint("salary_type IN ('monthly', 'daily', 'hourly')", name="ck_employee_salary_type"),
        CheckConstraint("status IN ('active', 'inactive', 'ended')", name="ck_employee_status"),
        CheckConstraint("typeof(salary_sen) = 'integer' AND salary_sen >= 0", name="ck_employee_salary_sen"),
    )

    employee_number: Mapped[str] = mapped_column(String(80, collation="NOCASE"))
    name: Mapped[str] = mapped_column(String(200))
    identification_type: Mapped[str] = mapped_column(String(30))
    identification_number: Mapped[str] = mapped_column(String(80, collation="NOCASE"))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    address: Mapped[str | None] = mapped_column(Text)
    position: Mapped[str] = mapped_column(String(150))
    salary_type: Mapped[str] = mapped_column(String(20))
    basic_salary: Mapped[Decimal] = mapped_column("salary_sen", Money)
    start_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)
    citizenship: Mapped[str | None] = mapped_column(String(30))
    tax_residency: Mapped[str | None] = mapped_column(String(30))
    employment_type: Mapped[str | None] = mapped_column(String(30))


class TemplateCategory(CompanyRecord, Base):
    __tablename__ = "template_categories"
    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_category_company_id"),
        UniqueConstraint("company_id", "name", name="uq_category_name"),
    )

    name: Mapped[str] = mapped_column(String(120, collation="NOCASE"))


class Template(ArchivableRecord, Base):
    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_template_company_id"),
        UniqueConstraint("company_id", "name", name="uq_template_name"),
        ForeignKeyConstraint(
            ["company_id", "category_id"], ["template_categories.company_id", "template_categories.id"],
            name="fk_template_company_category", ondelete="RESTRICT",
        ),
        Index("ix_templates_company_archive", "company_id", "archived_at"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_template_status"),
    )

    name: Mapped[str] = mapped_column(String(160, collation="NOCASE"))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(20), server_default="draft")


class TemplateVersion(CompanyRecord, Base):
    __tablename__ = "template_versions"
    __table_args__ = (
        UniqueConstraint("company_id", "template_id", "version_number", name="uq_template_version"),
        ForeignKeyConstraint(
            ["company_id", "template_id"], ["templates.company_id", "templates.id"],
            name="fk_version_company_template", ondelete="RESTRICT",
        ),
        CheckConstraint("version_number > 0", name="ck_template_version_number"),
    )

    template_id: Mapped[int]
    version_number: Mapped[int]
    metadata_snapshot: Mapped[dict] = mapped_column(JSON)
    document_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))


class BusinessActivity(CompanyRecord, Base):
    __tablename__ = "business_activity"
    __table_args__ = (Index("ix_activity_company_id", "company_id", "id"),)

    action: Mapped[str] = mapped_column(String(40))
    subject_type: Mapped[str] = mapped_column(String(30))
    subject_id: Mapped[int]
    subject_label: Mapped[str] = mapped_column(String(200))
