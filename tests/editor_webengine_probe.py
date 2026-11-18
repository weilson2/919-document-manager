"""Exercise the editor through a real renderer from source or an installed wheel."""

import json
import sys
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import document_manager
from document_manager.editor.bridge import DocumentResponse, EditorSession
from document_manager.editor.web import ENTRY_URL, register_editor_scheme
from document_manager.persistence.database import (
    create_database_engine,
    upgrade_database,
)
from document_manager.services.business import BusinessService
from document_manager.services.settings import CompanyProfile, SettingsService
from document_manager.ui.main_window import EDITOR_INDEX, MainWindow


def evaluate(page, script):
    result = []
    wait = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(wait.quit)

    def complete(value):
        result.append(value)
        wait.quit()

    page.runJavaScript(script, complete)
    if not result:
        timer.start(4000)
        wait.exec()
    assert result, "Renderer did not respond."
    return result[0]


def wait_for(page, script, expected):
    deadline = monotonic() + 12
    while monotonic() < deadline:
        value = evaluate(page, script)
        if value == expected:
            return
        QTest.qWait(30)
    raise AssertionError(f"Expected {expected!r}, got {value!r}")


def main(workspace: Path) -> None:
    register_editor_scheme()
    app = QApplication([])
    engine = create_database_engine(workspace / "document-manager.sqlite3")
    upgrade_database(engine)
    settings = SettingsService(engine)
    other = settings.create_company(CompanyProfile(name="Test company", registration_number="TEST-001", address="Muar"))
    window = MainWindow(settings, BusinessService(engine), 1, settings.get_company())
    original = EditorSession.handle
    responses = []

    def capture(session, raw):
        response = original(session, raw)
        responses.append((json.loads(raw)["method"], response))
        return response

    try:
        with patch.object(EditorSession, "handle", capture):
            window.show()
            window.navigation.setCurrentRow(EDITOR_INDEX)
            host = window.document_editor
            page = host._page
            status = "document.getElementById('editor-status')?.textContent"
            wait_for(page, status, "Editor ready")
            assert page.url().toEncoded() == ENTRY_URL
            assert page.profile().isOffTheRecord()
            assert page.renderProcessPid() > 0
            assert responses[0][0] == "open"
            assert responses[0][1].company_id == 1

            lines = ["Perjanjian sewa — 麻坡 🌿", "", "Lot 12 & 13"]
            sample = json.dumps("\n".join(lines))
            assert evaluate(page, f"""
                (() => {{
                  document.querySelector('.tiptap').focus();
                  return document.execCommand('insertText', false, {sample});
                }})()
            """) is True
            evaluate(page, "document.getElementById('verify-document').click()")
            wait_for(page, status, "Document structure verified")
            assert responses[-1][0] == "verify_document"
            verified = responses[-1][1]
            assert isinstance(verified, DocumentResponse)
            assert verified.document.model_dump(exclude_unset=True) == {
                "schema_version": 1,
                "document": {
                    "type": "doc",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": lines[0]}]},
                        {"type": "paragraph"},
                        {"type": "paragraph", "content": [{"type": "text", "text": lines[2]}]},
                    ],
                },
            }

            for url in (
                "https://outside.invalid/", "file:///C:/document-manager-editor-test-denied.txt",
                "document-manager-editor://app/app.js",
            ):
                evaluate(page, f"void (location.href = {json.dumps(url)})")
                QTest.qWait(150)
                assert page.url().toEncoded() == ENTRY_URL
                assert evaluate(page, status) == "Document structure verified"

            window.company_selector.setCurrentIndex(window.company_selector.findData(other))
            new_page = host._page
            assert new_page is not page
            wait_for(new_page, status, "Editor ready")
            assert responses[-1][0] == "open"
            fresh = responses[-1][1]
            assert fresh.company_id == other and fresh.session_id != verified.session_id
            assert evaluate(new_page, "document.querySelector('.tiptap').textContent") == ""
    finally:
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        engine.dispose()
    print("Offline renderer startup, WebChannel JSON round trip, navigation policy, and company switch passed.")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        assert Path(document_manager.__file__).is_relative_to(Path(sys.argv[2]))
    main(Path(sys.argv[1]))
