from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from document_manager.persistence.models import AppSetting, Company


class CompanyProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True, from_attributes=True)

    name: str = Field(min_length=1, max_length=200)
    registration_number: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=2000)


class SettingsService:
    def __init__(self, engine: Engine):
        self._engine = engine

    def get_company(self) -> CompanyProfile:
        with Session(self._engine) as session:
            company = session.scalars(
                select(Company).join(AppSetting, AppSetting.active_company_id == Company.id)
            ).one()
            return CompanyProfile.model_validate(company)

    def save_company(self, profile: CompanyProfile) -> None:
        active_company_id = select(AppSetting.active_company_id).scalar_subquery()
        with Session(self._engine) as session, session.begin():
            result = session.execute(
                update(Company).where(Company.id == active_company_id).values(**profile.model_dump())
            )
            if result.rowcount != 1:
                raise RuntimeError("Active company settings are missing.")
