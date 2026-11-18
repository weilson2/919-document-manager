from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

from document_manager.services.errors import BusinessError
from document_manager.ui.widgets import (
    HANDLED_ERRORS,
    ComboBox,
    error_text,
    plain_label,
)


class LocalLogin(QDialog):
    def __init__(self, auth, parent=None, *, creating_user=None):
        super().__init__(parent)
        self._auth = auth
        self._actor = creating_user
        self._enrolling = creating_user is not None or auth.needs_owner()
        self.identity = None
        self.setWindowTitle("Create local account" if self._enrolling else "Sign in to 919 Document Manager")
        self.setMinimumWidth(390)
        self._username, self._password = QLineEdit(), QLineEdit()
        self._username.setMaxLength(60)
        self._password.setMaxLength(128)
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirmation = QLineEdit()
        self._confirmation.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirmation.setMaxLength(128)
        self._role = ComboBox()
        for label, value in (("Clerk", "clerk"), ("Payroll officer", "payroll"), ("Owner", "owner")):
            self._role.addItem(label, value)
        self._status = plain_label()
        form = QFormLayout()
        form.addRow("Username", self._username)
        form.addRow("Password", self._password)
        if self._enrolling:
            form.addRow("Confirm password", self._confirmation)
        if creating_user is not None:
            form.addRow("Access role", self._role)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create account" if self._enrolling else "Sign in")
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        if self._enrolling and creating_user is None:
            layout.addWidget(plain_label("Create the workspace owner account. Use a password of at least 12 characters."))
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addWidget(buttons)
        self._username.setFocus()

    def _submit(self):
        username, password = self._username.text(), self._password.text()
        try:
            if self._enrolling and self._confirmation.text() != password:
                raise BusinessError("The confirmation does not match the password.")
            if self._actor is not None:
                self.identity = self._auth.add_user(self._actor, username, password, self._role.currentData())
            elif self._enrolling:
                self.identity = self._auth.enroll_owner(username, password)
            else:
                self.identity = self._auth.authenticate(username, password)
                if self.identity is None:
                    raise BusinessError("The username or password is incorrect.")
        except HANDLED_ERRORS as error:
            self._status.setText(error_text(error, "Sign in"))
            self._password.clear()
            self._confirmation.clear()
            self._password.setFocus()
            return
        self._password.clear()
        self._confirmation.clear()
        self.accept()
