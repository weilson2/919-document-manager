import type { JSONContent } from "@tiptap/core";
import { type FieldDefinition, fieldIdPattern, parseFields } from "./field_schema";

export type TextNode = { type: "text"; text: string };
export type Paragraph = { type: "paragraph"; content?: [TextNode] };
export type EditorDocument = {
  schema_version: 1;
  document: { type: "doc"; content: Paragraph[] };
};

export type Margin = "margin_top" | "margin_right" | "margin_bottom" | "margin_left";
export const margins: Margin[] = ["margin_top", "margin_right", "margin_bottom", "margin_left"];
export type PageSettings = Record<Margin, number> & {
  page_size: "A4" | "A5";
  orientation: "portrait" | "landscape";
};
export type VisualDocument = { schema_version: 2; document: JSONContent; page_settings: PageSettings };
export type FieldDocument = Omit<VisualDocument, "schema_version"> & { schema_version: 3; fields: FieldDefinition[] };
export type SessionBinding = { company_id: number; session_id: string };
export type EditorRequest =
  | { method: "open"; protocol_version: 1; schema_version: 3 }
  | (SessionBinding & {
      method: "verify_document";
      protocol_version: 1;
      document: FieldDocument;
    })
  | (SessionBinding & { method: "import_image"; protocol_version: 1 });

const errors = ["invalid_request", "session_mismatch", "session_closed", "image_cancelled", "invalid_image", "image_unavailable"] as const;
type ErrorCode = (typeof errors)[number];
export type EditorResponse =
  | (SessionBinding & { ok: true; protocol_version: 1; document: EditorDocument | VisualDocument | FieldDocument })
  | (SessionBinding & { ok: true; protocol_version: 1; asset_id: string })
  | { ok: false; protocol_version: 1; error: ErrorCode };

function record(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Expected an object");
  }
  return value as Record<string, unknown>;
}

function keysMatch(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length
    && keys.every((key) => Object.hasOwn(value, key));
}

function parseLegacyDocument(value: unknown): EditorDocument {
  const envelope = record(value);
  if (!keysMatch(envelope, ["schema_version", "document"]) || envelope.schema_version !== 1) {
    throw new Error("Unsupported document schema");
  }
  const doc = record(envelope.document);
  if (!keysMatch(doc, ["type", "content"]) || doc.type !== "doc" || !Array.isArray(doc.content)
      || doc.content.length < 1 || doc.content.length > 256) {
    throw new Error("Invalid document content");
  }
  const paragraphs = doc.content.map((value): Paragraph => {
    const paragraph = record(value);
    if (paragraph.type !== "paragraph") throw new Error("Unsupported block");
    if (keysMatch(paragraph, ["type"])) return { type: "paragraph" };
    if (!keysMatch(paragraph, ["type", "content"])
        || !Array.isArray(paragraph.content) || paragraph.content.length !== 1) {
      throw new Error("Invalid paragraph");
    }
    const text = record(paragraph.content[0]);
    if (!keysMatch(text, ["type", "text"]) || text.type !== "text"
        || typeof text.text !== "string" || !text.text || Array.from(text.text).length > 8192) {
      throw new Error("Invalid text");
    }
    return { type: "paragraph", content: [{ type: "text", text: text.text }] };
  });
  return { schema_version: 1, document: { type: "doc", content: paragraphs } };
}

export function parsePageSettings(value: unknown): PageSettings {
  const settings = record(value);
  if (!keysMatch(settings, ["page_size", "orientation", ...margins])
      || (settings.page_size !== "A4" && settings.page_size !== "A5")
      || (settings.orientation !== "portrait" && settings.orientation !== "landscape")
      || !margins.every((key) => {
        const value = settings[key];
        return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 60;
      })) {
    throw new Error("Invalid page settings");
  }
  return settings as PageSettings;
}

const visualNodes = new Set([
  "doc", "paragraph", "heading", "text", "bulletList", "orderedList", "listItem",
  "table", "tableRow", "tableCell", "tableHeader", "image",
]);
const visualMarks = new Set(["bold", "italic", "underline", "textStyle"]);
const nodeKeys = new Set(["type", "content", "text", "attrs", "marks"]);

export function parseVisualDocument(value: unknown): VisualDocument | FieldDocument {
  const envelope = record(value);
  const version = envelope.schema_version;
  const keys = ["schema_version", "document", "page_settings"];
  if (version === 3) keys.push("fields");
  if (!keysMatch(envelope, keys) || (version !== 2 && version !== 3)
      || record(envelope.document).type !== "doc") {
    throw new Error("Unsupported document schema");
  }
  const fields = version === 3 ? parseFields(envelope.fields) : [];
  const fieldIds = new Set(fields.map(({ id }) => id));
  let count = 0;
  function walk(value: unknown, depth: number, parent?: unknown): void {
    const node = record(value);
    const isField = version === 3 && node.type === "field";
    if (depth > 24 || ++count > 8000 || Object.keys(node).some((key) => !nodeKeys.has(key))
        || typeof node.type !== "string" || (!visualNodes.has(node.type) && !isField)) {
      throw new Error("Invalid document node");
    }
    if (node.attrs !== undefined) record(node.attrs);
    if (isField) {
      const attrs = record(node.attrs);
      const keys = Object.hasOwn(node, "marks") ? ["type", "attrs", "marks"] : ["type", "attrs"];
      if ((parent !== "paragraph" && parent !== "heading") || !keysMatch(node, keys)
          || !keysMatch(attrs, ["fieldId"]) || typeof attrs.fieldId !== "string"
          || !fieldIdPattern.test(attrs.fieldId) || !fieldIds.has(attrs.fieldId)) {
        throw new Error("Invalid or missing field reference.");
      }
    }
    if (node.type === "text") {
      if (typeof node.text !== "string" || !node.text || node.content !== undefined) throw new Error("Invalid text");
    }
    if (node.type === "text" || isField) {
      if (node.marks !== undefined && (!Array.isArray(node.marks) || node.marks.some((value) => {
        const mark = record(value);
        return Object.keys(mark).some((key) => key !== "type" && key !== "attrs")
          || typeof mark.type !== "string" || !visualMarks.has(mark.type);
      }))) throw new Error("Invalid marks");
    } else if (node.text !== undefined || node.marks !== undefined) {
      throw new Error("Invalid block");
    }
    if (node.content !== undefined) {
      if (!Array.isArray(node.content)) throw new Error("Invalid node content");
      for (const child of node.content) walk(child, depth + 1, node.type);
    }
  }
  walk(envelope.document, 0);
  const base = { document: envelope.document as JSONContent, page_settings: parsePageSettings(envelope.page_settings) };
  return version === 3 ? { ...base, schema_version: 3, fields } : { ...base, schema_version: 2 };
}

export function parseResponse(raw: unknown): EditorResponse {
  if (typeof raw !== "string") throw new Error("Expected a JSON response");
  const response = record(JSON.parse(raw));
  if (response.protocol_version !== 1) throw new Error("Unsupported editor protocol");
  if (response.ok === false && keysMatch(response, ["ok", "protocol_version", "error"])) {
    const error = errors.find((value) => value === response.error);
    if (error) return { ok: false, protocol_version: 1, error };
  }
  if (response.ok === true && typeof response.company_id === "number"
      && Number.isSafeInteger(response.company_id) && response.company_id > 0
      && typeof response.session_id === "string" && /^[0-9a-f]{32}$/.test(response.session_id)) {
    const shared = ["ok", "protocol_version", "company_id", "session_id"];
    const binding = { ok: true, protocol_version: 1, company_id: response.company_id, session_id: response.session_id } as const;
    if (keysMatch(response, [...shared, "asset_id"]) && typeof response.asset_id === "string"
        && /^[0-9a-f]{64}$/.test(response.asset_id)) {
      return { ...binding, asset_id: response.asset_id };
    }
    if (keysMatch(response, [...shared, "document"])) {
      const document = record(response.document);
      return { ...binding, document: document.schema_version === 1 ? parseLegacyDocument(document) : parseVisualDocument(document) };
    }
  }
  throw new Error("Invalid response");
}
