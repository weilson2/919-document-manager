from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QIODevice,
    QMarginsF,
    QObject,
    QSaveFile,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlSchemeHandler,
)
from PySide6.QtWidgets import QDialog, QVBoxLayout

from document_manager.editor.web import SCHEME, EditorRequestPolicy, EditorWebPage

PRINT_URL = SCHEME + b"://print/document.html"


class PrintRequests:
    def __init__(self, content: bytes):
        self.content = content

    def get(self, url, method):
        address = bytes(url.toEncoded())
        if method == b"GET" and (address == PRINT_URL or address.startswith(b"data:image/png;base64,")):
            return self.content
        return None


class PrintPage(EditorWebPage):
    def acceptNavigationRequest(self, url, _navigation_type, is_main_frame: bool) -> bool:
        return is_main_frame and bytes(url.toEncoded()) == PRINT_URL


class PrintResource(QWebEngineUrlSchemeHandler):
    def __init__(self, content, parent):
        super().__init__(parent)
        self.content = content

    def requestStarted(self, job) -> None:
        if bytes(job.requestUrl().toEncoded()) != PRINT_URL or bytes(job.requestMethod()) != b"GET":
            job.fail(job.Error.RequestDenied)
            return
        device = QBuffer(job)
        device.setData(self.content)
        device.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(b"text/html", device)


class PdfJob(QObject):
    """A separate, script-free profile that never shares the editor's channel."""

    def __init__(self, html: str, settings, done: Callable[[bytes | None], None], parent: QObject):
        super().__init__(parent)
        self._done = done
        self._layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4 if settings.page_size == "A4" else QPageSize.PageSizeId.A5),
            QPageLayout.Orientation.Portrait if settings.orientation == "portrait" else QPageLayout.Orientation.Landscape,
            QMarginsF(settings.margin_left, settings.margin_top, settings.margin_right, settings.margin_bottom),
            QPageLayout.Unit.Millimeter,
        )
        content = html.encode("utf-8")
        self._profile = QWebEngineProfile(self)
        self._page = PrintPage(self._profile, self)
        self._policy = EditorRequestPolicy(PrintRequests(content), self._profile)
        self._profile.setUrlRequestInterceptor(self._policy)
        self._resource = PrintResource(content, self._profile)
        self._profile.installUrlSchemeHandler(SCHEME, self._resource)
        for attribute in (
            QWebEngineSettings.WebAttribute.JavascriptEnabled,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
        ):
            self._page.settings().setAttribute(attribute, False)
        self._profile.downloadRequested.connect(lambda item: item.cancel())
        self._page.loadFinished.connect(self._loaded)
        self._page.renderProcessTerminated.connect(lambda *_: self._finish(None))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._finish(None))
        self._timer.start(25_000)
        self._page.load(QUrl.fromEncoded(PRINT_URL))

    def _loaded(self, ok: bool) -> None:
        if ok and self._done is not None:
            self._page.printToPdf(self._printed, self._layout)
        elif not ok:
            self._finish(None)

    def _printed(self, result) -> None:
        pdf = bytes(result)
        document = QPdfDocument()
        buffer = QBuffer()
        buffer.setData(pdf)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        document.load(buffer)
        valid = document.status() == QPdfDocument.Status.Ready and document.pageCount() > 0
        document.close()
        self._finish(pdf if valid else None)

    def _finish(self, pdf: bytes | None) -> None:
        callback, self._done = self._done, None
        if callback is None:
            return
        self._timer.stop()
        self._page.destroyed.connect(self.deleteLater)
        self._page.deleteLater()
        callback(pdf)


class PdfPreview(QDialog):
    def __init__(self, pdf: bytes, parent):
        super().__init__(parent)
        self.setWindowTitle("Print preview")
        self.resize(800, 750)
        self._buffer = QBuffer(self)
        self._buffer.setData(pdf)
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._document = QPdfDocument(self)
        self._document.load(self._buffer)
        view = QPdfView(self)
        view.setPageMode(QPdfView.PageMode.MultiPage)
        view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        view.setDocument(self._document)
        self.content = QVBoxLayout(self)
        self.content.addWidget(view, 1)


def export_pdf(path: Path, pdf: bytes) -> None:
    file = QSaveFile(str(path))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError("The PDF destination is unavailable.")
    if file.write(pdf) != len(pdf) or not file.commit():
        file.cancelWriting()
        raise OSError("The PDF could not be written.")
