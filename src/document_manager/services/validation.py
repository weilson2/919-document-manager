import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from document_manager.persistence.money import money_to_sen, sen_to_money

IDENTIFICATION_TYPES = {"nric": "NRIC", "passport": "Passport", "other": "Other"}
RECORD_STATUSES = {"active": "Active", "inactive": "Inactive", "ended": "Ended"}
RENTAL_TYPES = {"daily": "Daily", "monthly": "Monthly"}
SALARY_TYPES = {"monthly": "Monthly", "daily": "Daily", "hourly": "Hourly"}
CITIZENSHIP_TYPES = {
    "malaysian": "Malaysian citizen",
    "permanent_resident": "Permanent resident",
    "non_citizen": "Non-citizen",
}
TAX_RESIDENCIES = {"resident": "Resident", "non_resident": "Non-resident"}
EMPLOYMENT_TYPES = {"full_time": "Full-time", "part_time": "Part-time", "contract": "Fixed-term contract"}
TEMPLATE_STATUSES = {"draft": "Draft", "published": "Published"}

Name = Annotated[str, Field(min_length=1, max_length=200)]
ShortKey = Annotated[str, Field(min_length=1, max_length=80)]
Phone = Annotated[str, Field(max_length=40)]
Email = Annotated[str, Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]
Address = Annotated[str, Field(max_length=2000)]


def money_input(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise PydanticCustomError("money_type", "Enter the MYR amount as decimal text or an exact number.")
    if isinstance(value, str) and len(value) > 64:
        raise ValueError("Enter a valid MYR amount.")
    return value


def exact_money(value: Decimal) -> Decimal:
    return sen_to_money(money_to_sen(value))


MoneyValue = Annotated[Decimal, BeforeValidator(money_input), AfterValidator(exact_money)]


def date_input(value):
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value.strip()):
        return value.strip()
    raise PydanticCustomError("calendar_date", "Use a date in YYYY-MM-DD format.")


DateValue = Annotated[date, BeforeValidator(date_input)]


class ValidatedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", frozen=True, from_attributes=True)


class PersonDetails(ValidatedInput):
    name: Name
    identification_type: Literal["nric", "passport", "other"]
    identification_number: ShortKey
    phone: Phone | None = None
    address: Address | None = None
    start_date: DateValue
    status: Literal["active", "inactive", "ended"] = "active"


class TenantInput(PersonDetails):
    stall_number: ShortKey
    rental_type: Literal["daily", "monthly"]
    rental_amount: MoneyValue
    deposit: MoneyValue
    end_date: DateValue | None = None

    @field_validator("end_date")
    @classmethod
    def check_end_date(cls, value: date | None, info: ValidationInfo) -> date | None:
        start = info.data.get("start_date")
        if value is not None and start is not None and value < start:
            raise ValueError("The end date must be on or after the start date.")
        return value


class EmployeeInput(PersonDetails):
    employee_number: ShortKey
    email: Email | None = None
    position: Annotated[str, Field(min_length=1, max_length=150)]
    salary_type: Literal["monthly", "daily", "hourly"]
    basic_salary: MoneyValue
    birth_date: DateValue | None = None
    citizenship: Literal["malaysian", "permanent_resident", "non_citizen"] | None = None
    tax_residency: Literal["resident", "non_resident"] | None = None
    employment_type: Literal["full_time", "part_time", "contract"] | None = None

    @field_validator("birth_date")
    @classmethod
    def check_birth_date(cls, value: date | None, info: ValidationInfo) -> date | None:
        if value is not None and (value > date.today() or value > info.data.get("start_date", date.max)):
            raise ValueError("The birth date must be on or before the start date and today's date.")
        return value


class TemplateInput(ValidatedInput):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Address | None = None
    category_id: Annotated[int, Field(gt=0, strict=True)] | None = None


class CategoryInput(ValidatedInput):
    name: Annotated[str, Field(min_length=1, max_length=120)]
