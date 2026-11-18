from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, TypeAdapter, ValidationError
from PySide6.QtCore import QObject, Slot

from document_manager.editor.schema import (
    EditorDocument,
    StrictModel,
    VersionOne,
    blank_document,
)

MAX_REQUEST_BYTES = 1_048_576
CompanyId = Annotated[int, Field(gt=0, le=9_007_199_254_740_991)]
SessionId = Annotated[str, Field(pattern="^[0-9a-f]{32}$")]


class OpenRequest(StrictModel):
    method: Literal["open"]
    protocol_version: VersionOne


class VerifyRequest(StrictModel):
    method: Literal["verify_document"]
    protocol_version: VersionOne
    company_id: CompanyId
    session_id: SessionId
    document: EditorDocument


REQUEST = TypeAdapter(Annotated[OpenRequest | VerifyRequest, Field(discriminator="method")])


class DocumentResponse(StrictModel):
    ok: Literal[True]
    protocol_version: VersionOne
    company_id: CompanyId
    session_id: SessionId
    document: EditorDocument


class ErrorResponse(StrictModel):
    ok: Literal[False]
    protocol_version: VersionOne
    error: Literal["invalid_request", "session_mismatch", "session_closed"]


class EditorSession:
    """Temporary, company-bound session with no access to the database or filesystem."""

    def __init__(self, company_id: int):
        self._company_id = company_id
        self._session_id = uuid4().hex
        self._opened = False
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def handle(self, raw: str) -> DocumentResponse | ErrorResponse:
        if self._closed:
            return ErrorResponse(ok=False, protocol_version=1, error="session_closed")
        try:
            if len(raw) > MAX_REQUEST_BYTES or len(raw.encode("utf-8")) > MAX_REQUEST_BYTES:
                return ErrorResponse(ok=False, protocol_version=1, error="invalid_request")
            request = REQUEST.validate_json(raw)
        except (ValidationError, UnicodeError):
            return ErrorResponse(ok=False, protocol_version=1, error="invalid_request")

        if isinstance(request, OpenRequest):
            document = blank_document()
            self._opened = True
        else:
            if not self._opened or request.company_id != self._company_id or request.session_id != self._session_id:
                return ErrorResponse(ok=False, protocol_version=1, error="session_mismatch")
            document = request.document
        return DocumentResponse(
            ok=True, protocol_version=1, company_id=self._company_id, session_id=self._session_id, document=document,
        )


class EditorBridge(QObject):
    """Only this slot is published by the desktop shell."""

    def __init__(self, session: EditorSession, parent: QObject):
        super().__init__(parent)
        self._session = session

    @Slot(str, result=str)
    def request(self, payload: str) -> str:
        return self._session.handle(payload).model_dump_json(exclude_unset=True)
