from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from document_manager.payroll import EARNINGS, OTHER_DEDUCTIONS, STATUTORY_LABELS
from document_manager.services.errors import BusinessError
from document_manager.ui.widgets import (
    HANDLED_ERRORS,
    ComboBox,
    error_text,
    plain_label,
)

AMOUNT_LABELS = {
    "basic": "Basic pay for this period", "overtime": "Overtime", "allowances": "Allowances", "bonus": "Bonus",
    "commission": "Commission", "other_earnings": "Other earnings", "advance": "Salary advance",
    "other_deductions": "Other authorized deductions", "gross": "Gross pay", "deductions": "Known deductions",
    "net": "Estimated net pay", "employer_cost": "Estimated employer cost",
}


class PayrollPage(QWidget):
    payslip_requested = Signal(int)
    changed = Signal()

    def __init__(self, business):
        super().__init__()
        self._business = business
        self._company_id = None
        self._employees = {}
        self._revisions = ComboBox()
        self._selected_employee = ComboBox()
        self._period = QDateEdit(QDate.currentDate())
        self._period.setCalendarPopup(True)
        self._period.setDisplayFormat("MMMM yyyy")
        self._selected_employee.currentIndexChanged.connect(self._prefill)
        self._inputs = {key: self._amount() for key in EARNINGS + OTHER_DEDUCTIONS}
        self._status = plain_label()
        self._result = plain_label("Select an employee and calculate the draft.")
        self._adjustments = {}

        form_panel = QGroupBox("Payroll period and earnings")
        form = QFormLayout(form_panel)
        form.addRow("Employee", self._selected_employee)
        form.addRow("Month", self._period)
        for key, control in self._inputs.items():
            form.addRow(AMOUNT_LABELS[key] + " (MYR)", control)

        contributions = QGroupBox("Statutory contributions")
        contributions_layout = QVBoxLayout(contributions)
        contributions_layout.addWidget(plain_label(
            "Verified Malaysian rules are unavailable. Draft totals exclude unverified amounts. "
            "Enter a reason with any manual draft adjustment.",
        ))
        grid = QGridLayout()
        for column, caption in enumerate(("Contribution", "Employee MYR", "Employer MYR", "Reason for adjustment")):
            grid.addWidget(plain_label(caption), 0, column)
        for row, (code, caption) in enumerate(STATUTORY_LABELS.items(), 1):
            employee, employer, reason = self._amount(), self._amount(), QLineEdit()
            reason.setMaxLength(500)
            self._adjustments[code] = employee, employer, reason
            grid.addWidget(plain_label(caption), row, 0)
            grid.addWidget(employee, row, 1)
            grid.addWidget(employer, row, 2)
            grid.addWidget(reason, row, 3)
            if code == "pcb":
                employer.setEnabled(False)
        contributions_layout.addLayout(grid)

        actions = QHBoxLayout()
        for caption, slot in (
            ("Calculate draft", self._calculate), ("Save draft revision", self._save), ("Check approval", self._approve),
        ):
            button = QPushButton(caption)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch()

        versions = QHBoxLayout()
        versions.addWidget(self._revisions, 1)
        for caption, slot in (("Load as new revision", self._load_revision), ("Preview payslip", self._payslip)):
            button = QPushButton(caption)
            button.clicked.connect(slot)
            versions.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(form_panel)
        layout.addWidget(contributions)
        layout.addLayout(actions)
        layout.addWidget(self._result)
        layout.addWidget(plain_label("Saved payroll revisions", object_name="sectionTitle"))
        layout.addLayout(versions)
        layout.addWidget(self._status)
        layout.addStretch()

    @staticmethod
    def _amount():
        control = QLineEdit()
        control.setMaxLength(32)
        control.setPlaceholderText("0.00")
        return control

    def set_company(self, company_id):
        self._company_id = company_id
        self._employees = {}
        self._status.clear()
        self._selected_employee.clear()
        self._selected_employee.addItem("Select employee", None)
        for control in self._inputs.values():
            control.clear()
        for row in self._adjustments.values():
            for control in row:
                control.clear()
        self._result.setText("Select an employee and calculate the draft.")
        self.refresh()

    def refresh(self):
        try:
            selected = self._selected_employee.currentData()
            employees = self._business.list_records("employee", self._company_id)
            self._employees = {employee.id: employee for employee in employees}
            self._selected_employee.blockSignals(True)
            self._selected_employee.clear()
            self._selected_employee.addItem("Select employee", None)
            for employee in employees:
                self._selected_employee.addItem(f"{employee.name} · {employee.employee_number}", employee.id)
            self._selected_employee.setCurrentIndex(max(0, self._selected_employee.findData(selected)))
            self._selected_employee.blockSignals(False)
            self._load_saved()
        except HANDLED_ERRORS as error:
            self._status.setText(error_text(error, "Load payroll"))

    def _prefill(self):
        employee = self._employees.get(self._selected_employee.currentData())
        self._inputs["basic"].setText(str(employee.basic_salary) if employee and employee.salary_type == "monthly" else "")
        if employee and employee.salary_type != "monthly":
            self._status.setText("Enter basic pay for the entire period for daily and hourly employees.")

    def _payload(self):
        employee = self._selected_employee.currentData()
        if employee is None:
            raise BusinessError("Select an employee.")
        if not self._inputs["basic"].text().strip():
            raise BusinessError("Enter basic pay for this period.")
        month = self._period.date()
        payload = {key: control.text().strip() or "0.00" for key, control in self._inputs.items()}
        payload["period"] = QDate(month.year(), month.month(), 1).toString(Qt.DateFormat.ISODate)
        payload["adjustments"] = {}
        for code, (employee_amount, employer_amount, reason) in self._adjustments.items():
            if any(item.text().strip() for item in (employee_amount, employer_amount, reason)):
                payload["adjustments"][code] = {
                    "employee": employee_amount.text().strip() or "0.00", "employer": employer_amount.text().strip() or "0.00",
                    "reason": reason.text(),
                }
        return employee, payload

    def _calculate(self):
        try:
            employee, payload = self._payload()
            draft = self._business.payroll.calculate(self._company_id, employee, payload)
            totals = [f"{AMOUNT_LABELS[key]}  RM {draft.amounts[key]:,.2f}"
                      for key in ("gross", "deductions", "net", "employer_cost")]
            for code, row in draft.statutory.items():
                if row.employee is None:
                    totals.append(f"{STATUTORY_LABELS[code]}  Awaiting verified calculation")
                else:
                    totals.append(f"{STATUTORY_LABELS[code]}  Employee RM {row.employee:,.2f} · Employer RM {row.employer:,.2f}"
                                  f" · {row.mode.replace('_', ' ').title()}")
            self._result.setText("DRAFT\n" + "\n".join(totals))
            self._status.clear()
        except HANDLED_ERRORS as error:
            self._status.setText(error_text(error, "Calculate draft"))

    def _save(self):
        self._save_run(False)

    def _approve(self):
        self._save_run(True)

    def _save_run(self, approve):
        try:
            employee, payload = self._payload()
            run_id = self._business.payroll.save(self._company_id, employee, payload, approve=approve)
            self._load_saved(run_id)
            self._calculate()
            self._status.setText("Payroll approved." if approve else "Draft revision saved. Select Preview payslip to continue.")
            self.changed.emit()
        except HANDLED_ERRORS as error:
            self._status.setText(error_text(error, "Save payroll"))

    def _load_saved(self, selected=None):
        selected = selected or self._revisions.currentData()
        self._revisions.clear()
        self._revisions.addItem("Choose a saved revision", None)
        for run in self._business.payroll.list(self._company_id):
            self._revisions.addItem(
                f"{run.period:%Y-%m} · {run.employee_snapshot['name']} · {run.status.title()} {run.revision}", run.id,
            )
        self._revisions.setCurrentIndex(max(0, self._revisions.findData(selected)))

    def _load_revision(self):
        if (pk := self._revisions.currentData()) is not None:
            try:
                run = self._business.payroll.get(self._company_id, pk)
                index = self._selected_employee.findData(run.employee_id)
                if index == -1:
                    raise BusinessError("Restore this employee before creating a payroll revision.")
                self._selected_employee.setCurrentIndex(index)
                self._period.setDate(QDate(run.period.year, run.period.month, 1))
                for key, control in self._inputs.items():
                    control.setText(run.inputs[key])
                for code, fields in self._adjustments.items():
                    adjustment = run.inputs["adjustments"].get(code, {})
                    for name, control in zip(("employee", "employer", "reason"), fields, strict=True):
                        control.setText(adjustment.get(name, ""))
                self._calculate()
            except HANDLED_ERRORS as error:
                self._status.setText(error_text(error, "Load payroll revision"))

    def _payslip(self):
        if (pk := self._revisions.currentData()) is not None:
            self.payslip_requested.emit(pk)
        else:
            self._status.setText("Save or select a payroll revision to preview its payslip.")
