from dataclasses import dataclass
from itertools import count
from typing import Literal

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from document_manager.persistence.database import write_session
from document_manager.persistence.models import (
    ArchivableRecord,
    BusinessActivity,
    Employee,
    Template,
    TemplateCategory,
    TemplateDraft,
    TemplateVersion,
    Tenant,
)
from document_manager.persistence.repositories import (
    ActivityRepository,
    RecordRepository,
    TemplateRepository,
)
from document_manager.services.auth import require_sensitive
from document_manager.services.designs import (
    DesignService,
    checked_document,
    latest_design_version,
    uses_employee_data,
)
from document_manager.services.documents import DocumentService
from document_manager.services.errors import (
    BusinessError,
    DuplicateRecord,
    RecordUnavailable,
)
from document_manager.services.fill import FillService
from document_manager.services.payroll import PayrollService
from document_manager.services.starters import install_starters
from document_manager.services.validation import (
    CategoryInput,
    EmployeeInput,
    TemplateInput,
    TenantInput,
)

RecordKind = Literal["tenant", "employee", "template"]


@dataclass(frozen=True)
class RecordSpec:
    model: type
    schema: type
    search_columns: tuple
    duplicate_message: str


RECORDS = {
    "tenant": RecordSpec(
        Tenant, TenantInput, (Tenant.name, Tenant.identification_number, Tenant.stall_number, Tenant.phone),
        "This identification number and type are already registered for a tenant in this company.",
    ),
    "employee": RecordSpec(
        Employee, EmployeeInput, (Employee.name, Employee.employee_number, Employee.identification_number, Employee.position),
        "This staff number or identification number is already registered in this company.",
    ),
    "template": RecordSpec(
        Template, TemplateInput, (Template.name, Template.description),
        "This company already has a template with this name.",
    ),
}


@dataclass(frozen=True)
class DashboardSummary:
    templates: int
    documents: int | None
    active_employees: int
    active_tenants: int
    activity: list[BusinessActivity]


class BusinessService:
    def __init__(self, engine: Engine, identity=None):
        self._engine = engine
        self.identity = identity
        self.designs = DesignService(engine, identity)
        self.documents = DocumentService(engine, identity)
        self.fill = FillService(engine, identity)
        self.payroll = PayrollService(engine, identity)

    def install_starters(self, company_id: int) -> None:
        install_starters(self._engine, company_id)

    def dashboard(self, company_id: int) -> DashboardSummary:
        with Session(self._engine) as session:
            session.connection().exec_driver_sql("BEGIN")
            return DashboardSummary(
                templates=RecordRepository(session, company_id, Template).count(),
                  documents=self.documents.count(session, company_id),
                active_employees=RecordRepository(session, company_id, Employee).count("active"),
                active_tenants=RecordRepository(session, company_id, Tenant).count("active"),
                  activity=ActivityRepository(session, company_id).recent(
                      omit_sensitive=self.identity is not None and not self.identity.sensitive_access,
                  ),
            )

    def list_records(
        self, kind: RecordKind, company_id: int, *, search: str = "", archived: bool = False,
        status: str | None = None, category_id: int | None = None, record_type: str | None = None,
    ) -> list[ArchivableRecord]:
        if kind == "employee":
            require_sensitive(self.identity)
        spec = RECORDS[kind]
        filters = {}
        if status is not None:
            filters["status"] = status
        if kind == "template" and category_id is not None:
            filters["category_id"] = category_id
        if record_type is not None:
            if kind == "tenant":
                filters["rental_type"] = record_type
            elif kind == "employee":
                filters["salary_type"] = record_type
        with Session(self._engine) as session:
            return RecordRepository(session, company_id, spec.model).list(
                search.strip(), spec.search_columns, archived, filters,
            )

    def save_record(self, kind: RecordKind, company_id: int, payload: dict, record_id: int | None = None) -> int:
        if kind == "employee":
            require_sensitive(self.identity)
        spec = RECORDS[kind]
        values = spec.schema.model_validate(payload).model_dump()
        try:
            with write_session(self._engine) as session:
                records = RecordRepository(session, company_id, spec.model)
                if (
                    kind == "template" and values["category_id"] is not None
                    and TemplateRepository(session, company_id).category(values["category_id"]) is None
                ):
                    raise RecordUnavailable("Choose a category belonging to this company.")

                if record_id is None:
                    record = records.add(values)
                    action = "created"
                else:
                    record = self._require_record(records, record_id, archived=False)
                    if all(getattr(record, key) == value for key, value in values.items()):
                        return record.id
                    for key, value in values.items():
                        setattr(record, key, value)
                    if kind == "template":
                        record.status = "draft"
                    action = "updated"
                ActivityRepository(session, company_id).record(action, kind, record.id, record.name)
                return record.id
        except IntegrityError as error:
            self._explain_duplicate(error, spec.duplicate_message)
            raise

    def set_archived(self, kind: RecordKind, company_id: int, record_id: int, *, archived: bool) -> None:
        if kind == "employee":
            require_sensitive(self.identity)
        with write_session(self._engine) as session:
            records = RecordRepository(session, company_id, RECORDS[kind].model)
            record = self._require_record(records, record_id)
            if (record.archived_at is not None) == archived:
                return
            records.set_archived(record, archived)
            action = "archived" if archived else "restored"
            ActivityRepository(session, company_id).record(action, kind, record.id, record.name)

    def list_categories(self, company_id: int) -> list[TemplateCategory]:
        with Session(self._engine) as session:
            return TemplateRepository(session, company_id).categories()

    def create_category(self, company_id: int, name: str) -> int:
        category_data = CategoryInput(name=name)
        try:
            with write_session(self._engine) as session:
                category = TemplateCategory(company_id=company_id, name=category_data.name)
                session.add(category)
                session.flush()
                ActivityRepository(session, company_id).record("created", "category", category.id, category.name)
                return category.id
        except IntegrityError as error:
            self._explain_duplicate(error, "This company already has a category with this name.")
            raise

    def duplicate_template(self, company_id: int, template_id: int) -> int:
        with write_session(self._engine) as session:
            records = RecordRepository(session, company_id, Template)
            templates = TemplateRepository(session, company_id)
            source = self._require_record(records, template_id)
            for index in count(1):
                suffix = " (copy)" if index == 1 else f" (copy {index})"
                name = source.name[:160 - len(suffix)].rstrip() + suffix
                if not templates.name_used(name):
                    break
            template = records.add({"name": name, "description": source.description, "category_id": source.category_id})
            draft = session.get(TemplateDraft, (company_id, source.id))
            version = latest_design_version(session, company_id, source.id)
            if (version is not None and version.metadata_snapshot.get("sensitive")
                    or draft is not None and uses_employee_data(checked_document(draft.document_json))):
                require_sensitive(self.identity)
            if draft is not None or version is not None:
                session.add(TemplateDraft(
                    company_id=company_id, template_id=template.id, revision=1,
                    document_json=(draft if draft is not None else version).document_json,
                ))
            ActivityRepository(session, company_id).record("duplicated", "template", template.id, template.name)
            return template.id

    def publish_template(self, company_id: int, template_id: int) -> int:
        with write_session(self._engine) as session:
            records = RecordRepository(session, company_id, Template)
            templates = TemplateRepository(session, company_id)
            template = self._require_record(records, template_id, archived=False)
            if template.status == "published":
                raise BusinessError("This template metadata is already published.")
            last = session.scalar(templates.versions(template_id).limit(1))
            number = 1 if last is None else last.version_number + 1
            category = templates.category(template.category_id) if template.category_id is not None else None
            version = TemplateVersion(
                company_id=company_id, template_id=template_id, version_number=number,
                metadata_snapshot={
                    "name": template.name, "description": template.description,
                    "category": category.name if category is not None else None,
                },
            )
            session.add(version)
            template.status = "published"
            ActivityRepository(session, company_id).record("published metadata", "template", template.id, template.name)
            return number

    def list_template_versions(self, company_id: int, template_id: int) -> list[TemplateVersion]:
        with Session(self._engine) as session:
            rows = list(session.scalars(TemplateRepository(session, company_id).versions(template_id)))
            if any(version.metadata_snapshot.get("sensitive") for version in rows):
                require_sensitive(self.identity)
            return rows

    @staticmethod
    def _require_record(records: RecordRepository, record_id: int, archived: bool | None = None):
        record = records.get(record_id)
        if record is None or (archived is not None and (record.archived_at is not None) != archived):
            raise RecordUnavailable("This record is unavailable in the current view. Refresh and try again.")
        return record

    @staticmethod
    def _explain_duplicate(error: IntegrityError, message: str) -> None:
        if getattr(error.orig, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE":
            raise DuplicateRecord(message) from error
