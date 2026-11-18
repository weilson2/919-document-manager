from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImageReader

from document_manager.services.settings import MAX_LOGO_BYTES, MAX_LOGO_DIMENSION


def read_logo(path: Path) -> bytes:
    with path.open("rb") as handle:
        content = handle.read(MAX_LOGO_BYTES + 1)
    if len(content) > MAX_LOGO_BYTES:
        raise ValueError("Choose an image file of up to 2 MB.")

    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        image_format = b"png"
    elif content.startswith(b"\xff\xd8\xff"):
        image_format = b"jpeg"
    else:
        raise ValueError("Choose a PNG or JPEG image.")

    source = QBuffer()
    source.setData(QByteArray(content))
    source.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(source, image_format)
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.isEmpty():
        raise ValueError("The selected image could not be read.")
    if max(size.width(), size.height()) > MAX_LOGO_DIMENSION:
        raise ValueError("Use a logo no larger than 2048 × 2048 pixels.")
    image = reader.read()
    if image.isNull():
        raise ValueError("The selected image could not be read.")

    destination = QBuffer()
    destination.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(destination, "PNG") or destination.size() > MAX_LOGO_BYTES:
        raise ValueError("This image is too large to store as a PNG logo. Choose a smaller image.")
    return bytes(destination.data())
