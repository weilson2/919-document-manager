import base64
import re
from collections.abc import Callable
from html import escape

from document_manager.editor.visual_schema import FieldDocument, VisualNode
from document_manager.services.errors import BusinessError

PRINT_CSS = """
html { font-family: "Segoe UI", "Microsoft YaHei UI", "Noto Sans CJK SC", Arial, sans-serif;
       font-size: 11pt; line-height: 1.45; color: #152740; }
body { margin: 0; }
p, h1, h2, h3 { margin: 0 0 8pt; overflow-wrap: anywhere; white-space: pre-wrap; }
p:empty::after, td:empty::after, th:empty::after { content: '\\a0'; }
h1, h2, h3 { break-after: avoid; line-height: 1.25; }
h1 { font-size: 23pt; } h2 { font-size: 17pt; } h3 { font-size: 13pt; }
ul, ol { margin: 0 0 8pt; padding-inline-start: 22pt; }
table { width: 100%; table-layout: fixed; border-collapse: collapse; margin-bottom: 8pt; }
table.grid td, table.grid th { border: 0.6pt solid #9aacc1; }
td, th { padding: 5pt 6pt; vertical-align: top; overflow-wrap: anywhere; }
td p, th p { margin-bottom: 2pt; }
th { background: #edf2f8; }
tr { break-inside: avoid; }
figure { margin: 0 0 8pt; break-inside: avoid; }
img { display: block; height: auto; max-width: 100%; object-fit: contain; object-position: left; }
.page-break { break-after: page; }
.draft-banner { border: 1px solid #a15c07; color: #7c4300; padding: 6pt; margin-bottom: 10pt; font-weight: 700; }
.company-logo img { max-width: 42mm; max-height: 20mm; }
"""

TAGS = {
    "doc": "main", "paragraph": "p", "bulletList": "ul", "orderedList": "ol", "listItem": "li",
    "table": "table", "tableRow": "tr", "tableCell": "td", "tableHeader": "th",
}
MARKS = {"bold": "strong", "italic": "em", "underline": "u", "textStyle": "span"}


def css_string(value: str) -> str:
    # Encode characters that may end a CSS value or the HTML style element.
    return '"' + re.sub(r'[\x00-\x1f"\\<>]', lambda part: f"\\{ord(part[0]):x} ", value) + '"'


def styles(attributes: dict, accepted: dict[str, tuple[str, str]]) -> str:
    value = ";".join(
        f"{property_name}:{attributes[key]}{unit}"
        for key, (property_name, unit) in accepted.items() if attributes.get(key) is not None
    )
    return f' style="{escape(value, quote=True)}"' if value else ""


def print_html(
    design: FieldDocument, values: dict[str, str], load_image: Callable[[str], bytes], *,
    inputs=None, draft=False, logo: bytes | None = None,
) -> str:
    paper = design.page_settings
    print_settings = design.print_settings
    margins = (paper.margin_top, paper.margin_right, paper.margin_bottom, paper.margin_left)
    if print_settings.header and margins[0] < 8 or (print_settings.footer or print_settings.page_numbers) and margins[2] < 8:
        raise BusinessError("Use at least 8 mm of margin for headers, footers, or page numbers.")

    short, long = (210, 297) if paper.page_size == "A4" else (148, 210)
    height = long if paper.orientation == "portrait" else short
    rules = f"size:{paper.page_size} {paper.orientation};margin:{' '.join(f'{m}mm' for m in margins)};"
    for position, value in (("top-center", print_settings.header), ("bottom-center", print_settings.footer)):
        if value:
            rules += f"@{position}{{content:{css_string(value)};font-size:9pt;white-space:normal;}}"
    if print_settings.page_numbers:
        rules += "@bottom-right{content:counter(page);font-size:9pt;}"

    images = {}
    remaining = 72_000_000

    def within_budget(text: str) -> str:
        nonlocal remaining
        remaining -= len(text.encode("utf-8"))
        if remaining < 0:
            raise BusinessError("The print layout is too large. Reduce image size or split the document.")
        return text

    def render(node: VisualNode) -> str:
        kind, attrs = node.type, node.attrs
        if (field_id := attrs.get("showWhenFieldId")) is not None and not (inputs or {}).get(field_id):
            return ""
        if kind in {"text", "field"}:
            text = escape(node.text if kind == "text" else values[attrs["fieldId"]])
            for mark in node.marks:
                tag = MARKS[mark.type]
                detail = styles(mark.attrs, {"fontFamily": ("font-family", ""), "fontSize": ("font-size", "pt"),
                                            "color": ("color", "")})
                text = f"<{tag}{detail}>{text}</{tag}>"
            return within_budget(text)
        if kind == "image":
            asset = attrs["assetId"]
            if asset not in images:
                content = load_image(asset)
                images[asset] = base64.b64encode(content).decode("ascii")
            return within_budget(
                f'<figure><img src="data:image/png;base64,{images[asset]}"'
                f' alt="{escape(attrs.get("alt", ""), quote=True)}" style="width:{attrs.get("width", 70)}%"></figure>',
            )
        if kind == "pageBreak":
            return '<div class="page-break"></div>'

        tag = f'h{attrs["level"]}' if kind == "heading" else TAGS[kind]
        attributes = styles(attrs, {"textAlign": ("text-align", ""), "lineSpacing": ("line-height", ""),
                                    "spaceAfter": ("margin-bottom", "pt"), "align": ("text-align", "")})
        content = "".join(render(child) for child in node.content)
        if kind == "table":
            attributes += f' class="{attrs.get("borderStyle", "grid")}"'
            content = f"<tbody>{content}</tbody>"
        if kind in {"tableCell", "tableHeader"}:
            for span in ("colspan", "rowspan"):
                if span in attrs:
                    attributes += f' {span}="{attrs[span]}"'
        if kind == "orderedList":
            attributes += f' start="{attrs.get("start", 1)}"'
            if attrs.get("type"):
                attributes += f' type="{attrs["type"]}"'
        return f"<{tag}{attributes}>{content}</{tag}>"

    csp = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    banner = '<aside class="draft-banner">DRAFT · Statutory payroll has not been verified</aside>' if draft else ""
    company_logo = ""
    if print_settings.company_logo and logo:
        encoded = base64.b64encode(logo).decode("ascii")
        company_logo = f'<figure class="company-logo"><img src="data:image/png;base64,{encoded}" alt="Company logo"></figure>'
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
            f'<style>{PRINT_CSS} @page {{{rules}}}'
            f' img {{max-height:{height - margins[0] - margins[2] - 4}mm}}</style></head>'
            f'<body>{banner}{company_logo}{render(design.document)}</body></html>')
