from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from document_manager.services.settings import SettingsService
from document_manager.ui.main_window import MainWindow


def test_navigation_and_company_settings(qtbot, database_engine):
    settings = SettingsService(database_engine)
    window = MainWindow(settings, settings.get_company())
    qtbot.addWidget(window)
    window.show()
    assert window.company_name.text() == "919 RESTAURANT"
    dashboard_action = window.pages.currentWidget().findChild(QPushButton)
    qtbot.mouseClick(dashboard_action, Qt.MouseButton.LeftButton)
    assert window.pages.currentWidget().findChild(QLabel, "pageTitle").text() == "Company Settings"

    expected_pages = [
        "Dashboard", "Templates", "Document Editor", "Documents", "History",
        "Tenants", "Employees", "Payroll", "Company Settings", "Backup & Restore",
    ]
    assert window.navigation.count() == len(expected_pages)
    for index, title in enumerate(expected_pages):
        rect = window.navigation.visualItemRect(window.navigation.item(index))
        qtbot.mouseClick(window.navigation.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        page_title = window.pages.currentWidget().findChild(QLabel, "pageTitle")
        assert page_title.text() == title

    window.navigation.setCurrentRow(expected_pages.index("Company Settings"))
    form = window.company_settings
    form.name.setText("    ")
    qtbot.mouseClick(form.save_button, Qt.MouseButton.LeftButton)
    assert "Company name" in form.status.text()
    assert settings.get_company().name == "919 RESTAURANT"

    form.name.setText("  Kedai Baharu  ")
    qtbot.mouseClick(form.save_button, Qt.MouseButton.LeftButton)
    assert form.status.text() == "Company settings saved."
    assert settings.get_company().name == "Kedai Baharu"
    assert window.company_name.text() == "Kedai Baharu"
