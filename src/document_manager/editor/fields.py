import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from document_manager.editor.schema import StrictModel

FieldId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
FieldType = Literal[
    "text", "multiline", "number", "currency", "date", "date_range",
    "dropdown", "checkbox", "boolean", "phone", "email", "address",
    "integer", "decimal", "tenant_reference", "employee_reference", "company_reference",
]
FieldBinding = Literal[
    "company.name", "company.registration_number", "company.address", "company.phone", "company.email",
    "tenant.name", "tenant.identification_number", "tenant.phone", "tenant.address", "tenant.stall_number",
    "tenant.rental_type", "tenant.rental_amount", "tenant.deposit", "tenant.start_date", "tenant.end_date",
    "employee.name", "employee.employee_number", "employee.position", "employee.basic_salary",
    "employee.start_date", "employee.phone", "employee.email", "employee.address",
]
TEXT_TYPES = {"text", "multiline", "phone", "email", "address"}
NUMERIC_TYPES = {"number", "integer", "decimal", "currency"}
DATE_TYPES = {"date", "date_range"}
FLAG_TYPES = {"checkbox", "boolean"}
REFERENCE_TYPES = {"tenant_reference", "employee_reference", "company_reference"}


def decimal_value(value: str, kind: str) -> Decimal:
    if kind == "integer":
        if not re.fullmatch(r"-?[0-9]{1,15}", value):
            raise ValueError("Enter a whole number.")
        return Decimal(value)
    fraction = 2 if kind == "currency" else 6
    if not re.fullmatch(rf"-?[0-9]{{1,15}}(?:\.[0-9]{{1,{fraction}}})?", value):
        raise ValueError(f"Enter a {kind} with up to {fraction} decimal places.")
    return Decimal(value)


def calendar_date(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Use YYYY-MM-DD.")
    return date.fromisoformat(value)


class FieldReference(StrictModel):
    fieldId: FieldId


class DateRange(StrictModel):
    start: str
    end: str


class FieldRules(StrictModel):
    min_length: Annotated[int, Field(ge=0, le=4000)] | None = None
    max_length: Annotated[int, Field(ge=0, le=4000)] | None = None
    min: str | None = None
    max: str | None = None
    options: list[Annotated[str, Field(min_length=1, max_length=120)]] | None = Field(default=None, max_length=100)


class FieldFormatting(StrictModel):
    style: str | None = None
    decimals: Annotated[int, Field(ge=0, le=6)] | None = None


def check_bounds(low, high, values):
    if low is not None and high is not None and low > high:
        raise ValueError("The minimum must not exceed the maximum.")
    if any(low is not None and item < low or high is not None and item > high for item in values):
        raise ValueError("The default falls outside the allowed range.")


class FieldDefinition(StrictModel):
    id: FieldId
    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    type: FieldType
    required: bool
    default: Annotated[str, Field(max_length=4000)] | bool | DateRange | None
    validation: FieldRules
    formatting: FieldFormatting
    description: Annotated[str, Field(max_length=400)] | None = None
    binding: FieldBinding | None = None

    def validate_value(self, value):
        if value is None or isinstance(value, str) and not value.strip():
            if self.required:
                raise ValueError("Enter a value for this required field.")
            return None
        payload = self.model_dump(exclude_unset=True)
        payload["default"] = value
        return self.model_validate(payload).default

    @model_validator(mode="after")
    def check_configuration(self):
        kind, value, rules = self.type, self.default, self.validation
        if not self.label.strip():
            raise ValueError("Enter a field label.")
        allowed = (
            {"min_length", "max_length"} if kind in TEXT_TYPES else
            {"min", "max"} if kind in NUMERIC_TYPES | DATE_TYPES else
            {"options"} if kind == "dropdown" else set()
        )
        if rules.model_fields_set - allowed or any(getattr(rules, key) is None for key in rules.model_fields_set):
            raise ValueError("Unsupported validation rule for this field type.")
        self._check_format()
        if kind in REFERENCE_TYPES and self.binding is not None:
            raise ValueError("A record selector cannot be bound to a record property.")
        if kind in FLAG_TYPES:
            if value is not None and type(value) is not bool:
                raise ValueError("The default must be a boolean.")
        elif kind == "date_range":
            if value is not None and not isinstance(value, DateRange):
                raise ValueError("Provide both dates.")
            dates = [] if value is None else [calendar_date(value.start), calendar_date(value.end)]
            if dates != sorted(dates):
                raise ValueError("The end date must not precede the start date.")
            check_bounds(self._bound(rules.min, calendar_date), self._bound(rules.max, calendar_date), dates)
        else:
            if value is not None and not isinstance(value, str):
                raise ValueError("The default must be text.")
            self._check_string(value)
        return self

    @staticmethod
    def _bound(value, convert):
        return None if value is None else convert(value)

    def _check_string(self, value):
        kind, rules = self.type, self.validation
        if kind in REFERENCE_TYPES:
            if value is not None and not re.fullmatch(r"[1-9][0-9]{0,15}", value):
                raise ValueError("Choose an available record.")
        elif kind in NUMERIC_TYPES | {"date"}:
            convert = calendar_date if kind == "date" else lambda raw: decimal_value(raw, kind)
            check_bounds(self._bound(rules.min, convert), self._bound(rules.max, convert),
                         [] if value is None else [convert(value)])
        elif kind == "dropdown":
            options = rules.options or []
            if not options or len(options) != len(set(options)) or any(not option.strip() for option in options):
                raise ValueError("Provide distinct dropdown choices.")
            if value is not None and value not in options:
                raise ValueError("Choose a listed default.")
        else:
            check_bounds(rules.min_length, rules.max_length, [] if value is None else [len(value)])
            if value is None:
                return
            if kind not in {"multiline", "address"} and ("\r" in value or "\n" in value):
                raise ValueError("Use a single line for this field type.")
            if kind == "phone" and (
                not re.fullmatch(r"\+?[0-9 ().-]+", value) or not 3 <= sum(c.isdigit() for c in value) <= 20
            ):
                raise ValueError("Enter a phone number.")
            if kind == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                raise ValueError("Enter an email address.")

    def _check_format(self):
        kind, formatting = self.type, self.formatting
        styles = (
            {"upper", "lower"} if kind in TEXT_TYPES else
            {"iso", "dmy", "long"} if kind in DATE_TYPES else
            {"symbol", "code"} if kind == "currency" else
            {"yes_no", "true_false"} if kind in FLAG_TYPES else set()
        )
        if "style" in formatting.model_fields_set and formatting.style not in styles:
            raise ValueError("Unsupported display style.")
        if "decimals" in formatting.model_fields_set and (kind not in {"number", "decimal"} or formatting.decimals is None):
            raise ValueError("Decimal display is available for Number and Decimal fields.")
