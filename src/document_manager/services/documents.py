from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, defer

from document_manager.persistence.database import write_session
from document_manager.persistence.models import (
    DocumentExport,
    GeneratedDocument,
    PayrollDocument,
    PayrollRun,
    TemplateVersion,
)
from document_manager.persistence.repositories import (
    ActivityRepository,
    RecordRepository,
)
from document_manager.services.auth import require_sensitive
from document_manager.services.designs import checked_document
from document_manager.services.errors import BusinessError, RecordUnavailable
from document_manager.services.fill import FilledValues
from document_manager.services.payroll import PayrollService

MAX_PDF_BYTES = 60_000_000


@dataclass(frozen=True)
class DocumentSource:
    version: TemplateVersion
    values: dict
    subjects: dict


class DocumentService:
    def __init__(self, engine: Engine, identity=None):
        self._engine = engine
        self._identity = identity

    def save(self, company_id: int, version_id: int, filled: FilledValues, pdf: bytes, *, payroll_run_id=None) -> int:
        if not pdf.startswith(b"%PDF-") or not pdf.rstrip().endswith(b"%%EOF") or len(pdf) > MAX_PDF_BYTES:
            raise BusinessError("Generate a valid PDF under 60 MB before saving the document.")
        with write_session(self._engine) as session:
            version = self._version(session, company_id, version_id)
            fields = checked_document(version.document_json).fields
            ids = {field.id for field in fields}
            if ids != filled.inputs.keys() or ids != filled.text_by_id.keys():
                raise BusinessError("The filled data does not match the published template version.")
            metadata = version.metadata_snapshot
            if filled.subject_kind == "employee" or metadata.get("sensitive"):
                require_sensitive(self._identity)
            run = None
            if metadata.get("purpose") == "payroll" or payroll_run_id is not None:
                run = self._check_payroll(session, company_id, payroll_run_id, metadata, fields, filled)
            category = str(metadata.get("category_id") or 0)
            position = session.scalar(select(func.count()).select_from(GeneratedDocument).where(
                GeneratedDocument.company_id == company_id, GeneratedDocument.category_key == category,
            )) + 1
            document = GeneratedDocument(
                company_id=company_id, template_id=version.template_id, version_number=version.version_number,
                number=f"DOC-{category}-{position:06}", category_key=category,
                title=(metadata["name"][:143] + " · Draft payslip") if run and run.status == "draft" else metadata["name"],
                subject_kind=filled.subject_kind, subject_id=filled.subject_id, subject_name=filled.subject_name,
                input_values=filled.inputs, resolved_values=filled.text_by_id, pdf=pdf, checksum=sha256(pdf).hexdigest(),
            )
            session.add(document)
            session.flush()
            if run is not None:
                session.add(PayrollDocument(company_id=company_id, document_id=document.id, run_id=run.id))
            ActivityRepository(session, company_id).record("generated", "document", document.id, document.number)
            return document.id

    def list(self, company_id: int, search: str = "", *, archived=False, limit=None) -> list[GeneratedDocument]:
        with Session(self._engine) as session:
            model = GeneratedDocument
            query = self._query(company_id).options(
                defer(model.pdf), defer(model.input_values), defer(model.resolved_values),
            )
            query = query.where(model.archived_at.is_not(None) if archived else model.archived_at.is_(None))
            if search := search.strip():
                query = query.where(or_(*(field.icontains(search, autoescape=True) for field in (
                    model.number, model.title, model.subject_name,
                ))))
            return list(session.scalars(query.order_by(model.id.desc()).limit(limit)))

    def get(self, company_id: int, document_id: int) -> GeneratedDocument:
        with Session(self._engine) as session:
            document = self._get(session, company_id, document_id)
            if sha256(document.pdf).hexdigest() != document.checksum:
                raise BusinessError("The saved PDF failed its integrity check.")
            return document

    def source(self, company_id: int, document_id: int) -> DocumentSource:
        with Session(self._engine) as session:
            document = self._get(session, company_id, document_id, include_pdf=False)
            version = session.scalar(select(TemplateVersion).where(
                TemplateVersion.company_id == company_id, TemplateVersion.template_id == document.template_id,
                TemplateVersion.version_number == document.version_number,
            ))
            if version is None or version.document_json is None:
                raise BusinessError("The original template design is unavailable.")
            if version.metadata_snapshot.get("purpose") == "payroll":
                raise BusinessError("Create a payroll revision from Payroll to issue another payslip.")
            subjects = {document.subject_kind: document.subject_id} if document.subject_kind else {}
            return DocumentSource(version, document.input_values, subjects)

    def archive(self, company_id: int, document_id: int, archived: bool) -> None:
        with write_session(self._engine) as session:
            document = self._get(session, company_id, document_id, include_pdf=False)
            if (document.archived_at is not None) != archived:
                RecordRepository(session, company_id, GeneratedDocument).set_archived(document, archived)
                ActivityRepository(session, company_id).record(
                    "archived" if archived else "restored", "document", document_id, document.number,
                )

    def record_export(self, company_id: int, document_id: int, filename: str, checksum: str) -> None:
        with write_session(self._engine) as session:
            model = GeneratedDocument
            self._get(session, company_id, document_id, include_pdf=False)
            row = session.execute(select(model.checksum, func.length(model.pdf)).where(
                model.id == document_id, model.company_id == company_id,
            )).one_or_none()
            if row is None or row[0] != checksum:
                raise RecordUnavailable("The exported bytes do not match this document.")
            session.add(DocumentExport(
                company_id=company_id, document_id=document_id, filename=filename, byte_count=row[1], checksum=checksum,
            ))

    @staticmethod
    def _version(session, company_id, version_id):
        version = session.get(TemplateVersion, version_id)
        if version is None or version.company_id != company_id or version.document_json is None:
            raise RecordUnavailable("This company does not have the selected published design.")
        return version

    def _get(self, session, company_id, document_id, *, include_pdf=True):
        model = GeneratedDocument
        query = self._query(company_id).where(model.id == document_id)
        document = session.scalar(query if include_pdf else query.options(defer(model.pdf)))
        if document is None:
            raise RecordUnavailable("This document is unavailable in the active company.")
        return document

    def count(self, session, company_id):
        return session.scalar(select(func.count()).select_from(self._query(company_id).where(
            GeneratedDocument.archived_at.is_(None),
        ).with_only_columns(GeneratedDocument.id).subquery()))

    def _query(self, company_id):
        model = GeneratedDocument
        query = select(model).where(model.company_id == company_id)
        if self._identity is not None and not self._identity.sensitive_access:
            version = TemplateVersion
            sensitive = select(version.id).where(
                version.company_id == model.company_id, version.template_id == model.template_id,
                version.version_number == model.version_number,
                or_(version.metadata_snapshot["sensitive"].as_boolean().is_(True),
                    version.metadata_snapshot["purpose"].as_string() == "payroll"),
            ).exists()
            query = query.where(or_(model.subject_kind.is_(None), model.subject_kind != "employee"), ~sensitive)
        return query

    def _check_payroll(self, session, company_id, payroll_run_id, metadata, fields, filled):
        require_sensitive(self._identity)
        run = session.get(PayrollRun, payroll_run_id) if payroll_run_id is not None else None
        if (run is None or run.company_id != company_id or run.employee_id != filled.subject_id
                or filled.subject_kind != "employee" or metadata.get("purpose") != "payroll"):
            raise RecordUnavailable("Open a saved payroll revision to generate its payslip.")
        expected = PayrollService.payslip_values(run)
        for field in fields:
            if field.key in expected and filled.inputs[field.id] != expected[field.key]:
                raise BusinessError("The payslip values differ from the saved payroll revision.")
        return run
