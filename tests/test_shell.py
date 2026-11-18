import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
)

from document_manager.services.business import BusinessService
from document_manager.services.settings import SettingsService
from document_manager.ui.company_logo import read_logo
from document_manager.ui.editor_page import DocumentEditor
from document_manager.ui.main_window import MainWindow
from document_manager.ui.record_forms import record_dialog


@pytest.fixture
def shell(qtbot, database_engine):
    settings = SettingsService(database_engine)
    business = BusinessService(database_engine)
    window = MainWindow(settings, business, settings.get_default_company_id(), settings.get_company())
    qtbot.addWidget(window)
    window.show()
    return window, settings, business


def test_navigation_and_company_settings(qtbot, shell, monkeypatch):
    # WebEngine startup is covered in a separate process that tests the real renderer.
    monkeypatch.setattr(DocumentEditor, "activate", lambda _editor: None)
    window, settings, _business = shell
    assert window.company_name.text() == "919 RESTAURANT"
    qtbot.mouseClick(window.dashboard.settings_button, Qt.MouseButton.LeftButton)
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


def submit_form(button, values):
    def fill_and_save():
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            return
        try:
            dialog.fields.load(values)
            dialog.save()
        finally:
            if dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, fill_and_save)
    button.click()


def test_desktop_quick_create_switch_archive_and_restore(shell):
    window, settings, _business = shell
    new_tenant = next(button for button in window.dashboard.findChildren(QPushButton) if button.text() == "New tenant")
    submit_form(new_tenant, {
        "name": "Test Tenant", "identification_number": "TN-01", "stall_number": "A-01",
        "rental_amount": "100.10", "start_date": "2026-10-03",
    })
    tenants = window.record_pages["tenant"]
    assert window.pages.currentWidget().findChild(QLabel, "pageTitle").text() == "Tenants"
    assert tenants.table.rowCount() == 1
    assert window.dashboard.values["active_tenants"].text() == "1"
    submit_form(tenants.new_button, {
        "name": "Other Tenant", "identification_number": "TN-02", "stall_number": "A-02",
        "rental_amount": "0.001", "start_date": "2026-10-04",
    })
    assert tenants.table.rowCount() == 1
    tenants.table.selectRow(0)
    tenants.archive_button.click()
    assert tenants.table.rowCount() == 0
    assert window.dashboard.values["active_tenants"].text() == "0"
    tenants.archive_filter.setChecked(True)
    tenants.table.selectRow(0)
    assert tenants.archive_button.text() == "Restore"
    tenants.archive_button.click()
    assert tenants.table.rowCount() == 0

    window.dashboard.settings_button.click()
    new_company = next(
        button for button in window.company_settings.findChildren(QPushButton) if button.text() == "New company"
    )
    submit_form(new_company, {"name": "Second company", "registration_number": "NEW-123", "address": "Muar"})
    second = window.company_selector.currentData()
    assert second != 1
    assert window.company_name.text() == "Second company"
    assert tenants.table.rowCount() == 0
    assert not tenants.archive_filter.isChecked()
    assert settings.get_default_company_id() == 1
    window.company_settings.default_button.click()
    assert settings.get_default_company_id() == second
    window.company_selector.setCurrentIndex(window.company_selector.findData(1))
    assert tenants.table.rowCount() == 1
    assert window.company_name.text() == "919 RESTAURANT"
    assert settings.get_default_company_id() == second


def test_company_form_switch_can_keep_unsaved_edits(monkeypatch, shell):
    window, settings, _business = shell
    original = settings.get_company(1)
    second = settings.create_company(original.model_copy(update={"name": "Second", "registration_number": "C-2"}))
    window._reload_companies()
    window.company_settings.name.setText("Unsaved edits")
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Cancel)
    window.company_selector.setCurrentIndex(window.company_selector.findData(second))
    assert window.company_selector.currentData() == 1
    assert window.company_settings.name.text() == "Unsaved edits"
    window.company_settings.name.setText(original.name)


def test_logo_import_normalizes_and_persists_inside_company_profile(monkeypatch, shell, tmp_path):
    window, settings, _business = shell
    path = tmp_path / "example.jpg"
    image = QImage(24, 16, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkBlue)
    assert image.save(str(path), "JPEG")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(path), "Images"))
    form = window.company_settings
    choose = next(button for button in form.findChildren(QPushButton) if button.text() == "Choose logo")
    choose.click()
    form.save_button.click()
    logo = settings.get_company(1).logo
    assert logo.startswith(b"\x89PNG\r\n\x1a\n")
    assert not form.preview.pixmap().isNull()
    bad = tmp_path / "bad.png"
    bad.write_text("<svg />", encoding="utf-8")
    with pytest.raises(ValueError, match="PNG or JPEG"):
        read_logo(bad)
    form.remove_logo.click()
    form.save_button.click()
    assert settings.get_company(1).logo is None


def test_template_page_can_assign_category_publish_and_duplicate(shell):
    window, _settings, business = shell
    window.navigation.setCurrentRow(1)
    page = window.record_pages["template"]
    submit_form(page.category_button, {"name": "Business"})
    category_id, = page.categories
    submit_form(page.new_button, {"name": "Offer letter", "description": "Employment", "category_id": category_id})
    page.type_filter.setCurrentIndex(page.type_filter.findData(category_id))
    page.table.selectRow(0)
    page.publish_button.click()
    assert page.table.item(0, 2).text() == "Published"
    assert business.list_template_versions(1, page.rows[0].id)[0].metadata_snapshot["category"] == "Business"
    page.table.selectRow(0)
    page.duplicate_button.click()
    assert page.table.rowCount() == 2
    page.status_filter.setCurrentIndex(page.status_filter.findData("draft"))
    assert page.table.item(0, 0).text() == "Offer letter (copy)"


def test_dropdowns_use_readable_popup_colors_with_dark_system_palette(qtbot, shell):
    window, _settings, _business = shell
    original = QApplication.palette()
    dark = QPalette(original)
    dark.setColor(QPalette.ColorRole.Base, QColor("#202124"))
    dark.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
    QApplication.setPalette(dark)

    try:
        dialog = record_dialog(window, "tenant", {}, None, lambda _values: None)
        qtbot.addWidget(dialog)
        dialog.show()
        rental_types = dialog.fields.widgets["rental_type"]
        for combo in (dialog.fields.widgets["identification_type"], rental_types):
            chevron = QPoint(combo.width() - 15, combo.height() // 2)
            qtbot.mouseClick(combo, Qt.MouseButton.LeftButton, pos=chevron)
            try:
                view = combo.view()
                assert view.isVisible()
                colors = view.palette()
                assert colors.base().color().name() == "#ffffff"
                assert colors.text().color().name() == "#152740"
                assert colors.highlight().color().name() == "#28517b"
                assert colors.highlightedText().color().name() == "#ffffff"
                qtbot.keyClick(view, Qt.Key.Key_Home)
                qtbot.keyClick(view, Qt.Key.Key_Return)
            finally:
                combo.hidePopup()
        assert rental_types.currentData() == "daily"
        dialog.close()
    finally:
        QApplication.setPalette(original)
