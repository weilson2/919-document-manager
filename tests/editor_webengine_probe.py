"""Exercise the editor through a real renderer from source or an installed wheel."""

import json
import sys
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QImage
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


def click(page, selector):
    evaluate(page, f"document.querySelector({json.dumps(selector)}).click()")


def control(page, selector, value):
    evaluate(page, f"""
        (() => {{
          const input = document.querySelector({json.dumps(selector)});
          input.value = {json.dumps(value)};
          input.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }})()
    """)


def select_text(page, selector, select_all=False):
    evaluate(page, f"""
        (() => {{
          document.querySelector('.tiptap').focus();
          const range = document.createRange();
          range.selectNodeContents(document.querySelector({json.dumps(selector)}));
          if (!{json.dumps(select_all)}) range.collapse(false);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
        }})()
    """)
    QTest.qWait(70)


def insert_text(page, text):
    assert evaluate(page, f"document.execCommand('insertText', false, {json.dumps(text)})") is True


def make_image(path: Path, width: int, height: int):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkCyan)
    assert image.save(str(path))


def exercise_visual_tools(page, status, responses):
    verify = "#verify-document"
    select_text(page, ".tiptap p:first-child", select_all=True)
    for action in ("bold", "italic", "underline"):
        click(page, f'[data-command="{action}"]')
    control(page, "#font-family", "Georgia")
    control(page, "#font-size", "18")
    control(page, "#text-color", "#123456")
    control(page, "#alignment", "center")
    control(page, "#line-spacing", "1.5")
    control(page, "#space-after", "12")
    click(page, verify)
    wait_for(page, status, "Document structure verified")
    paragraph = responses[-1][1].document.document.content[0]
    assert paragraph.attrs == {"textAlign": "center", "lineSpacing": "1.5", "spaceAfter": 12}
    marks = {mark.type: mark.attrs for mark in paragraph.content[0].marks}
    assert set(marks) == {"bold", "italic", "underline", "textStyle"}
    assert marks["textStyle"] == {"fontFamily": "Georgia", "fontSize": 18, "color": "#123456"}

    select_text(page, ".tiptap p:first-child")
    control(page, "#block-format", "2")
    wait_for(page, "document.querySelector('#outline button')?.textContent", "Perjanjian sewa — 麻坡 🌿")
    click(page, '[data-command="undo"]')
    wait_for(page, "!!document.querySelector('.tiptap h2')", False)
    click(page, '[data-command="redo"]')
    wait_for(page, "!!document.querySelector('.tiptap h2')", True)

    select_text(page, ".tiptap > p:last-child")
    click(page, '[data-command="bullet-list"]')
    wait_for(page, "document.querySelector('.tiptap ul li')?.textContent", "Lot 12 & 13")
    click(page, '[data-command="undo"]')
    select_text(page, ".tiptap > p:last-child")
    click(page, '[data-command="ordered-list"]')
    wait_for(page, "document.querySelector('.tiptap ol li')?.textContent", "Lot 12 & 13")
    click(page, '[data-command="undo"]')

    select_text(page, ".tiptap > p:nth-child(2)")
    click(page, '[data-command="table"]')
    wait_for(page, "document.querySelectorAll('.tiptap tr').length", 3)
    click(page, '[data-command="add-column"]')
    wait_for(page, "document.querySelector('.tiptap tr').cells.length", 4)
    control(page, "#table-borders", "none")
    wait_for(page, "document.querySelector('.tiptap table')?.dataset.borders", "none")
    evaluate(page, """for (let row = 0; row < 48; row++) document.querySelector('[data-command="add-row"]').click()""")
    wait_for(page, "document.querySelectorAll('.tiptap tr').length", 51)
    select_text(page, ".tiptap tr:last-child td:last-child p")
    evaluate(page, """document.querySelector('.tiptap').dispatchEvent(
        new KeyboardEvent('keydown', {key: 'b', code: 'KeyB', ctrlKey: true, bubbles: true, cancelable: true}))""")
    insert_text(page, "Last row — 麻坡")
    click(page, verify)
    wait_for(page, status, "Document structure verified")
    table = next(node for node in responses[-1][1].document.document.content if node.type == "table")
    assert len(table.content) == 51
    last_cell = table.content[-1].content[-1].content[0].content[0]
    assert last_cell.text == "Last row — 麻坡"
    assert any(mark.type == "bold" for mark in last_cell.marks)

    select_text(page, ".tiptap > p:last-child")
    insert_text(page, " " + "Continuous text with Unicode 麻坡. " * 265)
    wait_for(page, "document.querySelectorAll('#page-nav button').length >= 4", True)
    page_map = "JSON.stringify([...document.querySelectorAll('#page-nav button')].map(b => [b.dataset.start,b.dataset.end]))"
    cuts = evaluate(page, page_map)
    assert evaluate(page, "document.getElementById('layout-warning').textContent") == ""
    control(page, "#zoom", "1.25")
    QTest.qWait(120)
    assert evaluate(page, page_map) == cuts
    click(page, "#preview-toggle")
    wait_for(page, "document.querySelectorAll('.preview-page').length >= 4", True)
    assert evaluate(page, page_map) == cuts
    click(page, "#page-nav button:last-child")
    wait_for(page, "!!document.querySelector('.preview-page:last-child .preview-window .tiptap')", True)
    click(page, "#preview-toggle")
    wait_for(page, "document.querySelector('.tiptap').isContentEditable", True)

    control(page, "#page-size", "A5")
    control(page, "#orientation", "landscape")
    control(page, '[data-margin="margin_left"]', "12")
    click(page, verify)
    wait_for(page, status, "Document structure verified")
    settings = responses[-1][1].document.page_settings
    assert (settings.page_size, settings.orientation, settings.margin_left) == ("A5", "landscape", 12)


def image_point(page, selector):
    x, y = json.loads(evaluate(page, f"""
        (() => {{
          const bounds = document.querySelector({json.dumps(selector)}).getBoundingClientRect();
          return JSON.stringify([Math.round(bounds.left + bounds.width / 2), Math.round(bounds.top + Math.min(bounds.height / 2, 14))]);
        }})()
    """))
    return QPoint(x, y)


def exercise_images(page, status, workspace, view):
    invalid = workspace / "invalid.png"
    invalid.write_text("<svg/>", encoding="utf-8")
    tall = workspace / "tall.png"
    make_image(tall, 100, 1000)
    with patch("document_manager.ui.editor_page.QFileDialog.getOpenFileName", side_effect=[
        (str(invalid), ""), (str(tall), ""),
    ]):
        click(page, '[data-command="image"]')
        wait_for(page, status, "Choose a valid PNG or JPEG up to 8 MB and 4096 × 4096 pixels.")
        assert not list(workspace.glob("editor-assets/**/*.png"))
        select_text(page, ".tiptap > p:last-child")
        click(page, '[data-command="image"]')
        wait_for(page, "document.querySelector('.tiptap img')?.naturalHeight", 1000)
    src = evaluate(page, "document.querySelector('.tiptap img').src")
    assert "/image/" in src
    assert len(list((workspace / "editor-assets" / "1").glob("*.png"))) == 1
    click(page, "#verify-document")
    wait_for(page, status, "Document structure verified")
    wait_for(page, "document.getElementById('layout-warning').textContent", "Oversized content extends beyond the paper size.")
    click(page, "#preview-toggle")
    assert evaluate(page, "Math.max(...[...document.querySelectorAll('.preview-page')].map(p => p.offsetHeight))") > 148 * 96 / 25.4
    click(page, "#preview-toggle")
    control(page, "#zoom", "fit")
    evaluate(page, "document.querySelector('.tiptap img').scrollIntoView({block: 'start', inline: 'nearest'})")
    QTest.qWait(100)
    surface = view.focusProxy()
    QTest.mouseClick(surface, Qt.MouseButton.LeftButton, pos=image_point(page, ".tiptap img"))
    wait_for(page, "!document.getElementById('image-properties').hidden", True)
    wait_for(page, "document.getElementById('image-width').value", "70")
    control(page, "#image-width", "60")
    wait_for(page, "document.querySelector('.managed-image-frame').style.width", "60%")

    handle = ".ProseMirror-selectednode .image-resize-handle"
    evaluate(page, f"document.querySelector({json.dumps(handle)}).scrollIntoView({{block: 'center', inline: 'nearest'}})")
    QTest.qWait(100)
    start = image_point(page, handle)
    span = evaluate(page, "document.querySelector('.ProseMirror-selectednode').getBoundingClientRect().width")
    end = start - QPoint(round(span * 0.2), 0)
    QTest.mousePress(surface, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(surface, end, 50)
    QTest.mouseRelease(surface, Qt.MouseButton.LeftButton, pos=end)
    wait_for(page, "document.querySelector('.managed-image-frame').style.width", "40%")
    wait_for(page, "document.getElementById('image-width').value", "40")
    click(page, '[data-command="undo"]')
    wait_for(page, "document.querySelector('.managed-image-frame').style.width", "60%")
    click(page, '[data-command="redo"]')
    wait_for(page, "document.querySelector('.managed-image-frame').style.width", "40%")
    click(page, "#verify-document")
    wait_for(page, status, "Document structure verified")
    return src


def assert_image_blocked(page, src):
    evaluate(page, f"""
        (() => {{
          delete document.body.dataset.imageResult;
          const image = new Image();
          image.onload = () => {{ document.body.dataset.imageResult = "loaded"; }};
          image.onerror = () => {{ document.body.dataset.imageResult = "blocked"; }};
          image.src = {json.dumps(src)};
          document.body.append(image);
        }})()
    """)
    wait_for(page, "document.body.dataset.imageResult", "blocked")


def main(workspace: Path) -> None:
    register_editor_scheme()
    app = QApplication([])
    engine = create_database_engine(workspace / "document-manager.sqlite3")
    upgrade_database(engine)
    settings = SettingsService(engine)
    other = settings.create_company(CompanyProfile(name="Test company", registration_number="TEST-001", address="Muar"))
    window = MainWindow(settings, BusinessService(engine), 1, settings.get_company(), workspace)
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
            assert verified.document.schema_version == 2
            assert [(node.type, [child.text for child in node.content]) for node in verified.document.document.content] == [
                ("paragraph", [lines[0]]), ("paragraph", []), ("paragraph", [lines[2]]),
            ]

            for url in (
                "https://outside.invalid/", "file:///C:/document-manager-editor-test-denied.txt",
                "document-manager-editor://app/app.js",
            ):
                evaluate(page, f"void (location.href = {json.dumps(url)})")
                QTest.qWait(150)
                assert page.url().toEncoded() == ENTRY_URL
                assert evaluate(page, status) == "Document structure verified"

            exercise_visual_tools(page, status, responses)
            image_url = exercise_images(page, status, workspace, host._view)
            assert_image_blocked(page, "https://outside.invalid/logo.png")
            window.company_selector.setCurrentIndex(window.company_selector.findData(other))
            new_page = host._page
            assert new_page is not page
            wait_for(new_page, status, "Editor ready")
            assert responses[-1][0] == "open"
            fresh = responses[-1][1]
            assert fresh.company_id == other and fresh.session_id != verified.session_id
            assert evaluate(new_page, "document.querySelector('.tiptap').textContent") == ""
            assert_image_blocked(new_page, image_url)
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
