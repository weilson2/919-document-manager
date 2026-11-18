from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from document_manager.services.settings import (
    CompanyProfile,
    SettingsService,
)
from document_manager.ui.company_logo import read_logo
from document_manager.ui.record_forms import RecordDialog, options
from document_manager.ui.widgets import (
    HANDLED_ERRORS,
    FormField,
    FormFields,
    error_text,
    plain_label,
    scrollable,
)

PROFILE_FIELDS = (
    FormField("name", "Company name"),
    FormField("registration_number", "Registration number"),
    FormField("address", "Business address", "notes"),
    FormField("contact_name", "Contact person", optional=True),
    FormField("phone", "Phone", optional=True),
    FormField("email", "Email", optional=True),
)
DOCUMENT_FIELDS = (
    options("page_size", "Page size", {"A4": "A4", "A5": "A5"}, default="A4"),
    options("orientation", "Orientation", {"portrait": "Portrait", "landscape": "Landscape"}, default="portrait"),
    FormField("margin_top", "Top margin", "margin", default=20),
    FormField("margin_right", "Right margin", "margin", default=20),
    FormField("margin_bottom", "Bottom margin", "margin", default=20),
    FormField("margin_left", "Left margin", "margin", default=20),
)


class CompanySettings(QWidget):
    company_saved = Signal()
    default_changed = Signal()
    company_created = Signal(int)

    def __init__(self, settings: SettingsService):
        super().__init__()
        self._settings = settings
        self.company_id = None
        self.logo = None
        self._original = None

        toolbar = QHBoxLayout()
        new_button = QPushButton("New company")
        new_button.clicked.connect(self._create)
        self.default_button = QPushButton("Make default")
        self.default_button.clicked.connect(self._make_default)
        self.default_label = plain_label()
        toolbar.addWidget(new_button)
        toolbar.addWidget(self.default_button)
        toolbar.addWidget(self.default_label)
        toolbar.addStretch()

        identity = QGroupBox("Company profile")
        identity_form = QFormLayout(identity)
        self.profile_fields = FormFields(identity_form, PROFILE_FIELDS)
        self.name = self.profile_fields.widgets["name"]
        self.registration_number = self.profile_fields.widgets["registration_number"]
        self.address = self.profile_fields.widgets["address"]
        self.address.setFixedHeight(105)
        logo_row = QWidget()
        logo_layout = QHBoxLayout(logo_row)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        self.preview = plain_label("No logo")
        self.preview.setAccessibleName("Company logo")
        logo_layout.addWidget(self.preview)
        choose_logo = QPushButton("Choose logo")
        choose_logo.clicked.connect(self._choose_logo)
        logo_layout.addWidget(choose_logo)
        self.remove_logo = QPushButton("Remove logo")
        self.remove_logo.clicked.connect(self._remove_logo)
        logo_layout.addWidget(self.remove_logo)
        logo_layout.addStretch()
        identity_form.addRow("Logo", logo_row)

        print_settings = QGroupBox("Document defaults")
        self.document_fields = FormFields(QFormLayout(print_settings), DOCUMENT_FIELDS)

        self.status = plain_label()
        self.save_button = QPushButton("&Save changes")
        self.save_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.save_button.clicked.connect(self._save)
        footer = QHBoxLayout()
        footer.addWidget(self.save_button)
        footer.addWidget(self.status, 1)

        panel = QWidget()
        sections = QVBoxLayout(panel)
        sections.setContentsMargins(0, 0, 8, 0)
        sections.setSpacing(12)
        sections.addWidget(identity)
        sections.addWidget(print_settings)
        sections.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(toolbar)
        layout.addWidget(scrollable(panel), 1)
        layout.addLayout(footer)

    def set_company(self, company_id: int, profile: CompanyProfile, default_id: int) -> None:
        self.company_id = company_id
        self._load(profile)
        self.show_default(default_id)
        self.status.clear()

    def show_default(self, default_id: int) -> None:
        is_default = self.company_id == default_id
        self.default_button.setEnabled(not is_default)
        self.default_label.setText("Default company" if is_default else "")

    def _load(self, profile: CompanyProfile) -> None:
        self.profile_fields.load(profile.model_dump(exclude={"logo", "document_settings"}))
        self.document_fields.load(profile.document_settings.model_dump())
        self.logo = profile.logo
        self._show_logo()
        self._original = self._values()

    def _values(self) -> dict:
        return {**self.profile_fields.values(), "logo": self.logo, "document_settings": self.document_fields.values()}

    def can_switch(self) -> bool:
        if self._original is None or self._original == self._values():
            return True
        answer = QMessageBox.question(
            self, "Unsaved company settings", "Discard unsaved changes to this company?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def _save(self) -> None:
        try:
            profile = CompanyProfile.model_validate(self._values())
            self._settings.save_company(profile, self.company_id)
        except HANDLED_ERRORS as error:
            self.profile_fields.show_error(self.status, error, "Save company settings")
            return

        self._load(profile)
        self.status.setText("Company settings saved.")
        self.company_saved.emit()

    def _make_default(self) -> None:
        try:
            self._settings.set_default_company(self.company_id)
        except HANDLED_ERRORS as error:
            self.status.setText(error_text(error, "Set default company"))
            return
        self.show_default(self.company_id)
        self.status.setText("This company will open when you start the application.")
        self.default_changed.emit()

    def _create(self) -> None:
        if not self.can_switch():
            return
        created = None

        def save(values):
            nonlocal created
            created = self._settings.create_company(CompanyProfile.model_validate(values))

        dialog = RecordDialog(self, "New company", PROFILE_FIELDS, {}, save)
        result = dialog.exec()
        dialog.deleteLater()
        if result == QDialog.DialogCode.Accepted:
            self.company_created.emit(created)

    def _choose_logo(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(self, "Choose company logo", "", "Images (*.png *.jpg *.jpeg)")
        if not filename:
            return
        try:
            self.logo = read_logo(Path(filename))
        except ValueError as error:
            self.status.setText(str(error))
            return
        except OSError:
            self.status.setText("The selected file could not be opened.")
            return
        self._show_logo()
        self.status.setText("Save changes to keep this logo.")

    def _remove_logo(self) -> None:
        self.logo = None
        self._show_logo()
        self.status.setText("Save changes to remove the logo.")

    def _show_logo(self) -> None:
        pixmap = QPixmap()
        if self.logo and pixmap.loadFromData(self.logo, "PNG"):
            self.preview.setPixmap(pixmap.scaled(
                100, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            self.preview.setText("No logo")
        self.remove_logo.setEnabled(self.logo is not None)
