from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from document_manager.persistence.database import (
    create_database_engine,
    upgrade_database,
)
from document_manager.services.business import BusinessService
from document_manager.services.errors import (
    BusinessError,
    DuplicateRecord,
    RecordUnavailable,
)
from document_manager.services.settings import (
    CompanyProfile,
    DocumentSettings,
    SettingsService,
)

TENANT = {
    "name": "Aminah 100%",
    "identification_type": "passport",
    "identification_number": "P-100",
    "phone": "012-1234567",
    "address": "Taman Indah",
    "stall_number": "ST-01",
    "rental_type": "daily",
    "rental_amount": "18.05",
    "deposit": "50.00",
    "start_date": "2026-10-01",
    "end_date": "2026-11-01",
}
EMPLOYEE = {
    "name": "李美丽",
    "identification_type": "passport",
    "identification_number": "E-100",
    "employee_number": "STAFF-100",
    "email": "staff@example.com",
    "position": "Cashier",
    "salary_type": "monthly",
    "basic_salary": "3500.10",
    "start_date": "2026-10-01",
    "birth_date": "2001-10-05",
    "citizenship": "malaysian",
    "tax_residency": "resident",
    "employment_type": "full_time",
}


def another_company(settings):
    return settings.create_company(CompanyProfile(name="Second Company", registration_number="CO-02", address="Muar"))


@pytest.mark.parametrize(("kind", "data", "amount_field", "expected"), [
    ("tenant", TENANT, "rental_amount", Decimal("18.05")),
    ("employee", EMPLOYEE, "basic_salary", Decimal("3500.10")),
])
def test_company_scoped_crud_search_archive_restore_and_restart(database_engine, kind, data, amount_field, expected):
    business = BusinessService(database_engine)
    settings = SettingsService(database_engine)
    second = another_company(settings)
    first_record = business.save_record(kind, 1, data)
    business.save_record(kind, second, {**data, "name": "Other scope"})

    assert [record.name for record in business.list_records(kind, 1)] == [data["name"]]
    search = "%" if kind == "tenant" else "staff-100"
    record, = business.list_records(kind, 1, search=search, status="active")
    assert record.id == first_record
    assert getattr(record, amount_field) == expected
    assert isinstance(getattr(record, amount_field), Decimal)
    assert not business.list_records(kind, second, search=data["name"])
    with pytest.raises(DuplicateRecord):
        business.save_record(kind, 1, {**data, "identification_number": data["identification_number"].lower()})
    with pytest.raises(RecordUnavailable):
        business.save_record(kind, second, data, first_record)
    with pytest.raises(RecordUnavailable):
        business.set_archived(kind, second, first_record, archived=True)

    change = {**data, "name": "Updated", "status": "inactive"}
    business.save_record(kind, 1, change, first_record)
    assert business.list_records(kind, 1, status="active") == []
    business.set_archived(kind, 1, first_record, archived=True)
    assert business.list_records(kind, 1) == []
    with pytest.raises(DuplicateRecord):
        business.save_record(kind, 1, data)

    reopened = create_database_engine(Path(database_engine.url.database))
    try:
        upgrade_database(reopened)
        restarted = BusinessService(reopened)
        archived, = restarted.list_records(kind, 1, archived=True)
        assert (archived.id, archived.name, archived.status) == (first_record, "Updated", "inactive")
        restarted.set_archived(kind, 1, first_record, archived=False)
        restored, = restarted.list_records(kind, 1)
        assert restored.id == first_record
        assert restored.status == "inactive"
        assert restarted.list_records(kind, second)[0].name == "Other scope"
        assert restarted.dashboard(1).activity[0].action == "restored"
        assert all(event.subject_label != "Updated" for event in restarted.dashboard(second).activity)
    finally:
        reopened.dispose()


@pytest.mark.parametrize("invalid", ["-1", "0.001", "NaN", "Infinity", "1000000000.00", 0.1, True, "", "0.010000000000000000000001"])
def test_invalid_money_is_rejected_without_side_effects(database_engine, invalid):
    business = BusinessService(database_engine)
    with pytest.raises(ValidationError):
        business.save_record("tenant", 1, {**TENANT, "deposit": invalid})
    assert business.list_records("tenant", 1) == []
    assert business.dashboard(1).activity == []


def test_money_is_stored_as_integer_sen_and_invalid_dates_fail(database_engine):
    business = BusinessService(database_engine)
    business.save_record("tenant", 1, TENANT)
    business.save_record("employee", 1, EMPLOYEE)
    with database_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT rental_sen, deposit_sen, typeof(rental_sen) FROM tenants").one() == (
            1805, 5000, "integer",
        )
        assert connection.exec_driver_sql("SELECT salary_sen FROM employees").scalar_one() == 350010
    with pytest.raises(ValidationError, match="on or after"):
        business.save_record("tenant", 1, {**TENANT, "end_date": "2026-09-30"})
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        business.save_record("tenant", 1, {**TENANT, "start_date": "0"})
    with pytest.raises(ValidationError, match="birth date"):
        business.save_record("employee", 1, {**EMPLOYEE, "birth_date": "2026-11-01"})
    with pytest.raises(DuplicateRecord, match="staff number"):
        business.save_record("employee", 1, {**EMPLOYEE, "identification_number": "OTHER-ID"})


def test_company_profiles_store_separate_document_settings_and_default(database_engine):
    settings = SettingsService(database_engine)
    second = another_company(settings)
    assert settings.get_default_company_id() == 1
    assert settings.get_company(second).document_settings == DocumentSettings()
    profile = CompanyProfile(
        name="Second", registration_number="CO-02", address="Muar", contact_name="Ali",
        phone="012-12345678", email="ali@example.com",
        document_settings=DocumentSettings(page_size="A5", orientation="landscape", margin_right=12),
    )
    settings.save_company(profile, second)
    settings.set_default_company(second)
    reloaded = SettingsService(database_engine)
    assert reloaded.get_default_company_id() == second
    assert reloaded.get_company() == profile
    assert reloaded.get_company(1).document_settings == DocumentSettings()
    with pytest.raises(RecordUnavailable):
        settings.set_default_company(999)
    assert reloaded.get_default_company_id() == second


def test_template_workflow_keeps_published_metadata_and_categories_isolated(database_engine):
    service = BusinessService(database_engine)
    second = another_company(SettingsService(database_engine))
    category = service.create_category(1, "Operations")
    other_category = service.create_category(second, "Operations")
    with pytest.raises(DuplicateRecord, match="category"):
        service.create_category(1, "operations")
    with pytest.raises(RecordUnavailable, match="belonging to this company"):
        service.save_record("template", 1, {"name": "Trial", "category_id": other_category})

    template_id = service.save_record("template", 1, {"name": "Receipt", "category_id": category})
    assert service.list_records("template", 1, category_id=category, status="draft")[0].id == template_id
    assert service.publish_template(1, template_id) == 1
    with pytest.raises(BusinessError, match="already published"):
        service.publish_template(1, template_id)
    with pytest.raises(RecordUnavailable):
        service.duplicate_template(second, template_id)

    service.save_record("template", 1, {"name": "Renamed", "category_id": category}, template_id)
    assert service.list_records("template", 1)[0].status == "draft"
    assert service.publish_template(1, template_id) == 2
    first_copy = service.duplicate_template(1, template_id)
    service.duplicate_template(1, template_id)
    assert {template.name for template in service.list_records("template", 1, status="draft")} == {
        "Renamed (copy)", "Renamed (copy 2)",
    }
    assert service.list_template_versions(1, first_copy) == []
    assert service.list_template_versions(second, template_id) == []
    versions = service.list_template_versions(1, template_id)
    assert [revision.metadata_snapshot["name"] for revision in versions] == ["Renamed", "Receipt"]
    assert versions[-1].metadata_snapshot["category"] == "Operations"
    assert all(revision.document_json is None for revision in versions)

    for statement in (
        "UPDATE template_versions SET version_number = 100",
        "DELETE FROM template_versions",
        (
            "INSERT OR REPLACE INTO template_versions (company_id, template_id, version_number, metadata_snapshot)"
            f" VALUES (1, {template_id}, 1, '{{}}')"
        ),
        f"UPDATE templates SET category_id = {other_category} WHERE id = {template_id}",
        (
            "INSERT INTO template_versions (company_id, template_id, version_number, metadata_snapshot)"
            f" VALUES ({second}, {template_id}, 8, '{{}}')"
        ),
    ):
        with pytest.raises(IntegrityError), database_engine.begin() as connection:
            connection.exec_driver_sql(statement)

    service.set_archived("template", 1, template_id, archived=True)
    assert service.dashboard(1).templates == 2
    service.set_archived("template", 1, template_id, archived=False)
    assert service.dashboard(1).templates == 3
    assert service.dashboard(second).templates == 0
    assert service.dashboard(1).documents is None
