import logging

from pydantic import ValidationError
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from document_manager.services.settings import CompanyProfile, SettingsService

logger = logging.getLogger(__name__)


class CompanySettings(QWidget):
    company_saved = Signal(str)

    def __init__(self, settings: SettingsService, profile: CompanyProfile):
        super().__init__()
        self._settings = settings
        self.name = QLineEdit(profile.name)
        self.registration_number = QLineEdit(profile.registration_number)
        self.address = QPlainTextEdit(profile.address)
        self.address.setMinimumHeight(112)
        self.address.setMaximumHeight(160)
        self.address.setTabChangesFocus(True)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.save_button = QPushButton("&Save changes")
        self.save_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.save_button.clicked.connect(self._save)

        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.addRow("Company &name", self.name)
        form.addRow("&Registration number", self.registration_number)
        form.addRow("Business &address", self.address)
        form.addRow("", self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addWidget(self.status)

        for field in (self.name, self.registration_number, self.address):
            field.textChanged.connect(self.status.clear)

    def _save(self) -> None:
        fields = {
            "name": ("Company name", self.name),
            "registration_number": ("Registration number", self.registration_number),
            "address": ("Business address", self.address),
        }
        try:
            profile = CompanyProfile(
                name=self.name.text(),
                registration_number=self.registration_number.text(),
                address=self.address.toPlainText(),
            )
        except ValidationError as error:
            first_error = error.errors()[0]
            label, field = fields[first_error["loc"][0]]
            self.status.setText(f"{label}: {first_error['msg']}.")
            field.setFocus()
            return

        try:
            self._settings.save_company(profile)
        except IntegrityError:
            self.status.setText("This registration number is already used by another company.")
            self.registration_number.setFocus()
            return
        except (SQLAlchemyError, RuntimeError):
            logger.exception("Could not save the active company profile")
            self.status.setText("Company settings could not be saved. Try again or check the application log.")
            return

        self.name.setText(profile.name)
        self.registration_number.setText(profile.registration_number)
        self.address.setPlainText(profile.address)
        self.status.setText("Company settings saved.")
        self.company_saved.emit(profile.name)
