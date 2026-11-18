from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

VersionOne = Annotated[int, Field(strict=True, ge=1, le=1)]
MAX_REQUEST_BYTES = 1_048_576


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TextNode(StrictModel):
    type: Literal["text"]
    text: Annotated[str, Field(min_length=1, max_length=8192)]


class ParagraphNode(StrictModel):
    type: Literal["paragraph"]
    # ProseMirror omits content on empty paragraphs and merges adjacent plain text.
    content: list[TextNode] = Field(default_factory=list, min_length=1, max_length=1)


class DocumentNode(StrictModel):
    type: Literal["doc"]
    content: Annotated[list[ParagraphNode], Field(min_length=1, max_length=256)]


class EditorDocument(StrictModel):
    schema_version: VersionOne
    document: DocumentNode


def blank_document() -> EditorDocument:
    return EditorDocument(
        schema_version=1,
        document=DocumentNode(type="doc", content=[ParagraphNode(type="paragraph")]),
    )
