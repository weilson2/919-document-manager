from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from document_manager.services.settings import CompanyProfile, SettingsService
from document_manager.ui.company_settings import CompanySettings

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

SHELL_STYLE = """
QWidget#workspace { background: #f1f5f9; color: #152740; }
QWidget#sidebar { background: #12223a; }
QLabel#brand { color: white; font-size: 16px; font-weight: 700; }
QListWidget {
    background: transparent; color: #e2e8f0; border: 0; outline: 0;
}
QListWidget::item { padding: 9px 12px; border-radius: 5px; }
QListWidget::item:hover { background: #243c58; }
QListWidget::item:selected { background: #28517b; color: white; }
QListWidget::item:focus { border: 1px solid #93c5fd; }
QWidget#card { background: white; border: 1px solid #d8e1ec; border-radius: 9px; }
QLabel#pageTitle { color: #152740; font-size: 25px; font-weight: 700; }
QLabel#companyName { color: #152740; font-size: 19px; font-weight: 600; }
QLabel { color: #33465d; }
QLineEdit, QPlainTextEdit {
    background: white; color: #152740; border: 1px solid #9aacc1;
    border-radius: 5px; padding: 6px;
}
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #245da0; }
QPushButton {
    background: #245589; color: white; font-weight: 600; border: 1px solid #245589;
    border-radius: 5px; padding: 7px 14px;
}
QPushButton:hover { background: #1b446f; }
QPushButton:focus { border: 1px solid white; }
"""


def plain_label(text: str = "", *, object_name: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsService, profile: CompanyProfile):
        super().__init__()
        self.setWindowTitle("919 Document Manager")
        self.resize(1040, 680)
        self.setMinimumSize(730, 540)
        self.setStyleSheet(SHELL_STYLE)

        self.navigation = QListWidget()
        self.navigation.addItems(NAVIGATION)
        self.navigation.setAccessibleName("Main navigation")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages = QStackedWidget()
        self.company_name = plain_label(profile.name, object_name="companyName")
        self.company_settings = CompanySettings(settings, profile)
        self.company_settings.company_saved.connect(self.company_name.setText)

        for title in NAVIGATION:
            self.pages.addWidget(self._page(title))
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        self.navigation.setFocus()

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 26, 14, 16)
        sidebar_layout.setSpacing(20)
        sidebar_layout.addWidget(plain_label("919 Document Manager", object_name="brand"))
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

    def _page(self, title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(16)
        layout.addWidget(plain_label(title, object_name="pageTitle"))

        card = QWidget()
        card.setObjectName("card")
        details = QVBoxLayout(card)
        details.setContentsMargins(20, 18, 20, 18)
        details.setSpacing(12)
        if title == "Dashboard":
            details.addWidget(plain_label("Active company"))
            details.addWidget(self.company_name)
            edit_company = QPushButton("Open company settings")
            edit_company.clicked.connect(lambda: self.navigation.setCurrentRow(SETTINGS_INDEX))
            details.addWidget(edit_company, alignment=Qt.AlignmentFlag.AlignLeft)
        elif title == "Company Settings":
            details.addWidget(self.company_settings)
        else:
            details.addWidget(plain_label("This section will be available in a later milestone."))
        layout.addWidget(card)
        layout.addStretch()
        return page
