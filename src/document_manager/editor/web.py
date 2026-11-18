from importlib.resources import files

from PySide6.QtCore import QBuffer, QFile, QIODevice, QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

SCHEME = b"document-manager-editor"
ORIGIN = SCHEME + b"://app/"
ENTRY_URL = ORIGIN + b"index.html"
ASSET_TYPES = {
    "index.html": b"text/html",
    "app.css": b"text/css",
    "app.js": b"application/javascript",
    "qwebchannel.js": b"application/javascript",
}
ALLOWED_URLS = {ORIGIN + name.encode("ascii"): name for name in ASSET_TYPES}


def register_editor_scheme() -> None:
    if QWebEngineUrlScheme.schemeByName(SCHEME).name():
        return
    scheme = QWebEngineUrlScheme(SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
    QWebEngineUrlScheme.registerScheme(scheme)


def allowed_asset(url: QUrl, method: bytes) -> str | None:
    if method != b"GET":
        return None
    return ALLOWED_URLS.get(bytes(url.toEncoded()))


class EditorResources(QWebEngineUrlSchemeHandler):
    def __init__(self, parent):
        super().__init__(parent)
        package = files("document_manager.editor").joinpath("assets")
        self._content = {
            name: package.joinpath(name).read_bytes()
            for name in ASSET_TYPES if name != "qwebchannel.js"
        }
        script = QFile(":/qtwebchannel/qwebchannel.js")
        if not script.open(QIODevice.OpenModeFlag.ReadOnly):
            raise OSError("Qt WebChannel script is unavailable.")
        self._content["qwebchannel.js"] = bytes(script.readAll())

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        asset = allowed_asset(job.requestUrl(), bytes(job.requestMethod()))
        if asset is None:
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
            return
        content = QBuffer(job)
        content.setData(self._content[asset])
        content.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(ASSET_TYPES[asset], content)


class EditorRequestPolicy(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, request) -> None:
        if allowed_asset(request.requestUrl(), bytes(request.requestMethod())) is None:
            request.block(True)


class EditorWebPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, _navigation_type, is_main_frame: bool) -> bool:
        return is_main_frame and bytes(url.toEncoded()) == ENTRY_URL

    def createWindow(self, _window_type):
        return None
