from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    registration_number: Mapped[str] = mapped_column(String(100), unique=True)
    address: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class AppSetting(Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    active_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
