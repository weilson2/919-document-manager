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
    def __init__(self, business: BusinessService, configure_company, start_new, start_document=None):
        super().__init__()
        self._business = business
        self.company_name = plain_label(object_name="companyName")
        self.settings_button = QPushButton("Open company settings")
        self.settings_button.clicked.connect(configure_company)
        owner = business.identity is None or business.identity.role == "owner"
        self.settings_button.setVisible(owner)
        actions = QHBoxLayout()
        actions.addWidget(self.settings_button)
        for kind in ("tenant", "employee", "template"):
            if kind == "employee" and business.identity is not None and not business.identity.sensitive_access:
                continue
            button = QPushButton(f"New {kind}")
            button.clicked.connect(lambda _checked=False, selected=kind: start_new(selected))
            actions.addWidget(button)
        actions.addStretch()
        quick = QGridLayout()
        if start_document is not None:
            for index, (label, name) in enumerate((
                ("New Rental Agreement", "Stall Rental Agreement"), ("New Offer Letter", "Employee Offer Letter"),
                ("New Payslip", "Employee Payslip"), ("New Payment Voucher", "Payment Voucher"),
            )):
                if index in (1, 2) and business.identity is not None and not business.identity.sensitive_access:
                    continue
                button = QPushButton(label)
                button.clicked.connect(lambda _pressed=False, selected=name: start_document(selected))
                quick.addWidget(button, index // 2, index % 2)

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
        recent_card = QWidget()
        recent_card.setObjectName("card")
        recent = QVBoxLayout(recent_card)
        recent.setContentsMargins(16, 12, 16, 12)
        recent.addWidget(plain_label("Recent documents", object_name="sectionTitle"))
        self.recent = plain_label()
        recent.addWidget(self.recent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.company_name)
        layout.addLayout(actions)
        layout.addLayout(quick)
        layout.addLayout(metrics)
        layout.addWidget(recent_card)
        layout.addWidget(card)
        layout.addStretch()

    def refresh(self, company_id: int) -> None:
        try:
            summary = self._business.dashboard(company_id)
            recent = self._business.documents.list(company_id, limit=5)
        except HANDLED_ERRORS as error:
            for label in self.values.values():
                label.setText("—")
            self.activity.setText(error_text(error, "Load dashboard"))
            self.recent.clear()
            return

        for key, label in self.values.items():
            count = getattr(summary, key)
            label.setText("—" if count is None else str(count))
        self.recent.setText("\n".join(f"{row.number}   {row.title}" for row in recent) or "No documents saved yet.")
        self.activity.setText(
            "\n".join(
                f"{entry.created_at.replace(tzinfo=UTC).astimezone():%d %b %Y %H:%M}"
                f"   {entry.action.capitalize()} {entry.subject_type} · {entry.subject_label}"
                for entry in summary.activity
            ) or "No activity yet. Changes to this company's records will appear here."
        )
