from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImageReader


def read_local_image(path: Path, *, max_bytes: int, max_dimension: int) -> bytes:
    with path.open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"Choose an image file of up to {max_bytes / 1_000_000:g} MB.")

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
    if max(size.width(), size.height()) > max_dimension:
        raise ValueError(f"Use an image no larger than {max_dimension} × {max_dimension} pixels.")
    image = reader.read()
    if image.isNull():
        raise ValueError("The selected image could not be read.")

    destination = QBuffer()
    destination.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(destination, "PNG") or destination.size() > max_bytes:
        raise ValueError("This image is too large to store as PNG. Choose a smaller image.")
    return bytes(destination.data())
