import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from document_manager.persistence.database import write_session
from document_manager.persistence.models import LocalUser
from document_manager.services.errors import BusinessError

Role = Literal["owner", "payroll", "clerk"]


@dataclass(frozen=True)
class LocalIdentity:
    id: int
    username: str
    role: Role

    @property
    def sensitive_access(self):
        return self.role in {"owner", "payroll"}


def require_sensitive(identity: LocalIdentity | None) -> None:
    if identity is not None and not identity.sensitive_access:
        raise BusinessError("This action requires payroll or owner access.")


def password_hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**17, r=8, p=1, maxmem=160 * 1024 * 1024)


class AuthService:
    def __init__(self, engine):
        self._engine = engine

    def needs_owner(self):
        with Session(self._engine) as session:
            return session.scalar(select(LocalUser.id).limit(1)) is None

    def enroll_owner(self, username, password):
        return self._create(username, password, "owner", first=True)

    def add_user(self, actor: LocalIdentity, username: str, password: str, role: Role) -> LocalIdentity:
        if actor.role != "owner" or role not in {"owner", "payroll", "clerk"}:
            raise BusinessError("Only an owner can create local user accounts.")
        return self._create(username, password, role)

    def _create(self, username, password, role, *, first=False):
        username = username.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,59}", username):
            raise BusinessError("Use a username of 3–60 letters, digits, dots, underscores or hyphens.")
        if not 12 <= len(password) <= 128:
            raise BusinessError("Use a password of 12–128 characters.")
        salt = secrets.token_bytes(32)
        digest = password_hash(password, salt)
        try:
            with write_session(self._engine) as session:
                if first and session.scalar(select(LocalUser.id).limit(1)) is not None:
                    raise BusinessError("The workspace already has a local account. Sign in instead.")
                user = LocalUser(username=username, password_hash=digest, password_salt=salt, role=role)
                session.add(user)
                session.flush()
                return self._identity(user)
        except IntegrityError:
            raise BusinessError("This username is already used.") from None

    def authenticate(self, username, password):
        if len(username) > 60 or len(password) > 128:
            return None
        with Session(self._engine) as session:
            user = session.scalar(select(LocalUser).where(LocalUser.username == username.strip().lower()))
            candidate = password_hash(password, user.password_salt if user else bytes(32))
            if user is not None and hmac.compare_digest(candidate, user.password_hash):
                return self._identity(user)
        return None

    @staticmethod
    def _identity(user):
        return LocalIdentity(user.id, user.username, user.role)
