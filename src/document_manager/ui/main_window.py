from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from document_manager.editor.visual_schema import PageSettings
from document_manager.services.business import BusinessService
from document_manager.services.designs import checked_document
from document_manager.services.documents import DocumentSource
from document_manager.services.errors import BusinessError
from document_manager.services.settings import CompanyProfile, SettingsService
from document_manager.ui.backup_page import BackupPage
from document_manager.ui.company_settings import CompanySettings
from document_manager.ui.dashboard import Dashboard
from document_manager.ui.document_history import DocumentHistory
from document_manager.ui.editor_page import DocumentEditor
from document_manager.ui.fill_document import FillDialog
from document_manager.ui.local_login import LocalLogin
from document_manager.ui.payroll_page import PayrollPage
from document_manager.ui.records import RecordsPage
from document_manager.ui.widgets import (
    HANDLED_ERRORS,
    ComboBox,
    error_text,
    plain_label,
    scrollable,
)

NAVIGATION = (
    "Dashboard",
    "Templates",
    "Document Editor",
    "Documents",
    "History",
    "Tenants",
    "Employees",
    "Payroll",
    "Company Settings",
    "Backup & Restore",
)
SETTINGS_INDEX = NAVIGATION.index("Company Settings")
EDITOR_INDEX = NAVIGATION.index("Document Editor")

SHELL_STYLE = """
QWidget#workspace { background: #f1f5f9; color: #152740; }
QScrollArea#contentScroll, QWidget#scrollContents { background: #f1f5f9; }
QWidget#sidebar { background: #12223a; }
QLabel#brand { color: white; font-size: 16px; font-weight: 700; }
QLabel#sidebarLabel { color: #e2e8f0; }
QWidget#sidebar QListWidget {
    background: transparent; color: #e2e8f0; border: 0; outline: 0;
}
QWidget#sidebar QListWidget::item { padding: 9px 12px; border-radius: 5px; }
QWidget#sidebar QListWidget::item:hover { background: #243c58; }
QWidget#sidebar QListWidget::item:selected { background: #28517b; color: white; }
QWidget#sidebar QListWidget::item:focus { border: 1px solid #93c5fd; }
QListWidget#templateGallery { background: transparent; border: 0; outline: 0; }
QListWidget#templateGallery::item { background: white; border: 1px solid #ced9e7; border-radius: 8px; }
QListWidget#templateGallery::item:hover { background: #f6faff; border-color: #8eafd3; }
QListWidget#templateGallery::item:selected { background: #dcecff; border-color: #4480be; }
QListWidget#templateGallery::item:focus { border-color: #245589; }
QWidget#card { background: white; border: 1px solid #d8e1ec; border-radius: 9px; }
QGroupBox {
    background: white; border: 1px solid #d8e1ec; border-radius: 9px;
    color: #152740; font-weight: 600; margin-top: 12px; padding: 9px 8px 5px 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 5px; }
QLabel#pageTitle { color: #152740; font-size: 25px; font-weight: 700; }
QLabel#companyName { color: #152740; font-size: 19px; font-weight: 600; }
QLabel#sectionTitle { font-weight: 700; }
QLabel[metric="true"] { color: #152740; font-size: 23px; font-weight: 700; }
QLabel { color: #33465d; }
QLineEdit, QPlainTextEdit, QSpinBox {
    background: white; color: #152740; border: 1px solid #9aacc1;
    border-radius: 5px; padding: 6px;
}
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #245da0; }
QComboBox {
    background: white; color: #152740; border: 1px solid #9aacc1;
    border-radius: 6px; padding: 6px 30px 6px 9px;
}
QComboBox:hover { background: #f8fbff; border-color: #6d89a9; }
QComboBox:focus, QComboBox:on { background: #f8fbff; border-color: #245da0; }
QComboBox:disabled { background: #e9eef5; color: #64748b; border-color: #cbd5e1; }
QComboBox::drop-down { subcontrol-origin: border; width: 30px; border: 0; }
QComboBox QAbstractItemView {
    background-color: white; color: #152740;
    selection-background-color: #28517b; selection-color: white;
    border: 1px solid #9aacc1; outline: 0;
}
QComboBox QAbstractItemView::item { padding: 6px 8px; }
QComboBox QAbstractItemView::item:selected { background-color: #28517b; color: white; }
QPushButton {
    background: #245589; color: white; font-weight: 600; border: 1px solid #245589;
    border-radius: 5px; padding: 7px 14px;
}
QPushButton:hover { background: #1b446f; }
QPushButton:focus { border: 1px solid white; }
QPushButton:disabled { background: #e1e8f0; color: #53667b; border-color: #d0dbe7; }
QTableWidget {
    background: white; alternate-background-color: #f4f7fb; color: #152740;
    gridline-color: #e1e8f0; border: 1px solid #d8e1ec;
    selection-background-color: #28517b; selection-color: white;
}
QHeaderView::section { background: #e6edf6; color: #152740; border: 0; padding: 7px; font-weight: 600; }
"""


class MainWindow(QMainWindow):
    def __init__(
        self, settings: SettingsService, business: BusinessService, company_id: int, profile: CompanyProfile,
        data_dir: Path | None = None, *, starter_designs: bool = False, auth=None,
    ):
        super().__init__()
        self.settings = settings
        self.business = business
        self._auth = auth
        self._owner = business.identity is None or business.identity.role == "owner"
        self._sensitive = business.identity is None or business.identity.sensitive_access
        self._data_dir = data_dir
        self._starter_designs = starter_designs
        self._paused_fill = None
        self.company_id = company_id
        self.default_company_id = company_id
        self.setWindowTitle("919 Document Manager")
        self.resize(1120, 735)
        self.setMinimumSize(840, 540)
        self.setStyleSheet(SHELL_STYLE)

        self.company_selector = ComboBox()
        self.company_selector.setAccessibleName("Active company")
        self.company_selector.setSizeAdjustPolicy(ComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.company_selector.currentIndexChanged.connect(self._switch_selected_company)
        self.switch_status = plain_label(object_name="sidebarLabel")
        self.navigation = QListWidget()
        self.navigation.addItems(NAVIGATION)
        for hidden, visible in (("Company Settings", self._owner), ("Backup & Restore", self._owner),
                                ("Employees", self._sensitive), ("Payroll", self._sensitive)):
            self.navigation.item(NAVIGATION.index(hidden)).setHidden(not visible)
        self.navigation.setAccessibleName("Main navigation")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages = QStackedWidget()
        self.document_editor = DocumentEditor(data_dir, business.designs)
        self._resume_button = QPushButton("Return to filled values")
        self._resume_button.hide()
        self._resume_button.clicked.connect(self._resume_fill)
        self.payroll = PayrollPage(business)
        self.payroll.payslip_requested.connect(self._open_payslip)
        self.payroll.changed.connect(self._refresh_dashboard)
        self.document_history = {
            title: DocumentHistory(business.documents) for title in ("Documents", "History")
        }
        for history in self.document_history.values():
            history.reuse_requested.connect(self._reuse_document)
            history.changed.connect(self._refresh_dashboard)
        self.dashboard = Dashboard(
            business, lambda: self.navigation.setCurrentRow(SETTINGS_INDEX), self._quick_create,
            self._quick_document if starter_designs else None,
        )
        self.company_name = self.dashboard.company_name
        self.company_settings = CompanySettings(settings)
        self.company_settings.company_saved.connect(self._company_saved)
        self.company_settings.default_changed.connect(self._default_changed)
        self.company_settings.company_created.connect(self._activate_company)
        self.record_pages = {kind: RecordsPage(business, kind) for kind in ("template", "tenant", "employee")}
        self.record_pages["template"].design_requested.connect(self._open_design)
        self.record_pages["template"].fill_requested.connect(self._open_fill)
        for page in self.record_pages.values():
            page.changed.connect(self._refresh_dashboard)

        for title in NAVIGATION:
            self.pages.addWidget(self._page(title))
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.pages.currentChanged.connect(self._page_changed)
        self.navigation.setCurrentRow(0)
        self.navigation.setFocus()

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 26, 14, 16)
        sidebar_layout.setSpacing(20)
        sidebar_layout.addWidget(plain_label("919 Document Manager", object_name="brand"))
        company_controls = QVBoxLayout()
        company_controls.setSpacing(6)
        company_controls.addWidget(plain_label("Active company", object_name="sidebarLabel"))
        company_controls.addWidget(self.company_selector)
        company_controls.addWidget(self.switch_status)
        sidebar_layout.addLayout(company_controls)
        sidebar_layout.addWidget(self.navigation, 1)
        if self._auth is not None:
            sidebar_layout.addWidget(plain_label(f"{business.identity.username} · {business.identity.role.title()}",
                                                  object_name="sidebarLabel"))
            if self._owner:
                accounts = QPushButton("Add local account")
                accounts.clicked.connect(self._add_account)
                sidebar_layout.addWidget(accounts)

        workspace = QWidget()
        workspace.setObjectName("workspace")
        layout = QHBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(workspace)

        for index, key in ((0, "Ctrl+1"), (SETTINGS_INDEX, "Ctrl+,")):
            if index == SETTINGS_INDEX and not self._owner:
                continue
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda row=index: self.navigation.setCurrentRow(row))

        self._load_company(company_id, profile)
        self._reload_companies()
        self.document_editor.prepare_view()

    def _reload_companies(self) -> None:
        try:
            profiles = self.settings.list_companies()
        except HANDLED_ERRORS as error:
            self.switch_status.setText(error_text(error, "Load companies"))
            return
        signals = self.company_selector.blockSignals(True)
        self.company_selector.clear()
        for company_id, name, registration in profiles:
            self.company_selector.addItem(name, company_id)
            index = self.company_selector.count() - 1
            self.company_selector.setItemData(index, f"{name} · {registration}", Qt.ItemDataRole.ToolTipRole)
        self.company_selector.setCurrentIndex(self.company_selector.findData(self.company_id))
        self.company_selector.blockSignals(signals)
        self.switch_status.clear()

    def _switch_selected_company(self) -> None:
        selected = self.company_selector.currentData()
        if selected is not None and selected != self.company_id:
            if self.company_settings.can_switch() and self.document_editor.can_leave_session() and self._close_paused_fill():
                self._activate_company(selected)
            else:
                self.company_selector.setCurrentIndex(self.company_selector.findData(self.company_id))

    def _activate_company(self, company_id: int) -> None:
        try:
            profile = self.settings.get_company(company_id)
            self._load_company(company_id, profile)
        except HANDLED_ERRORS as error:
            self.company_selector.setCurrentIndex(self.company_selector.findData(self.company_id))
            self.switch_status.setText(error_text(error, "Switch company"))
            return
        self._reload_companies()

    def _load_company(self, company_id: int, profile: CompanyProfile) -> None:
        if self._starter_designs:
            self.business.install_starters(company_id)
        self.company_id = company_id
        self.document_editor.set_company(company_id, PageSettings.model_validate(profile.document_settings.model_dump()))
        self.company_name.setText(profile.name)
        self.company_settings.set_company(company_id, profile, self.default_company_id)
        for kind, page in self.record_pages.items():
            if kind == "employee" and not self._sensitive:
                continue
            page.set_company(company_id)
        if self._sensitive:
            self.payroll.set_company(company_id)
        for history in self.document_history.values():
            history.company_id = company_id
            history.refresh()
        self._refresh_dashboard()

    def _company_saved(self, profile: CompanyProfile) -> None:
        self.company_name.setText(self.company_settings.name.text())
        self.document_editor.set_company(self.company_id, PageSettings.model_validate(profile.document_settings.model_dump()))
        self._reload_companies()
        self._refresh_dashboard()

    def _default_changed(self) -> None:
        self.default_company_id = self.company_id
        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        self.dashboard.refresh(self.company_id)

    def closeEvent(self, event) -> None:
        if self.company_settings.can_switch() and self.document_editor.can_leave_session() and self._close_paused_fill():
            self.document_editor.close_session()
            super().closeEvent(event)
        else:
            event.ignore()

    def _quick_create(self, kind: str) -> None:
        self.navigation.setCurrentRow(NAVIGATION.index({"tenant": "Tenants", "employee": "Employees", "template": "Templates"}[kind]))
        page = self.record_pages[kind]
        page.archive_filter.setChecked(False)
        page.new_record()

    def _quick_document(self, name: str) -> None:
        if name == "Employee Payslip":
            self.navigation.setCurrentRow(NAVIGATION.index("Payroll"))
            return
        try:
            template = self.business.designs.starter_template(self.company_id, name)
            if template is None:
                raise BusinessError("Restore the corresponding starter design in Templates.")
            self._open_fill(template)
        except HANDLED_ERRORS as error:
            self._warn("Create document", error_text(error, "Open starter design"))

    def _page_changed(self, index: int) -> None:
        if index < 0:
            return
        if index == EDITOR_INDEX:
            self.document_editor.activate()
        if index == NAVIGATION.index("Templates"):
            self.record_pages["template"].refresh()
        if NAVIGATION[index] in self.document_history:
            self.document_history[NAVIGATION[index]].refresh()
        if NAVIGATION[index] == "Payroll" and self._sensitive:
            self.payroll.refresh()

    def _open_design(self, template_id: int) -> bool:
        if self.document_editor.open_template(template_id):
            self.navigation.setCurrentRow(EDITOR_INDEX)
            return True
        return False

    def _open_fill(self, template_id: int) -> None:
        try:
            version = self.business.designs.published(self.company_id, template_id)
            if version.metadata_snapshot.get("purpose") == "payroll":
                raise BusinessError("Select a saved revision in Payroll to generate its payslip.")
            self._fill_dialog(version)
        except HANDLED_ERRORS as error:
            self._warn("Create document", error_text(error, "Open Fill Mode"))

    def _reuse_document(self, document_id: int) -> None:
        try:
            source = self.business.documents.source(self.company_id, document_id)
            self._fill_dialog(source.version, source=source)
        except HANDLED_ERRORS as error:
            self._warn("Reuse document", error_text(error, "Open saved values"))

    def _open_payslip(self, run_id: int) -> None:
        try:
            run = self.business.payroll.get(self.company_id, run_id)
            version = self.business.designs.payroll_design(self.company_id)
            design = checked_document(version.document_json)
            values = self.business.fill.suggested(self.company_id, design, {})
            payroll = self.business.payroll.payslip_values(run)
            values.update({field.id: payroll[field.key] for field in design.fields if field.key in payroll})
            source = DocumentSource(version, values, {"employee": run.employee_id})
            self._fill_dialog(version, source=source, payroll_run=run)
        except HANDLED_ERRORS as error:
            self._warn("Preview payslip", error_text(error, "Open saved payroll revision"))

    def _warn(self, title, message):
        notice = QMessageBox(self)
        notice.setIcon(QMessageBox.Icon.Warning)
        notice.setWindowTitle(title)
        notice.setTextFormat(Qt.TextFormat.PlainText)
        notice.setText(message)
        notice.exec()

    def _add_account(self) -> None:
        dialog = LocalLogin(self._auth, self, creating_user=self.business.identity)
        dialog.exec()
        dialog.deleteLater()

    def _fill_dialog(self, version, **options) -> None:
        if not self._close_paused_fill():
            return
        dialog = FillDialog(self.business, self._data_dir, self.company_id, version, self, **options)
        dialog.saved.connect(lambda _id: self._document_saved())
        dialog.design_requested.connect(lambda template_id: self._pause_fill(dialog, template_id))
        dialog.finished.connect(dialog.deleteLater)
        dialog.open()

    def _pause_fill(self, dialog, template_id):
        if self._open_design(template_id):
            dialog.hide()
            self._paused_fill = dialog
            self._resume_button.show()

    def _resume_fill(self):
        dialog, self._paused_fill = self._paused_fill, None
        self._resume_button.hide()
        if dialog is not None:
            pending = dialog.pending_values()
            try:
                latest = self.business.designs.published(self.company_id, pending.version.template_id)
            except HANDLED_ERRORS:
                latest = pending.version
            if latest.version_number != pending.version.version_number and self._use_new_version(latest.version_number):
                try:
                    design = checked_document(latest.document_json)
                    defaults = self.business.fill.suggested(self.company_id, design, pending.subjects)
                    old = {field.id: field.type for field in checked_document(pending.version.document_json).fields}
                    defaults.update({field.id: pending.values[field.id] for field in design.fields
                                     if old.get(field.id) == field.type})
                    source = DocumentSource(latest, defaults, pending.subjects)
                    self._fill_dialog(latest, source=source, allow_edit_design=True, inherited_changes=True)
                except HANDLED_ERRORS as error:
                    self._warn("Update filled form", error_text(error, "Use newer version"))
                    dialog.open()
                else:
                    dialog.deleteLater()
            else:
                dialog.open()

    def _use_new_version(self, version_number):
        notice = QMessageBox(self)
        notice.setWindowTitle("Published design available")
        notice.setText(f"Use version {version_number} and keep entries for matching fields?")
        update = notice.addButton("Use newer version", QMessageBox.ButtonRole.AcceptRole)
        keep = notice.addButton("Keep current version", QMessageBox.ButtonRole.RejectRole)
        notice.setDefaultButton(keep)
        notice.exec()
        return notice.clickedButton() == update

    def _close_paused_fill(self):
        if self._paused_fill is None:
            return True
        if not self._paused_fill.can_discard():
            return False
        self._paused_fill.deleteLater()
        self._paused_fill = None
        self._resume_button.hide()
        return True

    def _document_saved(self):
        self._refresh_dashboard()
        for history in self.document_history.values():
            history.refresh()

    def _page(self, title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(16)
        layout.addWidget(plain_label(title, object_name="pageTitle"))

        if title == "Dashboard":
            layout.addWidget(scrollable(self.dashboard), 1)
            return page
        if title == "Company Settings":
            layout.addWidget(self.company_settings, 1)
            return page
        if title == "Document Editor":
            layout.addWidget(self._resume_button, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self.document_editor, 1)
            return page
        if title in self.document_history:
            layout.addWidget(self.document_history[title], 1)
            return page
        if title == "Payroll":
            layout.addWidget(scrollable(self.payroll), 1)
            return page
        if title == "Backup & Restore":
            layout.addWidget(BackupPage(self._data_dir), 1)
            return page
        for kind, name in (("template", "Templates"), ("tenant", "Tenants"), ("employee", "Employees")):
            if title == name:
                layout.addWidget(self.record_pages[kind], 1)
                return page

        card = QWidget()
        card.setObjectName("card")
        details = QVBoxLayout(card)
        details.setContentsMargins(20, 18, 20, 18)
        details.setSpacing(12)
        details.addWidget(plain_label("This section will be available in a later milestone."))
        layout.addWidget(card)
        layout.addStretch()
        return page
