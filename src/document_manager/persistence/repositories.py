from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from document_manager.persistence.models import (
    AppSetting,
    ArchivableRecord,
    BusinessActivity,
    Company,
    Template,
    TemplateCategory,
    TemplateVersion,
)

Record = TypeVar("Record", bound=ArchivableRecord)


class CompanyRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self):
        query = select(Company.id, Company.name, Company.registration_number).order_by(Company.name, Company.id)
        return self.session.execute(query).all()

    def default(self) -> AppSetting:
        return self.session.get_one(AppSetting, 1)

    def get(self, company_id: int) -> Company | None:
        return self.session.get(Company, company_id)

    def registration_used(self, registration_number: str, target_id: int | None) -> bool:
        query = select(Company.id).where(Company.registration_number.collate("NOCASE") == registration_number)
        if target_id is not None:
            query = query.where(Company.id != target_id)
        return self.session.scalar(query.limit(1)) is not None


class RecordRepository:
    def __init__(self, session: Session, company_id: int, model: type[Record]):
        self.session = session
        self.company_id = company_id
        self.model = model

    def query(self):
        return select(self.model).where(self.model.company_id == self.company_id)

    def get(self, record_id: int) -> Record | None:
        return self.session.scalar(self.query().where(self.model.id == record_id))

    def list(self, search: str, search_columns: tuple, archived: bool, filters: dict):
        query = self.query().where(self.model.archived_at.is_not(None) if archived else self.model.archived_at.is_(None))
        if search:
            query = query.where(or_(*(column.icontains(search, autoescape=True) for column in search_columns)))
        for key, value in filters.items():
            query = query.where(getattr(self.model, key) == value)
        return list(self.session.scalars(query.order_by(func.lower(self.model.name), self.model.id)))

    def add(self, values: dict) -> Record:
        record = self.model(company_id=self.company_id, **values)
        self.session.add(record)
        self.session.flush()
        return record

    def set_archived(self, record: Record, archived: bool) -> None:
        record.archived_at = datetime.now(UTC).replace(tzinfo=None) if archived else None

    def count(self, status: str | None = None) -> int:
        query = select(func.count()).select_from(self.model).where(
            self.model.company_id == self.company_id, self.model.archived_at.is_(None)
        )
        if status is not None:
            query = query.where(self.model.status == status)
        return self.session.scalar(query)


class TemplateRepository:
    def __init__(self, session: Session, company_id: int):
        self.session = session
        self.company_id = company_id

    def categories(self):
        return list(self.session.scalars(
            select(TemplateCategory)
            .where(TemplateCategory.company_id == self.company_id)
            .order_by(func.lower(TemplateCategory.name), TemplateCategory.id)
        ))

    def category(self, category_id: int) -> TemplateCategory | None:
        return self.session.scalar(select(TemplateCategory).where(
            TemplateCategory.company_id == self.company_id, TemplateCategory.id == category_id
        ))

    def name_used(self, name: str) -> bool:
        return self.session.scalar(select(Template.id).where(
            Template.company_id == self.company_id, Template.name == name
        )) is not None

    def versions(self, template_id: int):
        return select(TemplateVersion).where(
            TemplateVersion.company_id == self.company_id, TemplateVersion.template_id == template_id
        ).order_by(TemplateVersion.version_number.desc())


class ActivityRepository:
    def __init__(self, session: Session, company_id: int):
        self.session = session
        self.company_id = company_id

    def record(self, action: str, subject_type: str, subject_id: int, label: str) -> None:
        self.session.add(BusinessActivity(
            company_id=self.company_id, action=action, subject_type=subject_type,
            subject_id=subject_id, subject_label=label,
        ))

    def recent(self, limit: int = 8, *, omit_sensitive=False):
        query = select(BusinessActivity).where(BusinessActivity.company_id == self.company_id)
        if omit_sensitive:
            query = query.where(BusinessActivity.subject_type.not_in(("employee", "payroll")))
        return list(self.session.scalars(query.order_by(BusinessActivity.id.desc()).limit(limit)))
