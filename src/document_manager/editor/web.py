from importlib.resources import files

from PySide6.QtCore import QBuffer, QFile, QIODevice, QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

from document_manager.editor.images import ImportedImage

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


class EditorImages:
    def __init__(self):
        self._images: dict[bytes, bytes] = {}
        self._size = 0

    def add(self, session_id: str, image: ImportedImage) -> None:
        url = ORIGIN + f"image/{session_id}/{image.asset_id}.png".encode("ascii")
        if url not in self._images:
            if self._size + len(image.content) > 48_000_000:
                raise OSError("The editor session has reached its image limit.")
            self._images[url] = image.content
            self._size += len(image.content)

    def get(self, url: QUrl, method: bytes) -> bytes | None:
        return self._images.get(bytes(url.toEncoded())) if method == b"GET" else None

    def clear(self) -> None:
        self._images.clear()
        self._size = 0


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
    def __init__(self, images, parent):
        super().__init__(parent)
        self._images = images
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
        url, method = job.requestUrl(), bytes(job.requestMethod())
        asset = allowed_asset(url, method)
        image = self._images.get(url, method) if asset is None else None
        if asset is None and image is None:
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
            return
        content = QBuffer(job)
        content.setData(self._content[asset] if asset is not None else image)
        content.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(ASSET_TYPES[asset] if asset is not None else b"image/png", content)


class EditorRequestPolicy(QWebEngineUrlRequestInterceptor):
    def __init__(self, images, parent):
        super().__init__(parent)
        self._images = images

    def interceptRequest(self, request) -> None:
        url, method = request.requestUrl(), bytes(request.requestMethod())
        if allowed_asset(url, method) is None and self._images.get(url, method) is None:
            request.block(True)


class EditorWebPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, _navigation_type, is_main_frame: bool) -> bool:
        return is_main_frame and bytes(url.toEncoded()) == ENTRY_URL

    def createWindow(self, _window_type):
        return None
