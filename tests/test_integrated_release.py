from datetime import date
from decimal import Decimal
from hashlib import sha256

import pytest
from PySide6.QtCore import QBuffer
from PySide6.QtGui import QImage, QPainter, QPdfWriter
from sqlalchemy.exc import IntegrityError

from document_manager.editor.images import import_image, load_image
from document_manager.editor.print_layout import print_html
from document_manager.payroll import (
    ContributionBand,
    ContributionSchedule,
    PayrollInput,
    calculate,
)
from document_manager.persistence.database import (
    create_database_engine,
    upgrade_database,
    write_session,
)
from document_manager.persistence.models import GeneratedDocument, PayrollRun
from document_manager.services.auth import AuthService
from document_manager.services.backup import BackupService
from document_manager.services.business import BusinessService
from document_manager.services.designs import checked_document
from document_manager.services.errors import BusinessError, RecordUnavailable
from document_manager.services.settings import CompanyProfile, SettingsService


@pytest.fixture
def services(database_engine):
    business = BusinessService(database_engine)
    business.install_starters(1)
    templates = {row.name: row.id for row in business.designs.published_list(1)}
    return business, templates


@pytest.fixture
def pdf(qapp):
    device = QBuffer()
    device.open(QBuffer.OpenModeFlag.WriteOnly)
    writer = QPdfWriter(device)
    with QPainter(writer) as painter:
        painter.drawText(100, 100, "Fictional sample")
    return bytes(device.data())


def tenant(business):
    return business.save_record("tenant", 1, {
        "name": "Fictional Tenant", "identification_type": "other", "identification_number": "FAKE-01",
        "address": "Muar", "start_date": "2026-11-01", "stall_number": "B3", "rental_type": "monthly",
        "rental_amount": "1110.50", "deposit": "2240.60",
    })


def employee(business):
    return business.save_record("employee", 1, {
        "name": "Fictional Employee", "identification_type": "other", "identification_number": "FAKE-02",
        "employee_number": "F-001", "start_date": "2026-11-01", "position": "Service assistant",
        "salary_type": "monthly", "basic_salary": "2400.50",
    })


def test_rental_fill_reuse_and_original_immutability(services, database_engine, pdf):
    business, templates = services
    person = tenant(business)
    version = business.designs.published(1, templates["Stall Rental Agreement"])
    design = checked_document(version.document_json)
    fields = {field.key: field.id for field in design.fields}
    subjects = {"tenant": person}
    values = business.fill.suggested(1, design, subjects)
    assert values[fields["rent"]] == "1110.50"
    values[fields["terms"]] = '<script>alert("no")</script>'
    filled = business.fill.capture(1, design, values, subjects)
    markup = print_html(design, filled.text_by_id, lambda _asset: b"", inputs=filled.inputs)
    assert "&lt;script&gt;" in markup and "<script>" not in markup
    assert "RM 1,110.50" in markup
    original = business.documents.save(1, version.id, filled, pdf)
    with pytest.raises(IntegrityError), write_session(database_engine) as session:
        session.get_one(GeneratedDocument, original).pdf = b"modified"
    business.set_archived("template", 1, version.template_id, archived=True)
    business.set_archived("tenant", 1, person, archived=True)
    source = business.documents.source(1, original)
    source.values[fields["rent"]] = "1210.50"
    updated = business.fill.capture(1, design, source.values, source.subjects)
    duplicate = business.documents.save(1, source.version.id, updated, pdf)
    assert duplicate != original
    assert business.documents.get(1, original).resolved_values[fields["rent"]] == "RM 1,110.50"
    assert business.documents.get(1, duplicate).resolved_values[fields["rent"]] == "RM 1,210.50"
    assert business.documents.get(1, original).checksum == sha256(pdf).hexdigest()
    business.documents.record_export(1, original, "contract.pdf", sha256(pdf).hexdigest())
    business.documents.archive(1, original, True)
    assert [row.id for row in business.documents.list(1, "fictional")] == [duplicate]
    assert [row.id for row in business.documents.list(1, "fictional", archived=True)] == [original]

    other = SettingsService(database_engine).create_company(CompanyProfile(
        name="Other", registration_number="RELEASE-OTHER", address="Muar",
    ))
    with pytest.raises(RecordUnavailable):
        business.documents.get(other, original)
    with pytest.raises(BusinessError, match="active company"):
        business.fill.suggested(other, design, subjects)


def test_offer_and_employee_pdf_are_restricted_to_authorized_roles(services, database_engine, pdf):
    business, templates = services
    worker = employee(business)
    auth = AuthService(database_engine)
    owner = auth.enroll_owner("Owner", "Long fictitious secret")
    clerk = auth.add_user(owner, "clerk", "Clerk's separate secret", "clerk")
    assert auth.authenticate("OWNER", "Long fictitious secret") == owner
    assert auth.authenticate("owner", "wrong") is None
    with pytest.raises(BusinessError):
        auth.add_user(clerk, "unauthorized", "Another long secret", "owner")

    version = business.designs.published(1, templates["Employee Offer Letter"])
    design = checked_document(version.document_json)
    assert version.metadata_snapshot["sensitive"]
    subjects = {"employee": worker}
    values = business.fill.suggested(1, design, subjects)
    values.update({field.id: "As agreed" for field in design.fields if field.key in {"hours", "notice", "probation"}})
    captured = business.fill.capture(1, design, values, subjects)
    document = business.documents.save(1, version.id, captured, pdf)
    restricted = BusinessService(database_engine, clerk)
    assert restricted.documents.list(1) == []
    assert restricted.dashboard(1).documents == 0
    with pytest.raises(RecordUnavailable):
        restricted.documents.source(1, document)
    with pytest.raises(BusinessError, match="owner access"):
        restricted.fill.capture(1, design, values, subjects)
    with pytest.raises(BusinessError, match="owner access"):
        restricted.list_records("employee", 1)


def test_payroll_missing_rates_manual_reasons_and_immutable_revisions(services, database_engine, pdf):
    business, _ = services
    worker = employee(business)
    inputs = {
        "period": "2026-11-01", "basic": "2400.50", "overtime": "23.49", "advance": "5.10",
        "adjustments": {"epf": {"employee": "1.05", "employer": "2.20", "reason": "Fictional manual draft amount"}},
    }
    draft = business.payroll.calculate(1, worker, inputs)
    assert draft.amounts["net"] == Decimal("2417.84")
    assert draft.amounts["employer_cost"] == Decimal("2426.19")
    assert draft.amounts["employee_eis"] is None
    with pytest.raises(BusinessError, match="Approval blocked"):
        business.payroll.save(1, worker, inputs, approve=True)
    first = business.payroll.save(1, worker, inputs)
    second = business.payroll.save(1, worker, dict(inputs, overtime="20.19"))
    assert business.payroll.get(1, second).revision == 2
    with pytest.raises(IntegrityError), write_session(database_engine) as session:
        session.get_one(PayrollRun, first).status = "approved"
    run = business.payroll.get(1, first)
    version = business.designs.payroll_design(1)
    design = checked_document(version.document_json)
    values = business.fill.suggested(1, design, {"employee": worker})
    amounts = business.payroll.payslip_values(run)
    values.update({field.id: amounts[field.key] for field in design.fields if field.key in amounts})
    captured = business.fill.capture(1, design, values, {"employee": worker})
    document = business.documents.save(1, version.id, captured, pdf, payroll_run_id=first)
    assert "Draft payslip" in business.documents.get(1, document).title
    assert run.result["statutory"]["epf"]["mode"] == "MANUAL_ADJUSTMENT"


def test_schedule_uses_effective_month_and_exact_bracket_boundaries():
    decimal = Decimal
    schedule = ContributionSchedule("epf", "fictional test", "urn:test:schedule", date(2026, 11, 1),
                                    date(2026, 11, 30), {"fictional": (
                                        ContributionBand(decimal("1"), decimal("100"), decimal("3"), decimal("4")),
                                        ContributionBand(decimal("100.01"), decimal("200"), decimal("5"), decimal("6")),
                                    )}, {"ineligible": "Fictional test category"})
    period = {"period": "2026-11-01", "basic": "100.00"}
    for wage, expected in (("100.00", "3"), ("100.01", "5")):
        result = calculate(PayrollInput(**period), {"epf": ("fictional", decimal(wage))}, (schedule,))
        assert result.statutory["epf"].employee == decimal(expected)
    result = calculate(PayrollInput(**period), {"epf": ("ineligible", decimal("100.00"))}, (schedule,))
    assert result.statutory["epf"].mode == "NOT_APPLICABLE"
    result = calculate(PayrollInput(**dict(period, period="2026-12-01")), {}, (schedule,))
    assert result.statutory["epf"].employee is None


def test_portable_backup_checks_password_restores_database_pdf_and_assets(tmp_path, qapp, pdf):
    workspace = tmp_path / "active"
    workspace.mkdir()
    engine = create_database_engine(workspace / "document-manager.sqlite3")
    try:
        upgrade_database(engine)
        business = BusinessService(engine)
        template = business.save_record("template", 1, {"name": "With logo"})
        design = business.designs.open(1, template).document.model_dump(exclude_unset=True)
        source_image = tmp_path / "sample.png"
        image = QImage(31, 21, QImage.Format.Format_RGB32)
        image.fill(0xFF123456)
        assert image.save(str(source_image))
        asset = import_image(workspace, 1, source_image)
        design["document"]["content"].append({"type": "image", "attrs": {"assetId": asset.asset_id}})
        business.designs.save(1, template, 0, design, publish=True)
        version = business.designs.published(1, template)
        filled = business.fill.capture(1, checked_document(version.document_json), {}, {})
        document = business.documents.save(1, version.id, filled, pdf)
        service = BackupService(workspace)
        archive = tmp_path / "sample.919backup"
        password = "Fictional backup password"
        service.create(archive, password)
        service.verify(archive, password)
        assert b"Fictional sample" not in archive.read_bytes()
        with pytest.raises(BusinessError, match="password"):
            service.verify(archive, "Incorrect backup password")
        restored = tmp_path / "recovered"
        service.restore(archive, password, restored)
        with pytest.raises(BusinessError, match="new workspace"):
            service.restore(archive, password, restored)
        restored_db = create_database_engine(restored / "document-manager.sqlite3")
        try:
            assert BusinessService(restored_db).documents.get(1, document).pdf == pdf
            assert load_image(restored, 1, asset.asset_id) == asset
        finally:
            restored_db.dispose()
    finally:
        engine.dispose()
