from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from document_manager.ui.fill_document import export_document
from document_manager.ui.pdf_view import PdfPreview
from document_manager.ui.widgets import HANDLED_ERRORS, error_text, plain_label


class DocumentHistory(QWidget):
    reuse_requested = Signal(int)
    changed = Signal()

    def __init__(self, documents):
        super().__init__()
        self._documents = documents
        self.company_id = None
        self._rows = []
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by number, template or subject")
        self._archive = QCheckBox("Archived")
        self._status = plain_label()
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(("Number", "Document", "Subject", "Version", "Created (UTC)"))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        actions = QHBoxLayout()
        self._view = QPushButton("View PDF")
        self._reuse = QPushButton("Reuse values")
        self._export = QPushButton("Export PDF")
        self._toggle = QPushButton("Archive")
        for button, action in (
            (self._view, self._open), (self._reuse, self._reuse_document), (self._export, self._export_pdf),
            (self._toggle, self._change_archive),
        ):
            button.clicked.connect(action)
            actions.addWidget(button)
        actions.addStretch()

        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._archive)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(actions)
        layout.addLayout(filters)
        layout.addWidget(self._status)
        layout.addWidget(self._table, 1)
        self._search.textChanged.connect(self.refresh)
        self._archive.toggled.connect(self.refresh)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._table.cellDoubleClicked.connect(self._open)
        self._update_buttons()

    def refresh(self, *_args) -> None:
        if self.company_id is None:
            return
        try:
            self._rows = self._documents.list(
                self.company_id, self._search.text(), archived=self._archive.isChecked(),
            )
            self._status.setText("" if self._rows else "No matching saved documents.")
        except HANDLED_ERRORS as error:
            self._rows = []
            self._status.setText(error_text(error, "Load documents"))
        self._table.clearSelection()
        self._table.setRowCount(len(self._rows))
        for index, document in enumerate(self._rows):
            for column, value in enumerate((
                document.number, document.title, document.subject_name, str(document.version_number),
                document.created_at.strftime("%Y-%m-%d %H:%M"),
            )):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(index, column, item)
        self._update_buttons()

    def _selected(self):
        selected = self._table.selectionModel().selectedRows()
        return self._rows[selected[0].row()].id if selected else None

    def _update_buttons(self):
        for button in (self._view, self._reuse, self._export, self._toggle):
            button.setEnabled(self._selected() is not None)
        self._toggle.setText("Restore" if self._archive.isChecked() else "Archive")

    def _open(self, *_args):
        if (pk := self._selected()) is not None:
            try:
                document = self._documents.get(self.company_id, pk)
                preview = PdfPreview(document.pdf, self)
                preview.setWindowTitle(f"{document.number} · {document.title}")
                preview.exec()
                preview.deleteLater()
            except HANDLED_ERRORS as error:
                self._status.setText(error_text(error, "Open saved PDF"))

    def _reuse_document(self):
        if (pk := self._selected()) is not None:
            self.reuse_requested.emit(pk)

    def _export_pdf(self):
        if (pk := self._selected()) is not None:
            try:
                export_document(self._documents, self.company_id, pk, self)
            except (*HANDLED_ERRORS, OSError) as error:
                self._status.setText(error_text(error, "Export PDF"))

    def _change_archive(self):
        if (pk := self._selected()) is not None:
            try:
                self._documents.archive(self.company_id, pk, archived=not self._archive.isChecked())
                self.refresh()
                self.changed.emit()
            except HANDLED_ERRORS as error:
                self._status.setText(error_text(error, "Update document archive"))
