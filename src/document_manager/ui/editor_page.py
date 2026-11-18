import logging
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout, QWidget

from document_manager.editor.bridge import EditorBridge, EditorSession
from document_manager.editor.images import import_image, load_image
from document_manager.editor.visual_schema import PageSettings
from document_manager.editor.web import (
    ENTRY_URL,
    SCHEME,
    EditorImages,
    EditorRequestPolicy,
    EditorResources,
    EditorWebPage,
)
from document_manager.services.designs import DesignService
from document_manager.ui.widgets import HANDLED_ERRORS, error_text, plain_label

logger = logging.getLogger(__name__)


class DocumentEditor(QWidget):
    def __init__(self, data_dir: Path | None, designs: DesignService):
        super().__init__()
        self._data_dir = data_dir
        self._designs = designs
        self._template_id = None
        self._design_title = plain_label()
        self._design_title.hide()
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
        self._layout.addWidget(self._design_title)
        self._layout.addWidget(self._status)

    def set_company(self, company_id: int, page_settings: PageSettings) -> None:
        self._page_settings = page_settings
        if company_id != self._company_id:
            self.close_session()
            self._company_id = company_id
            self._template_id = None
            self._design_title.hide()
            if self.isVisible():
                self.activate()

    def open_template(self, template_id: int) -> bool:
        if not self.can_leave_session():
            return False
        self.close_session()
        self._template_id = template_id
        if self.isVisible():
            self.activate()
        return True

    def can_leave_session(self) -> bool:
        if self._session is None or not self._session.has_unsaved_changes:
            return True
        button = QMessageBox.question(
            self, "Leave template design", "There are unsaved template changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        return button == QMessageBox.StandardButton.Discard

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
        design = None
        company_id, template_id = self._company_id, self._template_id
        if template_id is not None:
            try:
                design = self._designs.open(company_id, template_id)
            except HANDLED_ERRORS as error:
                self._design_title.hide()
                self._status.setText(error_text(error, "Open template design"))
                self._status.show()
                return
        self._design_title.setText(design.name if design is not None else "")
        self._design_title.setVisible(design is not None)
        self._status.setText("Opening the local editor…")
        self._status.show()
        previous = self._page
        page = self._view.page() if previous is None else EditorWebPage(self._profile, self._view)
        self._page = page
        self._session = EditorSession(
            company_id, self._page_settings, lambda: self._choose_image(company_id), self._images.add,
            design=(design.revision, design.document) if design is not None else None,
            load_asset=lambda asset_id: self._load_asset(company_id, asset_id),
            save_design=lambda revision, value, publish: self._designs.save(
                company_id, template_id, revision, value, publish=publish,
            ),
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

    def _load_asset(self, company_id: int, asset_id: str):
        if self._data_dir is None:
            raise OSError("The editor workspace is unavailable.")
        return load_image(self._data_dir, company_id, asset_id)

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
