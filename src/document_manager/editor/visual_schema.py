from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, model_validator

from document_manager.editor.schema import StrictModel
from document_manager.services.settings import DocumentSettings

VersionTwo = Annotated[int, Field(strict=True, ge=2, le=2)]
AssetId = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FontFamily = Literal["Arial", "Calibri", "Georgia", "Segoe UI", "Times New Roman", "Verdana", "Courier New"]


class PageSettings(DocumentSettings):
    model_config = ConfigDict(strict=True, extra="forbid")


class ParagraphStyle(StrictModel):
    textAlign: Literal["left", "center", "right", "justify"] | None = None
    lineSpacing: Literal["1", "1.15", "1.5", "2"] | None = None
    spaceAfter: Annotated[int, Field(ge=0, le=48)] | None = None


class HeadingStyle(ParagraphStyle):
    level: Annotated[int, Field(ge=1, le=3)]


class OrderedStyle(StrictModel):
    start: Annotated[int, Field(ge=1, le=1_000_000)] = 1
    type: Literal["1", "a", "A", "i", "I"] | None = None


class TableStyle(StrictModel):
    borderStyle: Literal["grid", "none"] = "grid"


class CellStyle(StrictModel):
    colspan: Annotated[int, Field(ge=1, le=100)] = 1
    rowspan: Annotated[int, Field(ge=1, le=100)] = 1
    colwidth: list[Annotated[int, Field(ge=1, le=2400)]] | None = Field(default=None, max_length=100)
    align: Literal["left", "center", "right", "justify"] | None = None


class ImageStyle(StrictModel):
    assetId: AssetId
    alt: Annotated[str, Field(max_length=300)] = ""
    width: Annotated[int, Field(ge=10, le=100)] = 70


class TextStyle(StrictModel):
    fontFamily: FontFamily | None = None
    fontSize: Annotated[int, Field(ge=8, le=72)] | None = None
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None


class VisualMark(StrictModel):
    type: Literal["bold", "italic", "underline", "textStyle"]
    attrs: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_style(self):
        if self.type == "textStyle":
            TextStyle.model_validate(self.attrs)
        elif self.attrs:
            raise ValueError("This mark does not accept attributes.")
        return self


Block = Literal["paragraph", "heading", "bulletList", "orderedList", "table", "image"]
BLOCKS = frozenset({"paragraph", "heading", "bulletList", "orderedList", "table", "image"})
NODE_ATTRS = {
    "paragraph": ParagraphStyle, "heading": HeadingStyle, "orderedList": OrderedStyle,
    "table": TableStyle, "tableCell": CellStyle, "tableHeader": CellStyle, "image": ImageStyle,
}
NODE_CHILDREN = {
    "doc": BLOCKS, "paragraph": {"text"}, "heading": {"text"}, "bulletList": {"listItem"},
    "orderedList": {"listItem"}, "listItem": BLOCKS, "table": {"tableRow"},
    "tableRow": {"tableCell", "tableHeader"}, "tableCell": BLOCKS, "tableHeader": BLOCKS,
}
REQUIRED_CONTENT = frozenset({
    "doc", "bulletList", "orderedList", "listItem", "table", "tableRow", "tableCell", "tableHeader",
})


class VisualNode(StrictModel):
    type: Literal["doc", "text", "listItem", "tableRow", "tableCell", "tableHeader"] | Block
    attrs: dict[str, JsonValue] = Field(default_factory=dict)
    content: list["VisualNode"] = Field(default_factory=list, max_length=2500)
    text: Annotated[str, Field(min_length=1, max_length=65_536)] | None = None
    marks: list[VisualMark] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_node(self):
        attributes = NODE_ATTRS.get(self.type)
        if attributes is not None:
            attributes.model_validate(self.attrs)
        elif self.attrs:
            raise ValueError("Unexpected node attributes.")
        if self.type == "text":
            if self.text is None or self.content or len({mark.type for mark in self.marks}) != len(self.marks):
                raise ValueError("Invalid text node.")
        elif "text" in self.model_fields_set or "marks" in self.model_fields_set:
            raise ValueError("Only text nodes may contain text or marks.")
        children = NODE_CHILDREN.get(self.type, set())
        if any(child.type not in children for child in self.content):
            raise ValueError("Unexpected child node.")
        if self.type in REQUIRED_CONTENT and not self.content:
            raise ValueError("Missing child node.")
        if self.type == "listItem" and self.content[0].type != "paragraph":
            raise ValueError("A list item must begin with a paragraph.")
        return self


class VisualDocument(StrictModel):
    schema_version: VersionTwo
    document: VisualNode
    page_settings: PageSettings

    @model_validator(mode="after")
    def validate_tree(self):
        if self.document.type != "doc":
            raise ValueError("Expected the document root.")
        stack = [(self.document, 0)]
        count = 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if depth > 24 or count > 8000:
                raise ValueError("The document is too complex.")
            stack.extend((child, depth + 1) for child in node.content)
        return self

    def image_ids(self) -> set[str]:
        stack = [self.document]
        image_ids = set()
        while stack:
            node = stack.pop()
            if node.type == "image":
                image_ids.add(node.attrs["assetId"])
            stack.extend(node.content)
        return image_ids


def blank_visual_document(settings: PageSettings) -> VisualDocument:
    return VisualDocument(
        schema_version=2,
        document=VisualNode(type="doc", content=[VisualNode(type="paragraph")]),
        page_settings=settings,
    )
