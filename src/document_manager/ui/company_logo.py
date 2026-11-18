from pathlib import Path

from document_manager.raster import read_local_image
from document_manager.services.settings import MAX_LOGO_BYTES, MAX_LOGO_DIMENSION


def read_logo(path: Path) -> bytes:
    return read_local_image(path, max_bytes=MAX_LOGO_BYTES, max_dimension=MAX_LOGO_DIMENSION)
