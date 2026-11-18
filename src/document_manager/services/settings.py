import struct
from typing import Annotated, Literal

from pydantic import Field, field_validator
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from document_manager.persistence.database import write_session
from document_manager.persistence.models import Company
from document_manager.persistence.repositories import (
    ActivityRepository,
    CompanyRepository,
)
from document_manager.services.errors import DuplicateRecord, RecordUnavailable
from document_manager.services.validation import Email, Name, Phone, ValidatedInput

MAX_LOGO_BYTES = 2_000_000
MAX_LOGO_DIMENSION = 2048
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
Margin = Annotated[int, Field(ge=0, le=60)]


class DocumentSettings(ValidatedInput):
    page_size: Literal["A4", "A5"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    margin_top: Margin = 20
    margin_right: Margin = 20
    margin_bottom: Margin = 20
    margin_left: Margin = 20


class CompanyProfile(ValidatedInput):
    name: Name
    registration_number: Annotated[str, Field(min_length=1, max_length=100)]
    address: Annotated[str, Field(min_length=1, max_length=2000)]
    contact_name: Name | None = None
    phone: Phone | None = None
    email: Email | None = None
    logo: bytes | None = None
    document_settings: DocumentSettings = Field(default_factory=DocumentSettings)

    @field_validator("logo")
    @classmethod
    def check_logo(cls, logo: bytes | None) -> bytes | None:
        if logo is not None:
            if not 33 <= len(logo) <= MAX_LOGO_BYTES or not logo.startswith(PNG_HEADER):
                raise ValueError("Use a PNG logo of up to 2 MB.")
            width, height = struct.unpack_from(">II", logo, len(PNG_HEADER))
            if not 0 < width <= MAX_LOGO_DIMENSION or not 0 < height <= MAX_LOGO_DIMENSION:
                raise ValueError("Use a logo no larger than 2048 × 2048 pixels.")
        return logo


class SettingsService:
    def __init__(self, engine: Engine):
        self._engine = engine

    def list_companies(self) -> list[tuple[int, str, str]]:
        with Session(self._engine) as session:
            return [(row.id, row.name, row.registration_number) for row in CompanyRepository(session).list()]

    def get_default_company_id(self) -> int:
        with Session(self._engine) as session:
            return CompanyRepository(session).default().active_company_id

    def get_company(self, company_id: int | None = None) -> CompanyProfile:
        with Session(self._engine) as session:
            companies = CompanyRepository(session)
            target_id = companies.default().active_company_id if company_id is None else company_id
            return CompanyProfile.model_validate(self._require_company(companies, target_id))

    def set_default_company(self, company_id: int) -> None:
        with write_session(self._engine) as session:
            companies = CompanyRepository(session)
            company = self._require_company(companies, company_id)
            setting = companies.default()
            if setting.active_company_id != company_id:
                setting.active_company_id = company_id
                ActivityRepository(session, company_id).record("set default", "company", company_id, company.name)

    def create_company(self, profile: CompanyProfile) -> int:
        with write_session(self._engine) as session:
            companies = CompanyRepository(session)
            if companies.registration_used(profile.registration_number, None):
                raise DuplicateRecord("This registration number is already used by another company.")
            company = Company(**profile.model_dump())
            session.add(company)
            session.flush()
            ActivityRepository(session, company.id).record("created", "company", company.id, company.name)
            return company.id

    def save_company(self, profile: CompanyProfile, company_id: int | None = None) -> None:
        with write_session(self._engine) as session:
            companies = CompanyRepository(session)
            target_id = companies.default().active_company_id if company_id is None else company_id
            company = self._require_company(companies, target_id)
            if (
                profile.registration_number != company.registration_number
                and companies.registration_used(profile.registration_number, target_id)
            ):
                raise DuplicateRecord("This registration number is already used by another company.")
            if profile != CompanyProfile.model_validate(company):
                for key, value in profile.model_dump().items():
                    setattr(company, key, value)
                ActivityRepository(session, target_id).record("updated", "company", target_id, profile.name)

    @staticmethod
    def _require_company(companies: CompanyRepository, company_id: int) -> Company:
        company = companies.get(company_id)
        if company is None:
            raise RecordUnavailable("This company is unavailable.")
        return company
