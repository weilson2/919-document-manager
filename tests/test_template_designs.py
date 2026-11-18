import json

import pytest
from sqlalchemy.exc import IntegrityError

from document_manager.editor.bridge import EditorSession
from document_manager.persistence.database import (
    create_database_engine,
    upgrade_database,
    write_session,
)
from document_manager.persistence.models import TemplateVersion
from document_manager.services.business import BusinessService
from document_manager.services.designs import DesignService, StaleDraft
from document_manager.services.errors import RecordUnavailable
from document_manager.services.settings import CompanyProfile, SettingsService


def test_published_design_and_draft_are_independent_across_restart(database_engine):
    business = BusinessService(database_engine)
    template = business.save_record("template", 1, {"name": "Rental Custom"})
    assert business.publish_template(1, template) == 1
    first = business.designs.open(1, template).document.model_dump(exclude_unset=True)
    first["document"]["content"][0]["content"] = [{"type": "text", "text": "First · 租约"}]
    assert business.designs.save(1, template, 0, first, publish=True) == (1, 2)
    second = business.designs.open(1, template).document.model_dump(exclude_unset=True)
    second["document"]["content"][0]["content"][0]["text"] = "Second"
    assert business.designs.save(1, template, 1, second) == (2, None)
    with pytest.raises(StaleDraft):
        business.designs.save(1, template, 1, first)

    reopened = create_database_engine(database_engine.url.database)
    try:
        upgrade_database(reopened)
        designs = DesignService(reopened)
        assert designs.open(1, template).document.model_dump(exclude_unset=True) == second
        published = designs.published(1, template)
        assert published.document_json == first
        with pytest.raises(IntegrityError), write_session(reopened) as session:
            session.get_one(TemplateVersion, published.id).document_json = second
    finally:
        reopened.dispose()
    assert business.list_template_versions(1, template)[-1].document_json is None


def test_design_duplicate_archive_and_company_scope(database_engine):
    business = BusinessService(database_engine)
    other = SettingsService(database_engine).create_company(CompanyProfile(
        name="Other", registration_number="OTHER", address="Other",
    ))
    template = business.save_record("template", 1, {"name": "Private Design"})
    design = business.designs.open(1, template)
    business.designs.save(1, template, 0, design.document)
    duplicate = business.duplicate_template(1, template)
    assert business.designs.open(1, duplicate).document == design.document
    with pytest.raises(RecordUnavailable):
        business.designs.open(other, template)
    with pytest.raises(RecordUnavailable):
        business.designs.save(other, template, 0, design.document, publish=True)
    business.set_archived("template", 1, template, archived=True)
    with pytest.raises(RecordUnavailable):
        business.designs.open(1, template)
    business.set_archived("template", 1, template, archived=False)
    assert business.designs.open(1, template).revision == 1


def test_bridge_may_only_save_selected_design_in_bound_session(database_engine):
    business = BusinessService(database_engine)
    template = business.save_record("template", 1, {"name": "Bridge Design"})
    design = business.designs.open(1, template)
    session = EditorSession(1, design=(0, design.document), save_design=lambda revision, document, publish:
        business.designs.save(1, template, revision, document, publish=publish))
    opened = session.handle('{"method":"open","protocol_version":1,"schema_version":3}')
    request = {
        "method": "publish_design", "protocol_version": 1, "company_id": 1, "session_id": opened.session_id,
        "revision": 0, "document": opened.document.model_dump(exclude_unset=True),
    }
    assert session.handle(json.dumps(dict(request, company_id=2))).error == "session_mismatch"
    assert session.handle(json.dumps(dict(request, template_id=999))).error == "invalid_request"
    assert session.handle(json.dumps(request)).published_version == 1
    assert session.handle(json.dumps(request)).error == "design_conflict"
