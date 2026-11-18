from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from document_manager.editor.fields import (
    FLAG_TYPES,
    REFERENCE_TYPES,
    DateRange,
    FieldDefinition,
    calendar_date,
)
from document_manager.editor.visual_schema import FieldDocument
from document_manager.persistence.models import Company, Employee, Tenant
from document_manager.services.auth import require_sensitive
from document_manager.services.designs import uses_employee_data
from document_manager.services.errors import BusinessError

Subject = Literal["tenant", "employee"]
SUBJECTS = {"tenant": Tenant, "employee": Employee}


@dataclass(frozen=True)
class FilledValues:
    inputs: dict
    text_by_id: dict[str, str]
    subject_kind: Subject | None
    subject_id: int | None
    subject_name: str


class FillService:
    def __init__(self, engine: Engine, identity=None):
        self._engine = engine
        self._identity = identity

    def choices(self, company_id: int, kind: str) -> list[tuple[int, str]]:
        if kind == "employee":
            require_sensitive(self._identity)
        with Session(self._engine) as session:
            if kind == "company":
                company = session.get_one(Company, company_id)
                return [(company.id, company.name)]
            model = SUBJECTS[kind]
            return list(session.execute(select(model.id, model.name).where(
                model.company_id == company_id, model.archived_at.is_(None),
            ).order_by(model.name, model.id)).tuples())

    def company_logo(self, company_id: int) -> bytes | None:
        with Session(self._engine) as session:
            return session.scalar(select(Company.logo).where(Company.id == company_id))

    def suggested(self, company_id: int, design: FieldDocument, subjects: dict[str, int]) -> dict:
        self._require_design_access(design, subjects)
        with Session(self._engine) as session:
            records = {
                "company": session.get_one(Company, company_id),
                **{kind: self._subject(session, company_id, kind, pk) for kind, pk in subjects.items()},
            }
            values = {}
            for field in design.fields:
                initial = field.default.model_dump() if isinstance(field.default, DateRange) else field.default
                if field.type in REFERENCE_TYPES:
                    kind = field.type.removesuffix("_reference")
                    if kind in records:
                        initial = str(records[kind].id)
                if field.binding:
                    kind, property_name = field.binding.split(".", 1)
                    if (record := records.get(kind)) is not None:
                        value = getattr(record, property_name)
                        if isinstance(value, (date, Decimal)):
                            value = str(value)
                        initial = initial if value is None else value
                values[field.id] = initial
            return values

    def capture(
        self, company_id: int, design: FieldDocument, values: dict, subjects: dict[str, int],
    ) -> FilledValues:
        self._require_design_access(design, subjects)
        definitions = {field.id: field for field in design.fields}
        if values.keys() - definitions.keys():
            raise BusinessError("The form contains fields from a different template version.")
        captured, display = {}, {}
        with Session(self._engine) as session:
            records = {kind: self._subject(session, company_id, kind, pk, archived=True) for kind, pk in subjects.items()}
            for key, field in definitions.items():
                try:
                    value = field.validate_value(values.get(key))
                    captured[key] = value.model_dump() if isinstance(value, DateRange) else value
                    if value is not None and field.type in REFERENCE_TYPES:
                        kind = field.type.removesuffix("_reference")
                        if kind == "company":
                            if int(value) != company_id:
                                raise ValueError("Choose the active company.")
                            display[key] = session.get_one(Company, company_id).name
                        else:
                            display[key] = self._subject(session, company_id, kind, int(value), archived=True).name
                    else:
                        display[key] = format_value(field, value)
                except ValueError as error:
                    detail = error.errors()[0]["msg"].removeprefix("Value error, ") if hasattr(error, "errors") else str(error)
                    raise BusinessError(f"{field.label} — {detail}") from None
            kind = next(iter(records), None)
            subject = records.get(kind)
            return FilledValues(
                captured, display, kind, subject.id if subject else None, subject.name if subject else "",
            )

    def _require_design_access(self, design, subjects):
        if "employee" in subjects or uses_employee_data(design):
            require_sensitive(self._identity)

    @staticmethod
    def _subject(session, company_id, kind, pk, *, archived=False):
        model = SUBJECTS.get(kind)
        if model is None or type(pk) is not int:
            raise BusinessError("Choose an available tenant or employee.")
        query = select(model).where(model.id == pk, model.company_id == company_id)
        if not archived:
            query = query.where(model.archived_at.is_(None))
        record = session.scalar(query)
        if record is None:
            raise BusinessError("The selected record is unavailable in the active company.")
        return record


def format_value(field: FieldDefinition, value) -> str:
    if value is None:
        return ""
    style = field.formatting.style
    if field.type == "currency":
        prefix = "MYR" if style == "code" else "RM"
        return f"{prefix} {Decimal(value):,.2f}"
    if field.type in FLAG_TYPES:
        if style == "true_false":
            return "True" if value else "False"
        return "Yes" if value else "No"
    if field.type in {"date", "date_range"}:
        def display_date(raw: str) -> str:
            parsed = calendar_date(raw)
            if style == "long":
                return parsed.strftime("%d %B %Y")
            return parsed.strftime("%d/%m/%Y") if style == "dmy" else raw

        if isinstance(value, DateRange):
            return f"{display_date(value.start)} – {display_date(value.end)}"
        return display_date(value)
    if field.type in {"number", "decimal"} and field.formatting.decimals is not None:
        return f"{Decimal(value):.{field.formatting.decimals}f}"
    if style in {"lower", "upper"}:
        return value.upper() if style == "upper" else value.lower()
    return value
