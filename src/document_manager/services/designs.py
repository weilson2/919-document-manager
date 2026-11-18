from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from document_manager.editor.schema import MAX_REQUEST_BYTES
from document_manager.editor.visual_schema import (
    FieldDocument,
    PageSettings,
    blank_visual_document,
)
from document_manager.persistence.database import write_session
from document_manager.persistence.models import (
    Company,
    Template,
    TemplateDraft,
    TemplateVersion,
)
from document_manager.persistence.repositories import (
    ActivityRepository,
    RecordRepository,
    TemplateRepository,
)
from document_manager.services.auth import require_sensitive
from document_manager.services.errors import BusinessError, RecordUnavailable


class StaleDraft(BusinessError):
    pass


@dataclass(frozen=True)
class Design:
    name: str
    revision: int
    document: FieldDocument


def checked_document(value: dict | FieldDocument) -> FieldDocument:
    document = FieldDocument.model_validate(value.model_dump(exclude_unset=True) if isinstance(value, FieldDocument) else value)
    if len(document.model_dump_json(exclude_unset=True).encode("utf-8")) > MAX_REQUEST_BYTES - 4096:
        raise BusinessError("The template design exceeds the editor's size limit.")
    return document


def latest_design_version(session: Session, company_id: int, template_id: int) -> TemplateVersion | None:
    versions = TemplateRepository(session, company_id).versions(template_id)
    return session.scalar(versions.where(TemplateVersion.document_json.is_not(None)).limit(1))


class DesignService:
    def __init__(self, engine: Engine, identity=None):
        self._engine = engine
        self._identity = identity

    def open(self, company_id: int, template_id: int) -> Design:
        with Session(self._engine) as session:
            template = self._template(session, company_id, template_id)
            draft = session.get(TemplateDraft, (company_id, template_id))
            published = latest_design_version(session, company_id, template_id)
            if published is not None and published.metadata_snapshot.get("sensitive"):
                require_sensitive(self._identity)
            if draft is not None:
                document = checked_document(draft.document_json)
                if uses_employee_data(document):
                    require_sensitive(self._identity)
                return Design(template.name, draft.revision, document)
            if published is not None:
                return Design(template.name, 0, checked_document(published.document_json))
            settings = PageSettings.model_validate(session.get_one(Company, company_id).document_settings)
            return Design(template.name, 0, blank_visual_document(settings, 3))

    def save(
        self, company_id: int, template_id: int, revision: int, value: dict | FieldDocument, *, publish: bool = False,
    ) -> tuple[int, int | None]:
        validated = checked_document(value)
        if uses_employee_data(validated):
            require_sensitive(self._identity)
        document = validated.model_dump(mode="json", exclude_unset=True)
        with write_session(self._engine) as session:
            template = self._template(session, company_id, template_id)
            draft = session.get(TemplateDraft, (company_id, template_id))
            published = latest_design_version(session, company_id, template_id)
            if (published is not None and published.metadata_snapshot.get("sensitive")
                    or draft is not None and uses_employee_data(checked_document(draft.document_json))):
                require_sensitive(self._identity)
            current = 0 if draft is None else draft.revision
            if revision != current:
                raise StaleDraft("A newer design was saved. Reopen the template to load it.")
            if draft is None:
                current = 1
                draft = TemplateDraft(
                    company_id=company_id, template_id=template_id, revision=current, document_json=document,
                )
                session.add(draft)
                template.status = "draft"
            elif draft.document_json != document:
                current += 1
                draft.revision = current
                draft.document_json = document
                template.status = "draft"
            return current, self.publish_version(session, template, document) if publish else None

    def published(self, company_id: int, template_id: int) -> TemplateVersion:
        with Session(self._engine) as session:
            self._template(session, company_id, template_id)
            version = latest_design_version(session, company_id, template_id)
            if version is None:
                raise BusinessError("Publish a design before creating a document from this template.")
            if version.metadata_snapshot.get("sensitive"):
                require_sensitive(self._identity)
            return version

    def published_list(self, company_id: int) -> list[Template]:
        with Session(self._engine) as session:
            return list(session.scalars(select(Template).where(
                Template.company_id == company_id,
                Template.archived_at.is_(None),
                select(TemplateVersion.id).where(
                    TemplateVersion.company_id == company_id,
                    TemplateVersion.template_id == Template.id,
                    TemplateVersion.document_json.is_not(None),
                ).exists(),
            ).order_by(Template.name)))

    def payroll_design(self, company_id: int) -> TemplateVersion:
        with Session(self._engine) as session:
            version = TemplateVersion
            result = session.scalar(select(version).join(
                Template, (Template.company_id == version.company_id) & (Template.id == version.template_id),
            ).where(
                version.company_id == company_id, Template.archived_at.is_(None),
                version.document_json.is_not(None), version.metadata_snapshot["purpose"].as_string() == "payroll",
            ).order_by(version.id.desc()).limit(1))
            if result is None:
                raise BusinessError("Restore the Employee Payslip template or publish its design.")
            return result

    def starter_template(self, company_id: int, name: str) -> int | None:
        with Session(self._engine) as session:
            version = TemplateVersion
            return session.scalar(select(version.template_id).join(
                Template, (Template.company_id == version.company_id) & (Template.id == version.template_id),
            ).where(
                version.company_id == company_id, Template.archived_at.is_(None),
                version.document_json.is_not(None), version.metadata_snapshot["starter_name"].as_string() == name,
            ).order_by(version.id.desc()).limit(1))

    @staticmethod
    def _template(session: Session, company_id: int, template_id: int) -> Template:
        template = RecordRepository(session, company_id, Template).get(template_id)
        if template is None or template.archived_at is not None:
            raise RecordUnavailable("This template is unavailable in the active company.")
        return template

    @staticmethod
    def publish_version(
        session: Session, template: Template, document: dict, *,
        purpose: str | None = None, starter_name: str | None = None,
    ) -> int:
        templates = TemplateRepository(session, template.company_id)
        last = session.scalar(templates.versions(template.id).limit(1))
        category = templates.category(template.category_id) if template.category_id is not None else None
        metadata = {
            "name": template.name, "description": template.description,
            "category": category.name if category is not None else None,
            "category_id": template.category_id,
        }
        if last is not None:
            purpose = purpose or last.metadata_snapshot.get("purpose")
            starter_name = starter_name or last.metadata_snapshot.get("starter_name")
        if purpose is not None:
            metadata["purpose"] = purpose
        if starter_name is not None:
            metadata["starter_name"] = starter_name
        if purpose == "payroll" or any(
            field["type"] == "employee_reference" or (field.get("binding") or "").startswith("employee.")
            for field in document["fields"]
        ):
            metadata["sensitive"] = True
        if last is not None and last.document_json == document and last.metadata_snapshot == metadata:
            template.status = "published"
            return last.version_number
        number = 1 if last is None else last.version_number + 1
        session.add(TemplateVersion(
            company_id=template.company_id, template_id=template.id, version_number=number,
            metadata_snapshot=metadata, document_json=document,
        ))
        template.status = "published"
        ActivityRepository(session, template.company_id).record("published design", "template", template.id, template.name)
        return number


def uses_employee_data(design: FieldDocument) -> bool:
    return any(field.type == "employee_reference" or (field.binding or "").startswith("employee.") for field in design.fields)
