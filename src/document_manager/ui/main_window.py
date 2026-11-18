from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from document_manager.services.business import BusinessService
from document_manager.services.settings import CompanyProfile, SettingsService
from document_manager.ui.company_settings import CompanySettings
from document_manager.ui.dashboard import Dashboard
from document_manager.ui.editor_page import DocumentEditor
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
QListWidget {
    background: transparent; color: #e2e8f0; border: 0; outline: 0;
}
QListWidget::item { padding: 9px 12px; border-radius: 5px; }
QListWidget::item:hover { background: #243c58; }
QListWidget::item:selected { background: #28517b; color: white; }
QListWidget::item:focus { border: 1px solid #93c5fd; }
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
    def __init__(self, settings: SettingsService, business: BusinessService, company_id: int, profile: CompanyProfile):
        super().__init__()
        self.settings = settings
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
        self.navigation.setAccessibleName("Main navigation")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages = QStackedWidget()
        self.document_editor = DocumentEditor()
        self.dashboard = Dashboard(business, lambda: self.navigation.setCurrentRow(SETTINGS_INDEX), self._quick_create)
        self.company_name = self.dashboard.company_name
        self.company_settings = CompanySettings(settings)
        self.company_settings.company_saved.connect(self._company_saved)
        self.company_settings.default_changed.connect(self._default_changed)
        self.company_settings.company_created.connect(self._activate_company)
        self.record_pages = {kind: RecordsPage(business, kind) for kind in ("template", "tenant", "employee")}
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

        workspace = QWidget()
        workspace.setObjectName("workspace")
        layout = QHBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(workspace)

        for index, key in ((0, "Ctrl+1"), (SETTINGS_INDEX, "Ctrl+,")):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda row=index: self.navigation.setCurrentRow(row))

        self._load_company(company_id, profile)
        self._reload_companies()

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
            if self.company_settings.can_switch():
                self._activate_company(selected)
            else:
                self.company_selector.setCurrentIndex(self.company_selector.findData(self.company_id))

    def _activate_company(self, company_id: int) -> None:
        try:
            profile = self.settings.get_company(company_id)
        except HANDLED_ERRORS as error:
            self.company_selector.setCurrentIndex(self.company_selector.findData(self.company_id))
            self.switch_status.setText(error_text(error, "Switch company"))
            return
        self._load_company(company_id, profile)
        self._reload_companies()

    def _load_company(self, company_id: int, profile: CompanyProfile) -> None:
        self.company_id = company_id
        self.document_editor.set_company(company_id)
        self.company_name.setText(profile.name)
        self.company_settings.set_company(company_id, profile, self.default_company_id)
        for page in self.record_pages.values():
            page.set_company(company_id)
        self._refresh_dashboard()

    def _company_saved(self) -> None:
        self.company_name.setText(self.company_settings.name.text())
        self._reload_companies()
        self._refresh_dashboard()

    def _default_changed(self) -> None:
        self.default_company_id = self.company_id
        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        self.dashboard.refresh(self.company_id)

    def closeEvent(self, event) -> None:
        if self.company_settings.can_switch():
            self.document_editor.close_session()
            super().closeEvent(event)
        else:
            event.ignore()

    def _quick_create(self, kind: str) -> None:
        self.navigation.setCurrentRow(NAVIGATION.index({"tenant": "Tenants", "employee": "Employees", "template": "Templates"}[kind]))
        page = self.record_pages[kind]
        page.archive_filter.setChecked(False)
        page.new_record()

    def _page_changed(self, index: int) -> None:
        if index == EDITOR_INDEX:
            self.document_editor.activate()

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
            layout.addWidget(self.document_editor, 1)
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
