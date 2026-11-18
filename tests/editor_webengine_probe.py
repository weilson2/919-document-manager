"""Exercise the editor through a real renderer from source or an installed wheel."""

import json
import sys
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from PySide6.QtCore import (
    QBuffer,
    QCoreApplication,
    QEvent,
    QEventLoop,
    QPoint,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

import document_manager
from document_manager.editor.bridge import DocumentResponse, EditorSession
from document_manager.editor.images import import_image, load_image
from document_manager.editor.print_layout import print_html
from document_manager.editor.web import ENTRY_URL, register_editor_scheme
from document_manager.persistence.database import (
    create_database_engine,
    upgrade_database,
)
from document_manager.services.business import BusinessService
from document_manager.services.designs import checked_document
from document_manager.services.settings import CompanyProfile, SettingsService
from document_manager.ui.acceptance_workspace import create_acceptance_workspace
from document_manager.ui.fill_document import FillDialog
from document_manager.ui.main_window import EDITOR_INDEX, NAVIGATION, MainWindow
from document_manager.ui.pdf_view import PdfJob, PdfPreview


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


def exercise_fields(page, status, responses):
    chips = "document.querySelectorAll('#editor .document-field').length"
    library = "document.getElementById('field-library').options.length"
    message = "document.getElementById('field-message').textContent"
    submit = "#field-form button[type=submit]"
    click(page, "#new-field")
    control(page, "#field-key", "tenant_name")
    control(page, "#field-label", "承租人 · Tenant")
    control(page, "#field-type", "currency")
    control(page, "#field-default", "120.005")
    click(page, submit)
    wait_for(page, f"{message}.includes('2 decimal places')", True)
    control(page, "#field-default", "120.50")
    control(page, "#field-format", "symbol")
    click(page, submit)
    wait_for(page, library, 2)
    click(page, '[data-command="undo"]')
    wait_for(page, library, 1)
    click(page, '[data-command="redo"]')
    wait_for(page, library, 2)

    field_id = evaluate(page, "document.getElementById('field-library').options[1].value")
    control(page, "#field-library", field_id)
    select_text(page, ".tiptap h2")
    click(page, "#insert-field")
    click(page, "#insert-field")
    wait_for(page, chips, 2)
    usage = "document.getElementById('field-usage').textContent"
    wait_for(page, usage, "Used in 2 places. They all share these settings.")
    click(page, '[data-command="undo"]')
    wait_for(page, chips, 1)
    wait_for(page, usage, "Used in 1 place.")
    click(page, '[data-command="redo"]')
    wait_for(page, chips, 2)

    click(page, "#editor .document-field")
    control(page, "#field-key", "rent_amount")
    control(page, "#field-label", "月租 · Rent")
    click(page, submit)
    labels = "JSON.stringify([...document.querySelectorAll('#editor .document-field')].map(node=>node.textContent))"
    wait_for(page, labels, json.dumps(["月租 · Rent", "月租 · Rent"], ensure_ascii=False, separators=(",", ":")))
    click(page, '[data-command="undo"]')
    wait_for(page, labels, json.dumps(["承租人 · Tenant", "承租人 · Tenant"], ensure_ascii=False, separators=(",", ":")))
    click(page, '[data-command="redo"]')
    wait_for(page, labels, json.dumps(["月租 · Rent", "月租 · Rent"], ensure_ascii=False, separators=(",", ":")))
    select_text(page, ".tiptap h2", select_all=True)
    click(page, '[data-command="bold"]')
    click(page, "#editor .document-field")
    click(page, "#delete-field")
    wait_for(page, f"{message}.includes('Remove all references')", True)
    click(page, "#new-field")
    control(page, "#field-key", "rent_amount")
    control(page, "#field-label", "Duplicate")
    click(page, submit)
    wait_for(page, f"{message}.includes('unique')", True)
    click(page, "#verify-document")
    wait_for(page, status, "Document structure verified")
    data = responses[-1][1].document.model_dump(exclude_unset=True)
    assert data["fields"][0]["id"] == field_id
    assert data["fields"][0]["key"] == "rent_amount"
    assert data["fields"][0]["default"] == "120.50"
    assert sum(node.get("attrs", {}).get("fieldId") == field_id for node in data["document"]["content"][0]["content"]) == 2

    # Deleting document nodes keeps their reusable definition and history restores the reference.
    click(page, "#editor .document-field")
    evaluate(page, """document.querySelector('.tiptap').dispatchEvent(
        new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true, cancelable: true}))""")
    wait_for(page, chips, 1)
    wait_for(page, library, 2)
    click(page, '[data-command="undo"]')
    wait_for(page, chips, 2)
    click(page, "#new-field")
    control(page, "#field-key", "unused")
    control(page, "#field-label", "Unused")
    click(page, submit)
    wait_for(page, library, 3)
    click(page, "#delete-field")
    wait_for(page, library, 2)
    click(page, '[data-command="undo"]')
    wait_for(page, library, 3)

    control(page, "#field-library", field_id)
    cell = ".tiptap tr:last-child td:last-child p"
    select_text(page, cell, select_all=True)
    click(page, "#insert-field")
    wait_for(page, chips, 3)
    wait_for(page, f"document.querySelector('{cell}').textContent", "月租 · Rent")
    click(page, '[data-command="undo"]')
    wait_for(page, chips, 2)
    wait_for(page, f"document.querySelector('{cell}').textContent", "Last row — 麻坡")


def exercise_print(company_id, workspace, business, parent):
    business.install_starters(company_id)
    starter = {template.name: template.id for template in business.designs.published_list(company_id)}
    assert len(starter) == 10
    template = starter["Blank Document"]
    original = business.designs.open(company_id, template)
    payload = original.document.model_dump(exclude_unset=True)
    first = {"type": "paragraph", "content": [{"type": "text", "text": "Perjanjian sewa 麻坡"}]}
    second = {"type": "paragraph", "content": [{"type": "text", "text": "Second page"}]}
    local_image = workspace / "print-logo.png"
    make_image(local_image, 80, 24)
    image = import_image(workspace, company_id, local_image)
    table = {"type": "table", "content": [
        {"type": "tableRow", "content": [{"type": "tableCell", "content": [second]}]},
    ]}
    payload["document"]["content"] = [first, {"type": "image", "attrs": {"assetId": image.asset_id, "width": 30}},
                                    {"type": "pageBreak"}, table]
    payload["print_settings"] = {"header": "Fictional header", "footer": "Fictional footer", "page_numbers": True}
    business.designs.save(company_id, template, original.revision, payload, publish=True)
    version = business.designs.published(company_id, template)
    design = checked_document(version.document_json)
    filled = business.fill.capture(company_id, design, {}, {})
    html = print_html(design, filled.text_by_id, lambda asset_id: load_image(workspace, company_id, asset_id).content)
    pdf = render_probe_pdf(html, design.page_settings, parent)
    document = QPdfDocument()
    buffer = QBuffer()
    buffer.setData(pdf)
    buffer.open(QBuffer.OpenModeFlag.ReadOnly)
    document.load(buffer)
    assert document.status() == QPdfDocument.Status.Ready
    assert document.pageCount() == 2
    assert abs(document.pagePointSize(0).width() - 595) <= 2
    assert abs(document.pagePointSize(0).height() - 842) <= 2
    first_text = document.getAllText(0).text()
    second_text = document.getAllText(1).text()
    assert "Perjanjian sewa" in first_text and "麻坡" in first_text
    assert "Second page" in second_text and "Fictional footer" in second_text and "2" in second_text
    preview = QImage(QSize(595, 842), QImage.Format.Format_RGB32)
    preview.fill(Qt.GlobalColor.white)
    with QPainter(preview) as painter:
        painter.drawImage(0, 0, document.render(0, preview.size()))
    assert preview.save(str(workspace / "rendered-preview.png"))
    assert any(preview.pixelColor(x, y).name() == "#008080"
               for x in range(60, 230, 5) for y in range(80, 150, 5)), "The image is missing from the printed page."
    assert all(preview.pixelColor(x, 100).name() == "#ffffff" for x in range(50))
    document_id = business.documents.save(company_id, version.id, filled, pdf)
    assert business.documents.get(company_id, document_id).pdf == pdf
    document.close()

    rows = [
        {"type": "tableRow", "content": [{"type": "tableCell", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": f"Row-{index:03} · 测试"}]},
        ]}]} for index in range(120)
    ]
    payload["document"]["content"] = [{"type": "table", "content": rows}]
    payload["page_settings"].update(page_size="A5", orientation="landscape")
    a5 = checked_document(payload)
    landscape = render_probe_pdf(print_html(a5, {}, lambda _asset: b""), a5.page_settings, parent)
    buffer.close()
    buffer.setData(landscape)
    buffer.open(QBuffer.OpenModeFlag.ReadOnly)
    document.load(buffer)
    assert document.pageCount() > 3
    assert abs(document.pagePointSize(0).width() - 595) <= 2
    assert abs(document.pagePointSize(0).height() - 420) <= 2
    # PDFium may insert line separators between glyph runs even when the row renders on one line.
    content = "\n".join("".join(document.getAllText(page).text().splitlines()) for page in range(document.pageCount()))
    anomalies = {index: content.count(f"Row-{index:03}") for index in range(120)
                 if content.count(f"Row-{index:03}") != 1}
    assert not anomalies, anomalies
    document.close()


def render_probe_pdf(html, settings, parent):
    loop = QEventLoop()
    result = []

    def done(value):
        result.append(value)
        loop.quit()

    PdfJob(html, settings, done, parent)
    if not result:
        QTimer.singleShot(27_000, loop.quit)
        loop.exec()
    assert result and result[0], "Qt WebEngine could not produce a valid offline PDF."
    return result[0]


def exercise_document_journeys(workspace):
    workspace.mkdir()
    engine = create_database_engine(workspace / "document-manager.sqlite3")
    try:
        upgrade_database(engine)
        settings = SettingsService(engine)
        business = BusinessService(engine)
        create_acceptance_workspace(settings, business, 1)
        assert len(business.list_records("tenant", 1)) == len(business.list_records("employee", 1)) == 2
        assert len(business.documents.list(1)) == 3
        window = MainWindow(settings, business, 1, settings.get_company(1), workspace, starter_designs=True)
        window.show()
        qapp = QApplication.instance()
        try:
            initial_agreement = business.documents.list(1, "Stall Rental Agreement")[0]
            initial_pdf = business.documents.get(1, initial_agreement.id).pdf
            window._reuse_document(initial_agreement.id)
            fill = visible_dialog(window, FillDialog)
            fields = {field.key: field.id for field in fill._design.fields}
            fill._fields[fields["rent"]][2]("1302.98")
            save_visible_pdf(window, fill)
            assert len(business.documents.list(1, "Stall Rental Agreement")) == 2
            assert business.documents.get(1, initial_agreement.id).pdf == initial_pdf

            find_button(window.dashboard, "New Offer Letter").click()
            fill = visible_dialog(window, FillDialog)
            chooser = fill._subjects["employee"]
            chooser.setCurrentIndex(1)
            fields = {field.key: field.id for field in fill._design.fields}
            assert fill._fields[fields["salary"]][1]() == "2100.00"
            for key, value in (("probation", "90 days"), ("notice", "As agreed"), ("hours", "See the roster")):
                fill._fields[fields[key]][2](value)
            save_visible_pdf(window, fill)
            assert len(business.documents.list(1, "Employee Offer Letter")) == 2

            find_button(window.dashboard, "New Payslip").click()
            assert window.navigation.currentRow() == NAVIGATION.index("Payroll")
            payroll = window.payroll
            payroll._selected_employee.setCurrentIndex(1)
            payroll._inputs["overtime"].setText("12.90")
            find_button(payroll, "Check approval").click()
            assert payroll._status.text().startswith("Approval blocked")
            find_button(payroll, "Save draft revision").click()
            find_button(payroll, "Preview payslip").click()
            fill = visible_dialog(window, FillDialog)
            save_visible_pdf(window, fill)
            assert all(run.status == "draft" for run in business.payroll.list(1))
            assert len(business.documents.list(1, "Draft payslip")) == 2

            custom = next(row.id for row in business.designs.published_list(1) if row.name.startswith("Demo Custom"))
            assert window._open_design(custom)
            editor = window.document_editor._page
            status = "document.getElementById('editor-status').textContent"
            wait_for(editor, status, "Editor ready")
            select_text(editor, ".tiptap h1")
            insert_text(editor, " 确认")
            wait_for(editor, status, "Draft saved")
            click(editor, "#publish-design")
            wait_for(editor, status, "Version 2 published")
            window._open_fill(custom)
            fill = visible_dialog(window, FillDialog)
            fill._fields[fill._design.fields[0].id][2]("Fictional Visitor")
            find_button(fill, "Edit design").click()
            assert window._paused_fill is fill and not fill.isVisible()
            find_button(window, "Return to filled values").click()
            assert visible_dialog(window, FillDialog) is fill
            assert fill._fields[fill._design.fields[0].id][1]() == "Fictional Visitor"
            save_visible_pdf(window, fill)
            assert len(business.documents.list(1, "Demo Custom")) == 1
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            qapp.processEvents()
    finally:
        engine.dispose()


def find_button(parent, label):
    return next(button for button in parent.findChildren(QPushButton) if button.text() == label)


def visible_dialog(parent, kind):
    deadline = monotonic() + 12
    while monotonic() < deadline:
        for dialog in parent.findChildren(kind):
            if dialog.isVisible():
                return dialog
        QTest.qWait(30)
    raise AssertionError(f"{kind.__name__} did not open.")


def save_visible_pdf(window, fill):
    loop = QEventLoop()
    saved = []
    failure = []
    timer = QTimer()
    deadline = monotonic() + 20
    fill.saved.connect(saved.append)

    def confirm():
        preview = next((dialog for dialog in window.findChildren(PdfPreview) if dialog.isVisible()), None)
        if preview is None:
            if monotonic() < deadline and fill._printing:
                return
            failure.append("Print preview did not open.")
            timer.stop()
            loop.quit()
            return
        try:
            find_button(preview, "Save to history").click()
            assert saved
            find_button(preview, "Back to form").click()
            QTimer.singleShot(0, fill.reject)
        except (AssertionError, RuntimeError, StopIteration) as error:
            failure.append(error)
        finally:
            timer.stop()
            loop.quit()

    find_button(fill, "Preview PDF").click()
    timer.timeout.connect(confirm)
    timer.start(25)
    loop.exec()
    assert not failure, (failure, fill._status.text())
    QTest.qWait(30)


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
            host = window.document_editor
            prepared_page = host._view.page()
            assert host._view.focusProxy() is not None
            assert host._session is None
            window.show()
            native_window_id = window.winId()
            window.navigation.setCurrentRow(EDITOR_INDEX)
            page = host._page
            assert page is prepared_page
            status = "document.getElementById('editor-status')?.textContent"
            wait_for(page, status, "Editor ready")
            assert window.winId() == native_window_id
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
            assert verified.document.schema_version == 3
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
            exercise_fields(page, status, responses)
            window.navigation.setCurrentRow(0)
            window.navigation.setCurrentRow(EDITOR_INDEX)
            assert window.winId() == native_window_id
            assert host._page is page
            assert evaluate(page, "document.querySelectorAll('#editor .document-field').length") == 2
            window.company_selector.setCurrentIndex(window.company_selector.findData(other))
            new_page = host._page
            assert new_page is not page
            wait_for(new_page, status, "Editor ready")
            assert responses[-1][0] == "open"
            fresh = responses[-1][1]
            assert fresh.company_id == other and fresh.session_id != verified.session_id
            assert evaluate(new_page, "document.querySelector('.tiptap').textContent") == ""
            assert evaluate(new_page, "document.getElementById('field-library').options.length") == 1
            assert_image_blocked(new_page, image_url)
            exercise_print(other, workspace, window.business, window)
    finally:
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        engine.dispose()
    exercise_document_journeys(workspace / "fictional")
    print("Offline renderer startup, WebChannel JSON round trip, navigation policy, and company switch passed.")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        assert Path(document_manager.__file__).is_relative_to(Path(sys.argv[2]))
    main(Path(sys.argv[1]))
