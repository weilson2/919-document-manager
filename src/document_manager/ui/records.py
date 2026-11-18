from datetime import UTC

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from document_manager.services.business import BusinessService, RecordKind
from document_manager.services.validation import (
    RECORD_STATUSES,
    RENTAL_TYPES,
    SALARY_TYPES,
    TEMPLATE_STATUSES,
)
from document_manager.ui.record_forms import RecordDialog, record_dialog
from document_manager.ui.widgets import (
    HANDLED_ERRORS,
    ComboBox,
    FormField,
    error_text,
    plain_label,
)

HEADERS = {
    "tenant": ("Name", "Stall", "Rental type", "Rent (MYR)", "Status"),
    "employee": ("Name", "Employee no.", "Position", "Basic salary (MYR)", "Status"),
    "template": ("Template", "Category", "Status"),
}


class RecordsPage(QWidget):
    changed = Signal()
    design_requested = Signal(int)
    fill_requested = Signal(int)

    def __init__(self, service: BusinessService, kind: RecordKind):
        super().__init__()
        self.service = service
        self.kind = kind
        self.company_id = None
        self.rows = []
        self.categories = {}
        self.gallery = None

        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search {'employees' if kind == 'employee' else kind + 's'}")
        self.search.setAccessibleName(self.search.placeholderText())
        self.status_filter = ComboBox()
        self.status_filter.setAccessibleName("Status filter")
        self.status_filter.addItem("All statuses")
        for value, label in (TEMPLATE_STATUSES if kind == "template" else RECORD_STATUSES).items():
            self.status_filter.addItem(label, value)
        self.type_filter = ComboBox()
        self.type_filter.setAccessibleName("Category filter" if kind == "template" else "Type filter")
        self._load_type_filter()
        self.archive_filter = QCheckBox("Archived")
        self.status = plain_label()

        self.table = QTableWidget(0, len(HEADERS[kind]))
        self.table.setHorizontalHeaderLabels(HEADERS[kind])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self.new_button = QPushButton(f"New {kind}")
        self.new_button.clicked.connect(self.new_record)
        self.edit_button = QPushButton("Rename or categorize" if kind == "template" else "Edit")
        self.edit_button.clicked.connect(self.edit_record)
        self.archive_button = QPushButton("Archive")
        self.archive_button.clicked.connect(self.change_archive)
        actions = QHBoxLayout()
        actions.addWidget(self.new_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.archive_button)
        design_actions = QHBoxLayout()
        if kind == "template":
            self.fill_button = QPushButton("Create document")
            self.fill_button.clicked.connect(self.use_template)
            self.design_button = QPushButton("Edit design")
            self.design_button.clicked.connect(self.edit_design)
            self.duplicate_button = QPushButton("Duplicate")
            self.duplicate_button.clicked.connect(self.duplicate)
            self.publish_button = QPushButton("Publish metadata")
            self.publish_button.clicked.connect(self.publish)
            self.category_button = QPushButton("New category")
            self.category_button.clicked.connect(self.new_category)
            self.versions_button = QPushButton("Versions")
            self.versions_button.clicked.connect(self._view_versions)
            actions.addWidget(self.duplicate_button)
            self.publish_button.hide()
            for button in (self.fill_button, self.design_button, self.versions_button, self.category_button):
                design_actions.addWidget(button)
            design_actions.addStretch()
        actions.addStretch()

        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.type_filter)
        filters.addWidget(self.archive_filter)
        if kind == "template":
            list_view = QCheckBox("List view")
            list_view.toggled.connect(self._toggle_gallery)
            filters.addWidget(list_view)
            self.gallery = QListWidget()
            self.gallery.setObjectName("templateGallery")
            self.gallery.setAccessibleName("Template gallery")
            self.gallery.setViewMode(QListView.ViewMode.IconMode)
            self.gallery.setResizeMode(QListView.ResizeMode.Adjust)
            self.gallery.setMovement(QListView.Movement.Static)
            self.gallery.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.gallery.setSpacing(8)
            self.gallery.currentRowChanged.connect(self._select_card)
            self.gallery.itemDoubleClicked.connect(lambda _item: self.edit_design())
            self.table.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(actions)
        if self.gallery is not None:
            layout.addLayout(design_actions)
        layout.addLayout(filters)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        if self.gallery is not None:
            layout.addWidget(self.gallery, 1)

        self.search.textChanged.connect(self.refresh)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        self.archive_filter.toggled.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.cellDoubleClicked.connect(self.edit_record)
        self._update_actions()

    def _load_type_filter(self, previous=None) -> None:
        options = {"tenant": RENTAL_TYPES, "employee": SALARY_TYPES, "template": self.categories}[self.kind]
        signals = self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem("All categories" if self.kind == "template" else "All types")
        for value, label in options.items():
            self.type_filter.addItem(label, value)
        self.type_filter.setCurrentIndex(max(0, self.type_filter.findData(previous)))
        self.type_filter.blockSignals(signals)

    def set_company(self, company_id: int) -> None:
        self.company_id = None
        if self.kind == "template":
            self.categories = {}
            self._load_type_filter()
        self.search.clear()
        self.status_filter.setCurrentIndex(0)
        self.archive_filter.setChecked(False)
        self.type_filter.setCurrentIndex(0)
        self.company_id = company_id
        self.refresh()

    def refresh(self) -> bool:
        if self.company_id is None:
            return False
        self.table.clearSelection()
        self.table.setRowCount(0)
        if self.gallery is not None:
            self.gallery.clear()
        self.rows = []
        try:
            if self.kind == "template":
                self.categories = {row.id: row.name for row in self.service.list_categories(self.company_id)}
                self._load_type_filter(self.type_filter.currentData())
            selection = self.type_filter.currentData()
            self.rows = self.service.list_records(
                self.kind, self.company_id, search=self.search.text(), archived=self.archive_filter.isChecked(),
                status=self.status_filter.currentData(),
                category_id=selection if self.kind == "template" else None,
                record_type=selection if self.kind != "template" else None,
            )
        except HANDLED_ERRORS as error:
            self.status.setText(error_text(error, "Load records"))
            self._update_actions()
            return False

        self.table.setRowCount(len(self.rows))
        for index, record in enumerate(self.rows):
            for column, value in enumerate(self._columns(record)):
                self.table.setItem(index, column, QTableWidgetItem(value))
            if self.gallery is not None:
                self._add_card(record)
        if self.rows:
            self.status.clear()
        elif self.archive_filter.isChecked():
            self.status.setText("No archived records match this view.")
        elif self.search.text() or self.status_filter.currentData() or self.type_filter.currentData():
            self.status.setText("No records match these filters.")
        else:
            self.status.setText(f"No records yet. Select New {self.kind} to add one.")
        self._update_actions()
        return True

    def _columns(self, record):
        if self.kind == "tenant":
            return (
                record.name, record.stall_number, RENTAL_TYPES[record.rental_type],
                f"{record.rental_amount:,.2f}", RECORD_STATUSES[record.status],
            )
        if self.kind == "employee":
            return (
                record.name, record.employee_number, record.position,
                f"{record.basic_salary:,.2f}", RECORD_STATUSES[record.status],
            )
        return record.name, self.categories.get(record.category_id, "—"), TEMPLATE_STATUSES[record.status]

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        return self.rows[rows[0].row()] if rows else None

    def _update_actions(self) -> None:
        record = self._selected()
        archived = self.archive_filter.isChecked()
        self.new_button.setEnabled(self.company_id is not None and not archived)
        self.edit_button.setEnabled(record is not None and not archived)
        self.archive_button.setEnabled(record is not None)
        self.archive_button.setText("Restore" if archived else "Archive")
        if self.kind == "template":
            self.design_button.setEnabled(record is not None and not archived)
            self.fill_button.setEnabled(record is not None and not archived)
            self.duplicate_button.setEnabled(record is not None)
            self.publish_button.setEnabled(record is not None and not archived and record.status == "draft")
            self.category_button.setEnabled(self.company_id is not None)
            self.versions_button.setEnabled(record is not None)

    def _toggle_gallery(self, list_view):
        self.table.setVisible(list_view)
        self.gallery.setVisible(not list_view)
        selected = self.table.selectionModel().selectedRows()
        self.gallery.setCurrentRow(selected[0].row() if selected else -1)

    def _select_card(self, index):
        if index < 0:
            self.table.clearSelection()
        else:
            self.table.selectRow(index)

    def _add_card(self, record):
        category = self.categories.get(record.category_id, "Uncategorized")
        status = TEMPLATE_STATUSES[record.status]
        changed = record.updated_at.replace(tzinfo=UTC).astimezone().strftime("%d %b %Y %H:%M")
        item = QListWidgetItem(record.name)
        item.setSizeHint(QSize(236, 145))
        item.setToolTip(record.description or record.name)
        self.gallery.addItem(item)
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        card = QVBoxLayout(widget)
        card.setContentsMargins(14, 12, 14, 12)
        card.setSpacing(5)
        title = plain_label(record.name, object_name="sectionTitle")
        title.setMaximumHeight(38)
        card.addWidget(title)
        card.addWidget(plain_label(f"{category} · {status}"))
        description = record.description or "No description"
        details = plain_label(description[:105] + ("…" if len(description) > 105 else ""))
        details.setMaximumHeight(35)
        card.addWidget(details, 1)
        card.addWidget(plain_label(f"Modified {changed}"))
        self.gallery.setItemWidget(item, widget)

    def _view_versions(self):
        record = self._selected()
        if record is None:
            return
        try:
            rows = list(reversed(self.service.list_template_versions(self.company_id, record.id)))
        except HANDLED_ERRORS as error:
            self.status.setText(error_text(error, "Load versions"))
            return
        lines = []
        previous = None
        previous_name = None
        for version in rows:
            design = version.document_json
            name = version.metadata_snapshot["name"]
            timestamp = version.created_at.replace(tzinfo=UTC).astimezone().strftime("%d %b %Y %H:%M")
            line = f"Version {version.version_number} · {timestamp} · {name}"
            if design is None:
                note = "Metadata only"
            elif previous is None:
                note = f"Initial design · {len(design['fields'])} fields"
            else:
                old, new = ({field["key"] for field in data["fields"]} for data in (previous, design))
                changed = "Layout changed" if any(previous.get(key) != design.get(key) for key in (
                    "document", "print_settings", "page_settings",
                )) else "Same layout"
                note = f"{changed} · {len(new - old)} added fields · {len(old - new)} removed fields"
            if previous_name is not None and previous_name != name:
                note += " · Renamed"
            lines.append(f"{line}\n{note}")
            previous, previous_name = design, name
        dialog = QMessageBox(self)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle("Published template versions")
        dialog.setText(f"{len(rows)} published version(s) for {record.name}")
        if lines:
            dialog.setDetailedText("\n\n".join(reversed(lines)))
        dialog.exec()

    def new_record(self) -> None:
        if self.company_id is not None:
            self._edit(None)

    def edit_design(self) -> None:
        record = self._selected()
        if record is not None and record.archived_at is None:
            self.design_requested.emit(record.id)

    def use_template(self) -> None:
        record = self._selected()
        if record is not None and record.archived_at is None:
            self.fill_requested.emit(record.id)

    def edit_record(self, *_args) -> None:
        record = self._selected()
        if record is not None and record.archived_at is None:
            self._edit(record)

    def _edit(self, record) -> None:
        company_id = self.company_id
        record_id = None if record is None else record.id
        dialog = record_dialog(
            self, self.kind, self.categories, record,
            lambda payload: self.service.save_record(self.kind, company_id, payload, record_id),
        )
        self._run_dialog(dialog, f"{self.kind.title()} saved.")

    def new_category(self) -> None:
        company_id = self.company_id
        dialog = RecordDialog(
            self, "New template category", (FormField("name", "Category name"),), {},
            lambda values: self.service.create_category(company_id, values["name"]),
        )
        self._run_dialog(dialog, "Category created.")

    def _run_dialog(self, dialog, message: str) -> None:
        result = dialog.exec()
        dialog.deleteLater()
        if result == QDialog.DialogCode.Accepted:
            self._saved(message)

    def change_archive(self) -> None:
        record = self._selected()
        if record is not None:
            restore = self.archive_filter.isChecked()
            self._action(
                "Restore" if restore else "Archive",
                lambda: self.service.set_archived(self.kind, self.company_id, record.id, archived=not restore),
                "Record restored." if restore else "Record archived. Open the Archived filter to restore it.",
            )

    def duplicate(self) -> None:
        record = self._selected()
        if record is not None:
            self._action(
                "Duplicate", lambda: self.service.duplicate_template(self.company_id, record.id),
                "Template duplicated as a draft.",
            )

    def publish(self) -> None:
        record = self._selected()
        if record is not None:
            self._action(
                "Publish", lambda: self.service.publish_template(self.company_id, record.id),
                "Metadata version published. Layout authoring will be available in the visual editor.",
            )

    def _action(self, action, callback, message) -> None:
        try:
            callback()
        except HANDLED_ERRORS as error:
            self.status.setText(error_text(error, action))
            return
        self._saved(message)

    def _saved(self, message) -> None:
        if self.refresh():
            self.status.setText(message)
        self.changed.emit()
