import logging
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from document_manager.editor.bridge import EditorBridge, EditorSession
from document_manager.editor.images import import_image
from document_manager.editor.visual_schema import PageSettings
from document_manager.editor.web import (
    ENTRY_URL,
    SCHEME,
    EditorImages,
    EditorRequestPolicy,
    EditorResources,
    EditorWebPage,
)
from document_manager.ui.widgets import plain_label

logger = logging.getLogger(__name__)


class DocumentEditor(QWidget):
    def __init__(self, data_dir: Path | None):
        super().__init__()
        self._data_dir = data_dir
        self._company_id = None
        self._page_settings = PageSettings()
        self._images = EditorImages()
        self._session = None
        self._page = None
        self._profile = None
        self._view = None
        self._status = plain_label("Opening the local editor…")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._status)

    def set_company(self, company_id: int, page_settings: PageSettings) -> None:
        self._page_settings = page_settings
        if company_id != self._company_id:
            self.close_session()
            self._company_id = company_id
            if self.isVisible():
                self.activate()

    def prepare_view(self) -> bool:
        if self._profile is None:
            try:
                resources = EditorResources(self._images, self)
            except OSError:
                logger.exception("Editor resources unavailable")
                self._status.setText("Editor files are unavailable. Reinstall 919 Document Manager and try again.")
                return False
            # Create the view before its profile so the owned pages are destroyed first.
            self._view = QWebEngineView(self)
            self._view.setAccessibleName("Local document editor")
            self._layout.addWidget(self._view, 1)
            self._profile = QWebEngineProfile(self)
            self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            self._profile.setUrlRequestInterceptor(EditorRequestPolicy(self._images, self._profile))
            self._profile.installUrlSchemeHandler(SCHEME, resources)
            resources.setParent(self._profile)
            self._profile.downloadRequested.connect(lambda item: item.cancel())
            page = EditorWebPage(self._profile, self._view)
            self._view.setPage(page)
            # Initialize the blank page's rendering widget before the main window is shown.
            # On Windows Qt can recreate a visible native window when it first needs WebEngine compositing.
            page.toPlainText(lambda _text: None)
        return True

    def activate(self) -> None:
        if self._session is not None or self._company_id is None or not self.prepare_view():
            return
        self._status.setText("Opening the local editor…")
        self._status.show()
        previous = self._page
        page = self._view.page() if previous is None else EditorWebPage(self._profile, self._view)
        self._page = page
        company_id = self._company_id
        self._session = EditorSession(
            company_id, self._page_settings, lambda: self._choose_image(company_id), self._images.add,
        )
        channel = QWebChannel(page)
        channel.registerObject("editorBridge", EditorBridge(self._session, channel))
        page.setWebChannel(channel)

        attribute = QWebEngineSettings.WebAttribute
        for name in (
            attribute.LocalContentCanAccessFileUrls, attribute.LocalContentCanAccessRemoteUrls,
            attribute.JavascriptCanOpenWindows, attribute.JavascriptCanAccessClipboard,
            attribute.PluginsEnabled, attribute.LocalStorageEnabled,
        ):
            page.settings().setAttribute(name, False)

        page.loadFinished.connect(lambda ok: self._on_loaded(page, ok))
        page.renderProcessTerminated.connect(lambda *_: self._on_terminated(page))
        if previous is not None:
            self._view.setPage(page)
            previous.deleteLater()
        self._view.show()
        page.load(QUrl.fromEncoded(ENTRY_URL))

    def close_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
            self._page.setWebChannel(None)
            self._view.hide()
            self._images.clear()

    def _choose_image(self, company_id: int):
        if self._data_dir is None:
            raise OSError("The editor workspace is unavailable.")
        selected, _filter = QFileDialog.getOpenFileName(self, "Insert image", "", "PNG or JPEG (*.png *.jpg *.jpeg)")
        return import_image(self._data_dir, company_id, Path(selected)) if selected else None

    def _on_loaded(self, page: EditorWebPage, ok: bool) -> None:
        if page is not self._page or self._session is None:
            return
        if ok:
            self._status.hide()
        elif not self._status.isHidden():
            self.close_session()
            self._status.setText("The local editor could not be opened. Reopen Document Editor to try again.")

    def _on_terminated(self, page: EditorWebPage) -> None:
        if page is self._page and self._session is not None:
            self.close_session()
            self._status.setText("The editor closed unexpectedly. Reopen Document Editor to try again.")
            self._status.show()
