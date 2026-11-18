from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from document_manager.editor.fields import FLAG_TYPES, REFERENCE_TYPES
from document_manager.editor.images import load_image
from document_manager.editor.print_layout import print_html
from document_manager.services.designs import checked_document
from document_manager.services.documents import DocumentSource
from document_manager.services.errors import BusinessError
from document_manager.ui.pdf_view import PdfJob, PdfPreview, export_pdf
from document_manager.ui.record_forms import record_dialog
from document_manager.ui.widgets import (
    HANDLED_ERRORS,
    ComboBox,
    error_text,
    plain_label,
)

NO_DATE = QDate(1, 1, 1)


class DateInput(QDateEdit):
    def __init__(self):
        super().__init__()
        self.setDisplayFormat("yyyy-MM-dd")
        self.setCalendarPopup(True)
        self.setMinimumDate(NO_DATE)
        self.setMaximumDate(QDate(9999, 12, 31))
        self.setSpecialValueText("No date")
        self.setDate(NO_DATE)

    def read(self):
        return self.date().toString(Qt.DateFormat.ISODate) if self.date() != NO_DATE else None

    def write(self, value):
        self.setDate(QDate.fromString(value, Qt.DateFormat.ISODate) if value else NO_DATE)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.setDate(NO_DATE)
        else:
            super().keyPressEvent(event)


def line_widget(multiline=False):
    if multiline:
        control = QPlainTextEdit()
        control.setMaximumHeight(82)
        return control, control.toPlainText, lambda value: control.setPlainText(value or "")
    control = QLineEdit()
    control.setMaxLength(4000)
    return control, control.text, lambda value: control.setText(value or "")


def field_widget(field, choices):
    kind = field.type
    if kind == "date":
        control = DateInput()
        return control, control.read, control.write
    if kind == "date_range":
        control = QWidget()
        start, end = DateInput(), DateInput()
        start.setAccessibleName("Start date")
        end.setAccessibleName("End date")
        layout = QHBoxLayout(control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(start, 1)
        layout.addWidget(end, 1)

        def read():
            a, b = start.read(), end.read()
            return {"start": a, "end": b} if a or b else None

        def write(value):
            value = value or {}
            start.write(value.get("start"))
            end.write(value.get("end"))

        return control, read, write
    if kind in FLAG_TYPES | REFERENCE_TYPES | {"dropdown"}:
        control = ComboBox()
        control.addItem("Choose a value", None)
        if kind in FLAG_TYPES:
            control.addItem("Checked" if kind == "checkbox" else "Yes", True)
            control.addItem("Unchecked" if kind == "checkbox" else "No", False)
        elif kind == "dropdown":
            for option in field.validation.options:
                control.addItem(option, option)
        else:
            for pk, name in choices(kind.removesuffix("_reference")):
                control.addItem(name, str(pk))
        return control, control.currentData, lambda value: control.setCurrentIndex(max(0, control.findData(value)))
    return line_widget(kind in {"multiline", "address"})


class FillDialog(QDialog):
    saved = Signal(int)
    design_requested = Signal(int)

    def __init__(
        self, business, data_dir, company_id, version, parent, *,
        source=None, payroll_run=None, allow_edit_design=False, inherited_changes=False,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Fill document · {version.metadata_snapshot['name']}")
        self.resize(730, 680)
        self._business = business
        self._company_id = company_id
        self._data_dir = data_dir
        self._version = version
        self._payroll_run = payroll_run
        self._design = checked_document(version.document_json)
        self._fields = {}
        self._subjects = {}
        self._status = plain_label()
        self._printing = False
        self._source_subjects = source.subjects if source else {}
        self._allow_edit_design = payroll_run is None and (source is None or allow_edit_design)

        layout = QVBoxLayout(self)
        layout.addWidget(plain_label(f"{version.metadata_snapshot['name']} · Published version {version.version_number}",
                                     object_name="sectionTitle"))
        form_contents = QWidget()
        form = QFormLayout(form_contents)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for kind in ("tenant", "employee"):
            if kind not in self._source_subjects and not any(
                (field.binding or "").startswith(kind + ".") or field.type == kind + "_reference"
                for field in self._design.fields
            ):
                continue
            holder = QWidget()
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            chooser = ComboBox()
            self._subjects[kind] = chooser
            self._load_choices(kind, self._source_subjects.get(kind))
            chooser.currentIndexChanged.connect(lambda _index, selected=kind: self._prefill(selected))
            row.addWidget(chooser, 1)
            if payroll_run is None:
                add = QPushButton(f"New {kind}")
                add.clicked.connect(lambda _checked=False, selected=kind: self._new_subject(selected))
                row.addWidget(add)
            else:
                chooser.setEnabled(False)
            form.addRow(f"Prefill from {kind}", holder)

        choices = lambda kind: business.fill.choices(company_id, kind)
        defaults = dict(source.values) if source else business.fill.suggested(company_id, self._design, {})
        payroll_values = business.payroll.payslip_values(payroll_run) if payroll_run is not None else {}
        for field in self._design.fields:
            control, read, write = field_widget(field, choices)
            self._fields[field.id] = (control, read, write)
            caption = field.label + (" *" if field.required else "")
            control.setAccessibleName(caption)
            if field.description:
                control.setToolTip(field.description)
            form.addRow(plain_label(caption), control)
            if field.description:
                form.addRow("", plain_label(field.description))
            if isinstance(control, ComboBox) and field.type in REFERENCE_TYPES:
                self._ensure_reference(control, defaults.get(field.id))
            write(defaults.get(field.id))
            if field.key in payroll_values:
                control.setEnabled(False)
        if not self._fields:
            form.addRow(plain_label("This design has no fillable fields. Preview the published content to continue."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_contents)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._status)
        actions = QHBoxLayout()
        actions.addStretch()
        self._preview = QPushButton("Preview PDF")
        self._preview.clicked.connect(self._render)
        cancel = QPushButton("Close")
        cancel.clicked.connect(self.reject)
        if self._allow_edit_design:
            self._design_button = QPushButton("Edit design")
            self._design_button.clicked.connect(lambda: self.design_requested.emit(self._version.template_id))
            actions.addWidget(self._design_button)
        else:
            self._design_button = None
        actions.addWidget(cancel)
        actions.addWidget(self._preview)
        layout.addLayout(actions)
        self._baseline = self._current() if not inherited_changes else None

    @staticmethod
    def _ensure_reference(control, value):
        if value is not None and control.findData(value) == -1:
            control.addItem("Previously selected record", value)

    def _load_choices(self, kind, selected=None):
        chooser = self._subjects[kind]
        blocked = chooser.blockSignals(True)
        chooser.clear()
        chooser.addItem(f"Choose a {kind}", None)
        for pk, name in self._business.fill.choices(self._company_id, kind):
            chooser.addItem(name, pk)
        self._ensure_reference(chooser, selected)
        chooser.setCurrentIndex(max(0, chooser.findData(selected)))
        chooser.blockSignals(blocked)

    def _new_subject(self, kind):
        def save(payload):
            self._new_id = self._business.save_record(kind, self._company_id, payload)

        dialog = record_dialog(self, kind, {}, None, save)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_choices(kind, self._new_id)
            self._prefill(kind)
        dialog.deleteLater()

    def _selected(self):
        return {kind: widget.currentData() for kind, widget in self._subjects.items() if widget.currentData() is not None}

    def _prefill(self, kind):
        try:
            selected = self._selected()
            defaults = self._business.fill.suggested(
                self._company_id, self._design, {kind: selected[kind]} if kind in selected else {},
            )
            for field in self._design.fields:
                if (field.binding or "").startswith(kind + ".") or field.type == kind + "_reference":
                    control, _read, write = self._fields[field.id]
                    if field.type in REFERENCE_TYPES:
                        self._ensure_reference(control, defaults[field.id])
                    write(defaults[field.id])
            self._status.setText("Prefilled fields can be edited for this document.")
        except HANDLED_ERRORS as error:
            self._status.setText(error_text(error, "Prefill document"))

    def _current(self):
        return ({key: read() for key, (_control, read, _write) in self._fields.items()}, self._selected())

    def pending_values(self):
        values, subjects = self._current()
        return DocumentSource(self._version, values, subjects)

    def can_discard(self):
        if self._baseline == self._current():
            return True
        answer = QMessageBox.question(
            self, "Discard form entries?", "There are unsaved form entries. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def _render(self):
        def asset(asset_id):
            if self._data_dir is None:
                raise BusinessError("The app-managed images are unavailable in this workspace.")
            return load_image(self._data_dir, self._company_id, asset_id).content

        try:
            values, subjects = self._current()
            filled = self._business.fill.capture(
                self._company_id, self._design, values, subjects,
            )
            logo = self._business.fill.company_logo(self._company_id) if self._design.print_settings.company_logo else None
            html = print_html(self._design, filled.text_by_id, asset, inputs=filled.inputs, logo=logo,
                              draft=self._payroll_run is not None and self._payroll_run.status == "draft")
        except (*HANDLED_ERRORS, OSError) as error:
            self._status.setText(error_text(error, "Prepare PDF"))
            return

        self._printing = True
        self._preview.setEnabled(False)
        if self._design_button is not None:
            self._design_button.setEnabled(False)
        self._status.setText("Preparing the print preview…")
        PdfJob(html, self._design.page_settings, lambda pdf: self._preview_ready(pdf, filled, (values, subjects)), self)

    def reject(self):
        if not self._printing and self.can_discard():
            super().reject()

    def _preview_ready(self, pdf, filled, captured):
        self._printing = False
        self._preview.setEnabled(True)
        if self._design_button is not None:
            self._design_button.setEnabled(True)
        if pdf is None:
            self._status.setText("The PDF could not be generated. Check the page settings and try again.")
            return
        self._status.clear()
        dialog = PdfPreview(pdf, self)
        actions = QHBoxLayout()
        message = plain_label()
        save = QPushButton("Save to history")
        export = QPushButton("Export PDF")
        export.setEnabled(False)
        close = QPushButton("Back to form")
        close.clicked.connect(dialog.accept)
        document_id = None

        def save_snapshot():
            nonlocal document_id
            try:
                document_id = self._business.documents.save(
                    self._company_id, self._version.id, filled, pdf,
                    payroll_run_id=self._payroll_run.id if self._payroll_run is not None else None,
                )
            except HANDLED_ERRORS as error:
                message.setText(error_text(error, "Save document"))
                return
            save.setEnabled(False)
            export.setEnabled(True)
            message.setText("Saved to history.")
            self._baseline = captured
            self.saved.emit(document_id)

        def export_snapshot():
            try:
                export_document(self._business.documents, self._company_id, document_id, dialog)
            except (*HANDLED_ERRORS, OSError) as error:
                message.setText(error_text(error, "Export PDF"))

        save.clicked.connect(save_snapshot)
        export.clicked.connect(export_snapshot)
        actions.addWidget(message, 1)
        for button in (save, export, close):
            actions.addWidget(button)
        dialog.content.addLayout(actions)
        dialog.exec()
        dialog.deleteLater()


def export_document(documents, company_id, document_id, parent):
    document = documents.get(company_id, document_id)
    picker = QFileDialog(parent, "Export PDF")
    picker.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    picker.setNameFilter("PDF (*.pdf)")
    picker.setDefaultSuffix("pdf")
    picker.selectFile(document.number + ".pdf")
    filename = picker.selectedFiles()[0] if picker.exec() else None
    picker.deleteLater()
    if filename:
        path = Path(filename)
        export_pdf(path, document.pdf)
        documents.record_export(company_id, document_id, path.name, document.checksum)
