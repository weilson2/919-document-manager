import { Editor } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { type EditorRequest, type EditorResponse, parseDocument, parseResponse } from "./protocol";
import "./editor.css";

type Bridge = { request: (payload: string, callback: (result: unknown) => void) => void };

declare const qt: { webChannelTransport: object } | undefined;
declare const QWebChannel: new (
  transport: object,
  ready: (channel: { objects: { editorBridge?: Bridge } }) => void,
) => unknown;

const editorElement = document.querySelector<HTMLElement>("#editor")!;
const statusElement = document.querySelector<HTMLElement>("#editor-status")!;
const verifyButton = document.querySelector<HTMLButtonElement>("#verify-document")!;
const timeoutMs = 5000;

function connect(): Promise<Bridge> {
  return new Promise((resolve, reject) => {
    if (typeof qt === "undefined" || typeof QWebChannel === "undefined") {
      reject(new Error("Local Qt WebChannel unavailable"));
      return;
    }
    const timer = window.setTimeout(() => reject(new Error("Connection timed out")), timeoutMs);
    new QWebChannel(qt.webChannelTransport, (channel) => {
      window.clearTimeout(timer);
      const bridge = channel.objects.editorBridge;
      if (typeof bridge?.request === "function") resolve(bridge);
      else reject(new Error("Editor bridge unavailable"));
    });
  });
}

function request(bridge: Bridge, payload: EditorRequest): Promise<EditorResponse> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("Request timed out")), timeoutMs);
    bridge.request(JSON.stringify(payload), (raw) => {
      window.clearTimeout(timer);
      try {
        resolve(parseResponse(raw));
      } catch (error) {
        reject(error);
      }
    });
  });
}

async function start(): Promise<void> {
  const bridge = await connect();
  const session = await request(bridge, { method: "open", protocol_version: 1 });
  if (!session.ok) throw new Error("Editor session unavailable");
  const editor = new Editor({
    element: editorElement,
    extensions: [Document, Paragraph, Text],
    content: session.document.document,
    enableContentCheck: true,
    injectCSS: false,
    editorProps: { attributes: { "aria-label": "Document text", role: "textbox", "aria-multiline": "true" } },
    onUpdate() {
      statusElement.textContent = "Ready to verify";
    },
  });
  statusElement.textContent = "Editor ready";
  verifyButton.disabled = false;
  verifyButton.addEventListener("click", async () => {
    verifyButton.disabled = true;
    try {
      const sent = parseDocument({ schema_version: 1, document: editor.getJSON() });
      const result = await request(bridge, {
        method: "verify_document", protocol_version: 1,
        company_id: session.company_id, session_id: session.session_id,
        document: sent,
      });
      if (!result.ok || result.company_id !== session.company_id || result.session_id !== session.session_id
          || JSON.stringify(result.document) !== JSON.stringify(sent)) {
        throw new Error("Document could not be verified");
      }
      const current = parseDocument({ schema_version: 1, document: editor.getJSON() });
      statusElement.textContent = JSON.stringify(current) === JSON.stringify(sent)
        ? "Document structure verified"
        : "Document changed. Verify again.";
    } catch {
      statusElement.textContent = "Could not verify the document. Try shorter text or reopen the editor.";
    } finally {
      verifyButton.disabled = false;
    }
  });
}

void start().catch(() => {
  statusElement.textContent = "Could not start the local editor.";
});
