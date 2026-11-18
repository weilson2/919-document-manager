from datetime import date

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

from document_manager.services.validation import (
    CITIZENSHIP_TYPES,
    EMPLOYMENT_TYPES,
    IDENTIFICATION_TYPES,
    RECORD_STATUSES,
    RENTAL_TYPES,
    SALARY_TYPES,
    TAX_RESIDENCIES,
)
from document_manager.ui.widgets import (
    HANDLED_ERRORS,
    FormField,
    FormFields,
    plain_label,
    scrollable,
)


def options(key, label, choices, *, optional=False, default=None):
    return FormField(key, label, "select", tuple(choices.items()), optional=optional, default=default)


PERSON_FIELDS = (
    FormField("name", "Name"),
    options("identification_type", "Identification type", IDENTIFICATION_TYPES, default="nric"),
    FormField("identification_number", "Identification number"),
    FormField("phone", "Phone", optional=True),
)
STATUS_FIELD = options("status", "Status", RECORD_STATUSES, default="active")
ADDRESS_FIELD = FormField("address", "Address", "notes", optional=True)
START_FIELD = FormField("start_date", "Start date", "date")


def fields_for(kind, categories):
    if kind == "tenant":
        return (
            *PERSON_FIELDS, ADDRESS_FIELD, FormField("stall_number", "Stall number"),
            options("rental_type", "Rental type", RENTAL_TYPES, default="monthly"),
            FormField("rental_amount", "Rent (MYR)", "money"),
            FormField("deposit", "Deposit (MYR)", "money", default="0.00"),
            START_FIELD, FormField("end_date", "End date", "date", optional=True), STATUS_FIELD,
        )
    if kind == "employee":
        return (
            FormField("employee_number", "Employee number"), *PERSON_FIELDS,
            FormField("email", "Email", optional=True), ADDRESS_FIELD, FormField("position", "Position"),
            options("salary_type", "Salary type", SALARY_TYPES, default="monthly"),
            FormField("basic_salary", "Basic salary (MYR)", "money"), START_FIELD, STATUS_FIELD,
            FormField("birth_date", "Date of birth", "date", optional=True),
            options("citizenship", "Citizenship", CITIZENSHIP_TYPES, optional=True),
            options("tax_residency", "Tax residency", TAX_RESIDENCIES, optional=True),
            options("employment_type", "Employment type", EMPLOYMENT_TYPES, optional=True),
        )
    return (
        FormField("name", "Template name"), FormField("description", "Description", "notes", optional=True),
        options("category_id", "Category", categories, optional=True),
    )


class RecordDialog(QDialog):
    def __init__(self, parent, title, fields, initial, save):
        super().__init__(parent)
        self._save = save
        self.setWindowTitle(title)
        panel = QWidget()
        form = QFormLayout(panel)
        self.fields = FormFields(form, fields)
        self.fields.load(initial)
        self.status = plain_label()
        self.status.setObjectName("formStatus")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(scrollable(panel), 1)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.resize(530, min(620, max(200, panel.sizeHint().height() + 90)))

    def save(self) -> None:
        try:
            self._save(self.fields.values())
        except HANDLED_ERRORS as error:
            self.fields.show_error(self.status, error, "Save")
            return
        self.accept()


def record_dialog(parent, kind, categories, record, save):
    fields = fields_for(kind, categories)
    if record is not None:
        initial = {field.key: getattr(record, field.key) for field in fields}
    else:
        initial = {"start_date": date.today()} if kind != "template" else {}
    title = f"{'Edit' if record is not None else 'New'} {kind}"
    return RecordDialog(parent, title, fields, initial, save)
