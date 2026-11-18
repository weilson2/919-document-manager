from PySide6.QtCore import QEventLoop, QObject

from document_manager.editor.print_layout import print_html
from document_manager.services.designs import checked_document
from document_manager.services.errors import BusinessError
from document_manager.services.settings import CompanyProfile
from document_manager.ui.pdf_view import PdfJob


def create_acceptance_workspace(settings, business, company_id):
    settings.save_company(CompanyProfile(
        name="DEMO · Fictional Cempaka Food Hall", registration_number="DEMO-NOT-A-REGISTRATION",
        address="10 Illustrative Lane\nMuar, Johor\nFictional address for software testing",
    ), company_id)
    business.install_starters(company_id)
    people = {
        "tenant": (
            {"name": "Fictional Tenant A · 陈小样", "identification_number": "DEMO-TENANT-1",
             "stall_number": "DEMO-A1", "rental_type": "monthly", "rental_amount": "1200.50", "deposit": "2401.00"},
            {"name": "Fictional Tenant B", "identification_number": "DEMO-TENANT-2",
             "stall_number": "DEMO-B2", "rental_type": "daily", "rental_amount": "60.00", "deposit": "120.00"},
        ),
        "employee": (
            {"name": "Fictional Employee A", "identification_number": "DEMO-EMPLOYEE-1", "employee_number": "DEMO-E1",
             "position": "Service assistant", "salary_type": "monthly", "basic_salary": "2100.00"},
            {"name": "Fictional Employee B", "identification_number": "DEMO-EMPLOYEE-2", "employee_number": "DEMO-E2",
             "position": "Kitchen assistant", "salary_type": "monthly", "basic_salary": "2300.00"},
        ),
    }
    records = {
        kind: [
            business.save_record(kind, company_id, {
                **person, "identification_type": "other", "start_date": "2026-11-01",
                "address": "Demo premises\nMuar",
            }) for person in group
        ] for kind, group in people.items()
    }
    templates = {row.name: row.id for row in business.designs.published_list(company_id)}
    custom = business.duplicate_template(company_id, templates["Blank Document"])
    business.save_record("template", company_id, {
        "name": "Demo Custom · Site Visit", "description": "A fictional site visit note for Fill Mode testing.",
    }, custom)
    current = business.designs.open(company_id, custom)
    field_id = "1" * 32
    data = current.document.model_dump(exclude_unset=True)
    data["fields"] = [{"id": field_id, "key": "visitor", "label": "Visitor · 访客", "type": "text",
                       "required": True, "default": None, "validation": {}, "formatting": {}}]
    data["document"]["content"] = [{"type": "heading", "attrs": {"level": 1},
                                    "content": [{"type": "text", "text": "Demo Site Visit"}]},
                                   {"type": "paragraph", "content": [
                                       {"type": "text", "text": "Visitor: "},
                                       {"type": "field", "attrs": {"fieldId": field_id}},
                                   ]}]
    business.designs.save(company_id, custom, current.revision, data, publish=True)

    employee = records["employee"][0]
    payroll_id = business.payroll.save(company_id, employee, {
        "period": "2026-11-01", "basic": "2100.00", "overtime": "35.50", "allowances": "50.00", "advance": "10.00",
    })
    run = business.payroll.get(company_id, payroll_id)
    documents = [
        (templates["Stall Rental Agreement"], {"tenant": records["tenant"][0]},
         {"terms": "Fictional example for software acceptance only."}, None),
        (templates["Employee Offer Letter"], {"employee": employee},
         {"probation": "3 months", "hours": "As stated in the roster", "notice": "As agreed in writing"}, None),
        (templates["Employee Payslip"], {"employee": employee}, business.payroll.payslip_values(run), run.id),
    ]
    parent = QObject()
    for template, subjects, overrides, run_id in documents:
        version = business.designs.published(company_id, template)
        design = checked_document(version.document_json)
        values = business.fill.suggested(company_id, design, subjects)
        values.update({field.id: overrides[field.key] for field in design.fields if field.key in overrides})
        filled = business.fill.capture(company_id, design, values, subjects)

        def no_assets(_asset_id):
            raise BusinessError("The demo template contains an unexpected external asset.")

        html = print_html(design, filled.text_by_id, no_assets, inputs=filled.inputs, draft=run_id is not None)
        pdf = _render_demo_pdf(html, design.page_settings, parent)
        if not pdf:
            raise BusinessError("A fictional acceptance PDF could not be generated.")
        business.documents.save(company_id, version.id, filled, pdf, payroll_run_id=run_id)


def _render_demo_pdf(html, settings, parent):
    result = []
    loop = QEventLoop()

    def done(pdf):
        result.append(pdf)
        loop.quit()

    PdfJob(html, settings, done, parent)
    if not result:
        loop.exec()
    return result[0]
