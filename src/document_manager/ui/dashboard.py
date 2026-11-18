from datetime import UTC

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from document_manager.services.business import BusinessService
from document_manager.ui.widgets import HANDLED_ERRORS, error_text, plain_label

METRICS = (
    ("templates", "Total templates"),
    ("documents", "Generated documents"),
    ("active_employees", "Active employees"),
    ("active_tenants", "Active tenants"),
)


class Dashboard(QWidget):
    def __init__(self, business: BusinessService, configure_company, start_new):
        super().__init__()
        self._business = business
        self.company_name = plain_label(object_name="companyName")
        self.settings_button = QPushButton("Open company settings")
        self.settings_button.clicked.connect(configure_company)
        actions = QHBoxLayout()
        actions.addWidget(self.settings_button)
        for kind in ("tenant", "employee", "template"):
            button = QPushButton(f"New {kind}")
            button.clicked.connect(lambda _checked=False, selected=kind: start_new(selected))
            actions.addWidget(button)
        actions.addStretch()

        metrics = QGridLayout()
        self.values = {}
        for index, (key, label) in enumerate(METRICS):
            card = QWidget()
            card.setObjectName("card")
            details = QVBoxLayout(card)
            details.setContentsMargins(16, 12, 16, 12)
            details.addWidget(plain_label(label))
            value = plain_label("—", object_name=f"metric_{key}")
            value.setProperty("metric", True)
            details.addWidget(value)
            if key == "documents":
                details.addWidget(plain_label("Available with document generation"))
            details.addStretch()
            self.values[key] = value
            metrics.addWidget(card, index // 2, index % 2)

        card = QWidget()
        card.setObjectName("card")
        activity = QVBoxLayout(card)
        activity.setContentsMargins(16, 12, 16, 12)
        activity.addWidget(plain_label("Recent activity", object_name="sectionTitle"))
        self.activity = plain_label()
        activity.addWidget(self.activity)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.company_name)
        layout.addLayout(actions)
        layout.addLayout(metrics)
        layout.addWidget(card)
        layout.addStretch()

    def refresh(self, company_id: int) -> None:
        try:
            summary = self._business.dashboard(company_id)
        except HANDLED_ERRORS as error:
            for label in self.values.values():
                label.setText("—")
            self.activity.setText(error_text(error, "Load dashboard"))
            return

        for key, label in self.values.items():
            count = getattr(summary, key)
            label.setText("—" if count is None else str(count))
        self.activity.setText(
            "\n".join(
                f"{entry.created_at.replace(tzinfo=UTC).astimezone():%d %b %Y %H:%M}"
                f"   {entry.action.capitalize()} {entry.subject_type} · {entry.subject_label}"
                for entry in summary.activity
            ) or "No activity yet. Changes to this company's records will appear here."
        )
