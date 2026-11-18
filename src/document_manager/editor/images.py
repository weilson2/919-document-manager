import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice, QSaveFile

from document_manager.raster import read_local_image

MAX_IMAGE_BYTES = 8_000_000
MAX_IMAGE_DIMENSION = 4096


@dataclass(frozen=True)
class ImportedImage:
    asset_id: str
    content: bytes


def load_image(workspace: Path, company_id: int, asset_id: str) -> ImportedImage:
    if re.fullmatch(r"[0-9a-f]{64}", asset_id) is None:
        raise ValueError("Invalid image identifier.")
    directory = workspace.resolve() / "editor-assets" / str(company_id)
    target = directory / f"{asset_id}.png"
    if target.resolve() != target:
        raise OSError("The image is outside the managed asset folder.")
    file = QFile(str(target))
    if not file.open(QIODevice.OpenModeFlag.ReadOnly):
        raise OSError("The managed image could not be opened.")
    try:
        content = bytes(file.read(MAX_IMAGE_BYTES + 1))
    finally:
        file.close()
    if len(content) > MAX_IMAGE_BYTES or sha256(content).hexdigest() != asset_id:
        raise OSError("The managed image is damaged.")
    return ImportedImage(asset_id, content)


def import_image(workspace: Path, company_id: int, user_selection: Path) -> ImportedImage:
    content = read_local_image(
        user_selection, max_bytes=MAX_IMAGE_BYTES, max_dimension=MAX_IMAGE_DIMENSION,
    )
    asset_id = sha256(content).hexdigest()
    workspace = workspace.resolve()
    directory = workspace / "editor-assets" / str(company_id)
    if not directory.resolve().is_relative_to(workspace):
        raise OSError("The editor asset folder is outside the workspace.")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{asset_id}.png"
    # Commit a complete file beside its destination, including when importing the same image twice.
    file = QSaveFile(str(target))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError("Could not open the managed image file.")
    if file.write(content) != len(content):
        file.cancelWriting()
        raise OSError("Could not write the managed image file.")
    if not file.commit():
        raise OSError("Could not commit the managed image file.")
    return ImportedImage(asset_id, content)
