from collections.abc import Callable
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, TypeAdapter, ValidationError
from PySide6.QtCore import QObject, Slot

from document_manager.editor.images import ImportedImage
from document_manager.editor.schema import (
    EditorDocument,
    StrictModel,
    VersionOne,
    blank_document,
)
from document_manager.editor.visual_schema import (
    AssetId,
    FieldDocument,
    PageSettings,
    VersionThree,
    VersionTwo,
    VisualDocument,
    blank_visual_document,
)

MAX_REQUEST_BYTES = 1_048_576
CompanyId = Annotated[int, Field(gt=0, le=9_007_199_254_740_991)]
SessionId = Annotated[str, Field(pattern="^[0-9a-f]{32}$")]


class OpenRequest(StrictModel):
    method: Literal["open"]
    protocol_version: VersionOne
    schema_version: VersionOne | VersionTwo | VersionThree = 1


class SessionRequest(StrictModel):
    protocol_version: VersionOne
    company_id: CompanyId
    session_id: SessionId


class VerifyRequest(SessionRequest):
    method: Literal["verify_document"]
    document: EditorDocument | VisualDocument | FieldDocument


class ImportImageRequest(SessionRequest):
    method: Literal["import_image"]


REQUEST = TypeAdapter(Annotated[OpenRequest | VerifyRequest | ImportImageRequest, Field(discriminator="method")])


class DocumentResponse(StrictModel):
    ok: Literal[True]
    protocol_version: VersionOne
    company_id: CompanyId
    session_id: SessionId
    document: EditorDocument | VisualDocument | FieldDocument


class ImageResponse(StrictModel):
    ok: Literal[True]
    protocol_version: VersionOne
    company_id: CompanyId
    session_id: SessionId
    asset_id: AssetId


class ErrorResponse(StrictModel):
    ok: Literal[False]
    protocol_version: VersionOne
    error: Literal[
        "invalid_request", "session_mismatch", "session_closed", "invalid_image", "image_cancelled", "image_unavailable",
    ]


def error_response(code) -> ErrorResponse:
    return ErrorResponse(ok=False, protocol_version=1, error=code)


class EditorSession:
    """Temporary company-bound session. Image import uses the desktop's file picker."""

    def __init__(
        self, company_id: int, page_settings: PageSettings | None = None,
        choose_image: Callable[[], ImportedImage | None] | None = None,
        expose_image: Callable[[str, ImportedImage], None] | None = None,
    ):
        self._company_id = company_id
        self._session_id = uuid4().hex
        self._page_settings = PageSettings.model_validate((page_settings or PageSettings()).model_dump())
        self._choose_image = choose_image
        self._expose_image = expose_image
        self._schema_version = None
        self._closed = False
        self._images = set()
        self._importing = False

    def close(self) -> None:
        self._closed = True

    def handle(self, raw: str) -> DocumentResponse | ImageResponse | ErrorResponse:
        if self._closed:
            return error_response("session_closed")
        try:
            if len(raw) > MAX_REQUEST_BYTES or len(raw.encode("utf-8")) > MAX_REQUEST_BYTES:
                return error_response("invalid_request")
            request = REQUEST.validate_json(raw)
        except (ValidationError, UnicodeError):
            return error_response("invalid_request")

        if isinstance(request, OpenRequest):
            if self._schema_version not in (None, request.schema_version):
                return error_response("session_mismatch")
            self._schema_version = request.schema_version
            document = (
                blank_document() if self._schema_version == 1
                else blank_visual_document(self._page_settings, self._schema_version)
            )
        else:
            if self._schema_version is None or request.company_id != self._company_id or request.session_id != self._session_id:
                return error_response("session_mismatch")
            if isinstance(request, ImportImageRequest):
                return self._import_image()
            document = request.document
            if document.schema_version != self._schema_version:
                return error_response("invalid_request")
            if isinstance(document, VisualDocument) and not document.image_ids() <= self._images:
                return error_response("invalid_image")
        return DocumentResponse(
            ok=True, protocol_version=1, company_id=self._company_id, session_id=self._session_id, document=document,
        )

    def _import_image(self) -> ImageResponse | ErrorResponse:
        if self._schema_version not in (2, 3):
            return error_response("invalid_request")
        if self._choose_image is None or self._expose_image is None or self._importing:
            return error_response("image_unavailable")
        self._importing = True
        try:
            image = self._choose_image()
            if self._closed:
                return error_response("session_closed")
            if image is None:
                return error_response("image_cancelled")
            self._expose_image(self._session_id, image)
        except ValueError:
            return error_response("invalid_image")
        except OSError:
            return error_response("image_unavailable")
        finally:
            self._importing = False
        self._images.add(image.asset_id)
        return ImageResponse(
            ok=True, protocol_version=1, company_id=self._company_id, session_id=self._session_id, asset_id=image.asset_id,
        )


class EditorBridge(QObject):
    """Only this slot is published by the desktop shell."""

    def __init__(self, session: EditorSession, parent: QObject):
        super().__init__(parent)
        self._session = session

    @Slot(str, result=str)
    def request(self, payload: str) -> str:
        return self._session.handle(payload).model_dump_json(exclude_unset=True)
