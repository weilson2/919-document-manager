import json
import os
import re
import secrets
import sqlite3
from contextlib import closing
from hashlib import scrypt, sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PySide6.QtCore import QIODevice, QSaveFile

from document_manager.editor.images import load_image
from document_manager.persistence.database import (
    create_database_engine,
    upgrade_database,
)
from document_manager.services.designs import checked_document
from document_manager.services.errors import BusinessError

DATABASE_NAME = "document-manager.sqlite3"
MANIFEST = "manifest.json"
MAGIC = b"919DOCUMENT-BACKUP\x01"
LIMIT = 256 * 1024 * 1024
ASSET_PATH = re.compile(r"editor-assets/([1-9][0-9]*)/([a-f0-9]{64})\.png")


def encryption_key(password, salt):
    return scrypt(password.encode("utf-8"), salt=salt, n=2**17, r=8, p=1, dklen=32, maxmem=160 * 1024 * 1024)


class BackupService:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def create(self, destination: Path, password: str) -> None:
        if not 12 <= len(password) <= 128:
            raise BusinessError("Use a backup password of 12–128 characters.")
        if destination.resolve().is_relative_to(self.workspace):
            raise BusinessError("Select a backup destination outside the active workspace.")
        data = BytesIO()
        with TemporaryDirectory(prefix="backup-", dir=self.workspace) as work:
            snapshot = Path(work) / DATABASE_NAME
            database = self.workspace / DATABASE_NAME
            with (
                closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source,
                closing(sqlite3.connect(snapshot)) as target,
            ):
                source.backup(target)
            assets = self._verify_database(snapshot)
            size = snapshot.stat().st_size
            if size > LIMIT:
                raise BusinessError("The workspace exceeds the 256 MB backup limit.")
            with ZipFile(data, mode="w", compression=ZIP_DEFLATED) as archive:
                content = snapshot.read_bytes()
                hashes = {DATABASE_NAME: sha256(content).hexdigest()}
                archive.writestr(DATABASE_NAME, content)
                for company_id, asset_id in sorted(assets):
                    image = load_image(self.workspace, company_id, asset_id).content
                    size += len(image)
                    if size > LIMIT:
                        raise BusinessError("The workspace exceeds the 256 MB backup limit.")
                    name = f"editor-assets/{company_id}/{asset_id}.png"
                    hashes[name] = asset_id
                    archive.writestr(name, image)
                archive.writestr(MANIFEST, json.dumps({"version": 1, "files": hashes}, sort_keys=True))

        salt, nonce = secrets.token_bytes(32), secrets.token_bytes(12)
        header = MAGIC + salt + nonce
        ciphertext = AESGCM(encryption_key(password, salt)).encrypt(nonce, data.getvalue(), header)
        file = QSaveFile(str(destination))
        if not file.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError("Could not open the backup destination.")
        if file.write(header) != len(header) or file.write(ciphertext) != len(ciphertext) or not file.commit():
            file.cancelWriting()
            raise OSError("Could not save the encrypted backup.")

    def verify(self, backup: Path, password: str) -> None:
        with TemporaryDirectory() as work:
            self._extract(backup, password, Path(work))

    def restore(self, backup: Path, password: str, destination: Path) -> None:
        dest = destination.resolve()
        if dest.exists() or dest.is_relative_to(self.workspace) or not dest.parent.is_dir():
            raise BusinessError("Choose a new workspace folder outside the current workspace.")
        with TemporaryDirectory(prefix="restore-", dir=dest.parent) as work:
            candidate = Path(work) / "workspace"
            candidate.mkdir()
            self._extract(backup, password, candidate)
            engine = create_database_engine(candidate / DATABASE_NAME)
            try:
                upgrade_database(engine)
            finally:
                engine.dispose()
            self._verify_database(candidate / DATABASE_NAME)
            if dest.exists():
                raise BusinessError("The restore destination already exists.")
            os.rename(candidate, dest)

    def _extract(self, backup, password, workspace) -> None:
        if not 12 <= len(password) <= 128:
            raise BusinessError("The backup password is incorrect.")
        header_length = len(MAGIC) + 44
        with backup.open("rb") as stream:
            encrypted = stream.read(LIMIT + 4 * 1024 * 1024 + 1)
        if not encrypted.startswith(MAGIC) or len(encrypted) > LIMIT + 4 * 1024 * 1024:
            raise BusinessError("This file is not a supported 919 Document Manager backup.")
        header = encrypted[:header_length]
        salt, nonce = header[len(MAGIC):-12], header[-12:]
        if len(salt) != 32:
            raise BusinessError("The backup file is incomplete.")
        try:
            plaintext = AESGCM(encryption_key(password, salt)).decrypt(nonce, encrypted[header_length:], header)
        except InvalidTag:
            raise BusinessError("The password is incorrect or the encrypted backup is damaged.") from None
        try:
            with ZipFile(BytesIO(plaintext)) as archive:
                entries = archive.infolist()
                names = {item.filename for item in entries}
                if (len(entries) != len(names) or DATABASE_NAME not in names or MANIFEST not in names
                        or sum(item.file_size for item in entries) > LIMIT + 2 * 1024 * 1024):
                    raise BusinessError("The backup archive is incomplete or too large.")
                manifest = json.loads(archive.read(MANIFEST))
                if manifest["version"] != 1 or manifest["files"].keys() != names - {MANIFEST}:
                    raise BusinessError("The backup manifest does not match its contents.")
                for name, expected in manifest["files"].items():
                    match = ASSET_PATH.fullmatch(name)
                    if name != DATABASE_NAME and (match is None or match[2] != expected):
                        raise BusinessError("The backup contains an invalid file name.")
                    data = archive.read(name)
                    if sha256(data).hexdigest() != expected:
                        raise BusinessError("A file in the backup failed its integrity check.")
                    output = workspace / name
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(data)
        except (BadZipFile, KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError):
            raise BusinessError("The backup archive is invalid.") from None

        assets = self._verify_database(workspace / DATABASE_NAME)
        if set(manifest["files"]) != {DATABASE_NAME} | {
            f"editor-assets/{company_id}/{asset_id}.png" for company_id, asset_id in assets
        }:
            raise BusinessError("The database refers to missing or unexpected image assets.")

    @staticmethod
    def _verify_database(database: Path) -> set[tuple[int, str]]:
        try:
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as session:
                if session.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or session.execute(
                    "PRAGMA foreign_key_check"
                ).fetchone() is not None:
                    raise BusinessError("The backup database failed its integrity checks.")
                assets = set()
                for table in ("template_drafts", "template_versions"):
                    for company_id, layout in session.execute(
                        f"SELECT company_id, document_json FROM {table} WHERE document_json IS NOT NULL",
                    ):
                        design = checked_document(json.loads(layout))
                        assets.update((company_id, asset_id) for asset_id in design.image_ids())
                for pdf, expected in session.execute("SELECT pdf, checksum FROM generated_documents"):
                    if sha256(pdf).hexdigest() != expected:
                        raise BusinessError("A saved PDF failed its integrity check.")
                return assets
        except sqlite3.DatabaseError as error:
            raise BusinessError("The workspace database is invalid or incompatible.") from error
