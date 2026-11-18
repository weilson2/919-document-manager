import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from document_manager.services.backup import BackupService
from document_manager.ui.widgets import HANDLED_ERRORS, error_text, plain_label

FILTER = "919 encrypted backup (*.919backup)"


class BackupPage(QWidget):
    def __init__(self, workspace):
        super().__init__()
        self._service = BackupService(workspace) if workspace is not None else None
        self._restored_path = None
        self._status = plain_label()
        self._status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(plain_label(
            "Back up the workspace database, template images, saved PDFs, and accounts. "
            "Use a separate backup password. Restore opens a copy in a new workspace folder.",
        ))
        for caption, action in (
            ("Create encrypted backup", self._create), ("Verify backup file", self._verify),
            ("Restore to a new workspace", self._restore),
        ):
            button = QPushButton(caption)
            button.setEnabled(self._service is not None)
            button.clicked.connect(action)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        self._open_button = QPushButton("Open restored workspace")
        self._open_button.clicked.connect(self._open_restored)
        self._open_button.hide()
        layout.addWidget(self._open_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._status)
        layout.addStretch()

    def _create(self):
        picker = QFileDialog(self, "Save encrypted backup")
        picker.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        picker.setNameFilter(FILTER)
        picker.setDefaultSuffix("919backup")
        picker.selectFile(f"919-backup-{date.today()}.919backup")
        filename = picker.selectedFiles()[0] if picker.exec() else None
        picker.deleteLater()
        if filename and (password := self._password(confirm=True)) is not None:
            self._run("Create backup", lambda: self._service.create(Path(filename), password), "Encrypted backup saved.")

    def _verify(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Verify encrypted backup", "", FILTER)
        if filename and (password := self._password()) is not None:
            self._run("Verify backup", lambda: self._service.verify(Path(filename), password), "Backup integrity verified.")

    def _restore(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select encrypted backup", "", FILTER)
        if not filename:
            return
        parent = QFileDialog.getExistingDirectory(self, "Choose the parent folder for the restored workspace")
        if not parent:
            return
        name, accepted = QInputDialog.getText(self, "New workspace folder", "Folder name",
                                              text=f"919-restored-{date.today()}")
        name = name.strip()
        if not accepted:
            return
        if not name or name in {".", ".."} or any(char in name for char in '<>:"/\x5c|?*') or name.endswith("."):
            self._status.setText("Enter a simple folder name.")
            return
        destination = Path(parent) / name
        question = QMessageBox(self)
        question.setWindowTitle("Confirm restore")
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setText(f"Restore a verified copy into this new folder?\n\n{destination}")
        question.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if (
            question.exec() == QMessageBox.StandardButton.Yes
            and (password := self._password()) is not None
            and self._run("Restore backup", lambda: self._service.restore(Path(filename), password, destination),
                          f"Workspace restored to {destination}.")
        ):
            self._restored_path = destination
            self._open_button.show()

    def _open_restored(self):
        args = [] if getattr(sys, "frozen", False) else ["-m", "document_manager"]
        started, _process = QProcess.startDetached(sys.executable, [*args, "--data-dir", str(self._restored_path)])
        if not started:
            self._status.setText(f"Reopen the application with --data-dir \"{self._restored_path}\".")

    def _password(self, *, confirm=False):
        password, accepted = QInputDialog.getText(self, "Backup password", "Backup password",
                                                  QLineEdit.EchoMode.Password)
        if not accepted:
            return None
        if confirm:
            again, accepted = QInputDialog.getText(self, "Confirm backup password", "Repeat password",
                                                   QLineEdit.EchoMode.Password)
            if not accepted or again != password:
                self._status.setText("The backup passwords did not match.")
                return None
        return password

    def _run(self, action, callback, success):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            callback()
            self._status.setText(success)
            return True
        except (*HANDLED_ERRORS, OSError) as error:
            self._status.setText(error_text(error, action))
            return False
        finally:
            QApplication.restoreOverrideCursor()
