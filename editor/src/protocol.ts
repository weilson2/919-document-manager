export type TextNode = { type: "text"; text: string };
export type Paragraph = { type: "paragraph"; content?: [TextNode] };
export type EditorDocument = {
  schema_version: 1;
  document: { type: "doc"; content: Paragraph[] };
};

type SessionBinding = { company_id: number; session_id: string };
export type EditorRequest =
  | { method: "open"; protocol_version: 1 }
  | (SessionBinding & {
      method: "verify_document";
      protocol_version: 1;
      document: EditorDocument;
    });

type ErrorCode = "invalid_request" | "session_mismatch" | "session_closed";
export type EditorResponse =
  | (SessionBinding & { ok: true; protocol_version: 1; document: EditorDocument })
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

export function parseDocument(value: unknown): EditorDocument {
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

export function parseResponse(raw: unknown): EditorResponse {
  if (typeof raw !== "string") throw new Error("Expected a JSON response");
  const response = record(JSON.parse(raw));
  if (response.protocol_version !== 1) throw new Error("Unsupported editor protocol");
  if (response.ok === false && keysMatch(response, ["ok", "protocol_version", "error"])) {
    const error = response.error;
    if (error === "invalid_request" || error === "session_mismatch" || error === "session_closed") {
      return { ok: false, protocol_version: 1, error };
    }
  }
  if (response.ok === true && keysMatch(response, ["ok", "protocol_version", "company_id", "session_id", "document"])
      && typeof response.company_id === "number" && Number.isSafeInteger(response.company_id) && response.company_id > 0
      && typeof response.session_id === "string" && /^[0-9a-f]{32}$/.test(response.session_id)) {
    return {
      ok: true, protocol_version: 1,
      company_id: response.company_id, session_id: response.session_id,
      document: parseDocument(response.document),
    };
  }
  throw new Error("Invalid response");
}
