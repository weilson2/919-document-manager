from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from document_manager.persistence.database import (
    create_database_engine,
    migration_config,
    upgrade_database,
)
from document_manager.persistence.models import AppSetting, Company
from document_manager.services.errors import DuplicateRecord
from document_manager.services.settings import CompanyProfile, SettingsService


def test_foundation_creates_seeded_database_and_matches_models(database_engine):
    with database_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0005_payroll_and_access"
    with migration_config(database_engine) as config:
        command.check(config)
    profile = SettingsService(database_engine).get_company()
    assert profile.name == "919 RESTAURANT"
    assert profile.registration_number == "202603013939 (CT0159652-K)"
    assert profile.address.splitlines() == [
        "1 G2 BLK D,", "JALAN INDAH 12/2,", "TAMAN INDAH,", "84000 MUAR,", "JOHOR, MALAYSIA."
    ]


def test_edits_survive_restart_and_repeated_migrations(database_engine):
    profile = CompanyProfile(name="New name", registration_number="NEW-01", address="Muar\n麻坡")
    SettingsService(database_engine).save_company(profile)
    reopened = create_database_engine(Path(database_engine.url.database))
    try:
        upgrade_database(reopened)
        assert SettingsService(reopened).get_company() == profile
        with Session(reopened) as session:
            assert session.scalar(select(func.count()).select_from(Company)) == 1
    finally:
        reopened.dispose()


def test_duplicate_registration_rolls_back_profile_update(database_engine):
    with Session(database_engine) as session, session.begin():
        session.add(Company(name="Another company", registration_number="OTHER", address="Johor"))

    settings = SettingsService(database_engine)
    original = settings.get_company()
    with pytest.raises(DuplicateRecord, match="registration number"):
        settings.save_company(CompanyProfile(name="Unsaved", registration_number="other", address="Muar"))
    assert settings.get_company() == original


def test_active_company_foreign_key_is_enforced(database_engine):
    with pytest.raises(IntegrityError), Session(database_engine) as session, session.begin():
        setting = session.get_one(AppSetting, 1)
        setting.active_company_id = 999

    with pytest.raises(IntegrityError), Session(database_engine) as session, session.begin():
        session.delete(session.get_one(Company, 1))


def test_migration_rolls_back_ddl_and_seed_when_startup_fails(tmp_path):
    engine = create_database_engine(tmp_path / "rollback.sqlite3")
    try:
        with pytest.raises(RuntimeError, match="interrupted migration"), migration_config(engine) as config:
            command.upgrade(config, "head")
            raise RuntimeError("interrupted migration")
        assert inspect(engine).get_table_names() == []
        upgrade_database(engine)
        assert SettingsService(engine).get_company().name == "919 RESTAURANT"
    finally:
        engine.dispose()


def test_existing_unversioned_database_is_left_intact(tmp_path):
    engine = create_database_engine(tmp_path / "other.sqlite3")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE other (id INTEGER PRIMARY KEY)")
        with pytest.raises(RuntimeError, match="unrecognized database"):
            upgrade_database(engine)
        assert inspect(engine).get_table_names() == ["other"]
    finally:
        engine.dispose()


def test_m0_database_upgrade_preserves_profiles_and_default_selection(tmp_path):
    engine = create_database_engine(tmp_path / "from-m0.sqlite3")
    try:
        with migration_config(engine) as config:
            command.upgrade(config, "0001_foundation")
            connection = config.attributes["connection"]
            connection.execute(text("UPDATE companies SET name = 'Retained M0 name' WHERE id = 1"))
            connection.execute(text(
                "INSERT INTO companies (id, name, registration_number, address) VALUES (2, 'Second', 'BRN-2', 'Muar')"
            ))
            connection.execute(text("UPDATE settings SET active_company_id = 2"))
        upgrade_database(engine)

        settings = SettingsService(engine)
        assert settings.get_company(1).name == "Retained M0 name"
        assert settings.get_default_company_id() == 2
        assert settings.get_company().registration_number == "BRN-2"
        assert settings.get_company().document_settings.page_size == "A4"
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        engine.dispose()


def test_m1_metadata_versions_survive_release_migrations(tmp_path):
    engine = create_database_engine(tmp_path / "m1.sqlite3")
    try:
        with migration_config(engine) as config:
            command.upgrade(config, "0002_business_data")
            connection = config.attributes["connection"]
            connection.execute(text("INSERT INTO templates (id, company_id, name, status) VALUES (9,1,'Retained','published')"))
            connection.execute(text(
                "INSERT INTO template_versions (company_id, template_id, version_number, metadata_snapshot) "
                "VALUES (1,9,1,:snapshot)"
            ), {"snapshot": '{"name":"Retained"}'})
        upgrade_database(engine)
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT version_number,metadata_snapshot,document_json FROM template_versions WHERE template_id=9"
            )).one() == (1, '{"name":"Retained"}', None)
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        engine.dispose()
