import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from document_manager.services.errors import BusinessError

logger = logging.getLogger(__name__)
HANDLED_ERRORS = (BusinessError, SQLAlchemyError, ValidationError)


def plain_label(text: str = "", *, object_name: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def scrollable(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("contentScroll")
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidgetResizable(True)
    widget.setObjectName("scrollContents")
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    scroll.setWidget(widget)
    return scroll


@dataclass(frozen=True)
class FormField:
    key: str
    label: str
    kind: str = "text"
    options: tuple = ()
    optional: bool = False
    default: object = None


class FormFields:
    def __init__(self, form: QFormLayout, fields: tuple[FormField, ...]):
        self.fields = {field.key: field for field in fields}
        self.widgets = {}
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setVerticalSpacing(10)
        for field in fields:
            widget = self._make_widget(field)
            widget.setObjectName(field.key)
            self.widgets[field.key] = widget
            form.addRow(field.label, widget)
        self.load({})

    @staticmethod
    def _make_widget(field: FormField):
        if field.kind == "select":
            widget = QComboBox()
            if field.optional:
                widget.addItem("—", None)
            for value, label in field.options:
                widget.addItem(label, value)
        elif field.kind == "notes":
            widget = QPlainTextEdit()
            widget.setFixedHeight(86)
            widget.setTabChangesFocus(True)
        elif field.kind == "margin":
            widget = QSpinBox()
            widget.setRange(0, 60)
            widget.setSuffix(" mm")
        else:
            widget = QLineEdit()
            if field.kind == "date":
                widget.setPlaceholderText("YYYY-MM-DD")
            elif field.kind == "money":
                widget.setPlaceholderText("0.00")
        return widget

    def load(self, values: dict) -> None:
        for key, field in self.fields.items():
            value = values.get(key, field.default)
            widget = self.widgets[key]
            if isinstance(widget, QComboBox):
                index = widget.findData(value)
                widget.setCurrentIndex(max(0, index))
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(value or "")
            elif isinstance(widget, QSpinBox):
                widget.setValue(value)
            else:
                if isinstance(value, (date, Decimal)):
                    value = str(value)
                widget.setText(value or "")

    def values(self) -> dict:
        result = {}
        for key, field in self.fields.items():
            widget = self.widgets[key]
            if isinstance(widget, QComboBox):
                value = widget.currentData()
            elif isinstance(widget, QPlainTextEdit):
                value = widget.toPlainText()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            else:
                value = widget.text()
            result[key] = None if field.optional and isinstance(value, str) and not value.strip() else value
        return result

    def show_error(self, status: QLabel, error: Exception, action: str) -> None:
        if isinstance(error, ValidationError):
            detail = error.errors(include_input=False)[0]
            key = detail["loc"][-1] if detail["loc"] else None
            if key in self.fields:
                self.widgets[key].setFocus()
                status.setText(f"{self.fields[key].label} — {detail['msg']}")
                return
        status.setText(error_text(error, action))


def error_text(error: Exception, action: str) -> str:
    if isinstance(error, BusinessError):
        return str(error)
    if isinstance(error, ValidationError):
        return error.errors(include_input=False)[0]["msg"]
    # Avoid logging SQL parameters or customer-provided values.
    logger.error("%s failed (%s)", action, type(error).__name__)
    return f"{action} failed. Try again or check the application log."
