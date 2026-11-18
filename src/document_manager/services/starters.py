import json
from importlib.resources import files

from sqlalchemy import select

from document_manager.editor.visual_schema import PageSettings
from document_manager.persistence.database import write_session
from document_manager.persistence.models import (
    BusinessActivity,
    Company,
    Template,
    TemplateCategory,
    TemplateDraft,
)
from document_manager.persistence.repositories import (
    ActivityRepository,
    RecordRepository,
    TemplateRepository,
)
from document_manager.services.designs import DesignService, checked_document

INSTALL_ACTION = "installed starter designs"


def install_starters(engine, company_id: int) -> None:
    with write_session(engine) as session:
        if session.scalar(select(BusinessActivity.id).where(
            BusinessActivity.company_id == company_id, BusinessActivity.action == INSTALL_ACTION,
        ).limit(1)) is not None:
            return
        company = session.get_one(Company, company_id)
        page_settings = PageSettings.model_validate(company.document_settings).model_dump()
        starter_file = files("document_manager").joinpath("presets", "starter_designs.json")
        presets = json.loads(starter_file.read_text(encoding="utf-8"))
        records = RecordRepository(session, company_id, Template)
        templates = TemplateRepository(session, company_id)
        categories = {category.name.casefold(): category for category in templates.categories()}
        for preset in presets:
            name = preset["name"]
            if templates.name_used(name):
                copy = 1
                while templates.name_used(name):
                    name = preset["name"] + (f" (Starter {copy})" if copy > 1 else " (Starter)")
                    copy += 1
            category_name = preset["category"]
            key = category_name.casefold()
            if key not in categories:
                category = TemplateCategory(company_id=company_id, name=category_name)
                session.add(category)
                session.flush()
                categories[key] = category
            template = records.add({
                "name": name, "description": preset["description"], "category_id": categories[key].id,
            })
            document = checked_document({
                "schema_version": 3, "document": preset["document"], "fields": preset["fields"],
                "page_settings": page_settings,
                **({"print_settings": {"company_logo": True}} if preset["name"] != "Blank Document" else {}),
            }).model_dump(exclude_unset=True)
            session.add(TemplateDraft(company_id=company_id, template_id=template.id,
                                      revision=1, document_json=document))
            DesignService.publish_version(session, template, document, purpose=preset.get("purpose"), starter_name=preset["name"])
        ActivityRepository(session, company_id).record(INSTALL_ACTION, "company", company_id, company.name)
