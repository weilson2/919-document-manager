import { Editor, type JSONContent } from "@tiptap/core";
import { PageCanvas } from "./canvas";
import { bindControls, element } from "./controls";
import { editorExtensions } from "./extensions";
import { bindFields } from "./field_controls";
import { definitions } from "./field_node";
import { type EditorRequest, type EditorResponse, parseResponse, parseVisualDocument } from "./protocol";
import "./editor.css";

type Bridge = { request: (payload: string, callback: (result: unknown) => void) => void };

declare const qt: { webChannelTransport: object } | undefined;
declare const QWebChannel: new (
  transport: object,
  ready: (channel: { objects: { editorBridge?: Bridge } }) => void,
) => unknown;

const editorElement = element("editor");
const statusElement = element("editor-status");
const verifyButton = element<HTMLButtonElement>("verify-document");
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
    // Image import waits for the user to close the native file picker.
    const timer = payload.method === "import_image" ? undefined
      : window.setTimeout(() => reject(new Error("Request timed out")), timeoutMs);
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

function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, entry: unknown) => {
    if (entry !== null && typeof entry === "object" && !Array.isArray(entry)) {
      return Object.fromEntries(Object.entries(entry).sort(([a], [b]) => a.localeCompare(b)));
    }
    return entry;
  });
}

function omitUnusedConditions(node: JSONContent): JSONContent {
  if (node.attrs?.showWhenFieldId === null) delete node.attrs.showWhenFieldId;
  node.content?.forEach(omitUnusedConditions);
  return node;
}

async function start(): Promise<void> {
  const bridge = await connect();
  const session = await request(bridge, { method: "open", protocol_version: 1, schema_version: 3 });
  if (!session.ok || !("document" in session) || session.document.schema_version !== 3) {
    throw new Error("Editor session unavailable");
  }
  const binding = { company_id: session.company_id, session_id: session.session_id, protocol_version: 1 } as const;
  const belongsHere = (result: EditorResponse) => result.ok
    && result.company_id === binding.company_id && result.session_id === binding.session_id;
  const editor = new Editor({
    element: editorElement,
    extensions: editorExtensions(session.session_id),
    content: { ...session.document.document, attrs: { fields: session.document.fields } },
    enableContentCheck: true,
    injectCSS: false,
    editorProps: { attributes: { "aria-label": "Document text", role: "textbox", "aria-multiline": "true" } },
  });
  const canvas = new PageCanvas(editor.view.dom, session.document.page_settings);
  const report = (message: string) => { statusElement.textContent = message; };
  let designRevision = session.design_revision;
  const header = element<HTMLInputElement>("page-header");
  const footer = element<HTMLInputElement>("page-footer");
  const pageNumbers = element<HTMLInputElement>("page-numbers");
  const companyLogo = element<HTMLInputElement>("page-company-logo");
  header.value = session.document.print_settings?.header ?? "";
  footer.value = session.document.print_settings?.footer ?? "";
  pageNumbers.checked = session.document.print_settings?.page_numbers ?? false;
  companyLogo.checked = session.document.print_settings?.company_logo ?? false;
  let printSettings = session.document.print_settings;
  if (printSettings) canvas.setPrintSettings(printSettings);
  for (const input of [header, footer, pageNumbers, companyLogo]) {
    input.addEventListener("change", () => {
      printSettings = { header: header.value, footer: footer.value, page_numbers: pageNumbers.checked, company_logo: companyLogo.checked };
      canvas.setPrintSettings(printSettings);
      if (designRevision !== undefined) queueSave();
    });
  }
  let importing = false;
  const settings = bindControls(editor, canvas, session.document.page_settings, async () => {
    if (importing) return;
    importing = true;
    try {
      const result = await request(bridge, { ...binding, method: "import_image" });
      if (!result.ok && result.error === "image_cancelled") return;
      if (!result.ok && result.error === "invalid_image") {
        report("Choose a valid PNG or JPEG up to 8 MB and 4096 × 4096 pixels.");
        return;
      }
      if (!belongsHere(result) || !("asset_id" in result)) throw new Error("Image unavailable");
      editor.chain().focus().insertContent({ type: "image", attrs: { assetId: result.asset_id } }).run();
    } catch {
      report("Could not insert the image into this session.");
    } finally {
      importing = false;
    }
  }, report, () => { if (designRevision !== undefined) queueSave(); });
  bindFields(editor);
  const currentDocument = () => {
    const content = editor.getJSON();
    editor.schema.nodeFromJSON(content).check();
    const { attrs, ...document } = omitUnusedConditions(content);
    const parsed = parseVisualDocument({
      schema_version: 3, fields: definitions(editor), document, page_settings: settings(),
      ...(printSettings ? { print_settings: printSettings } : {}),
    });
    if (parsed.schema_version !== 3) throw new Error("Unsupported document schema");
    return parsed;
  };
  const saveButton = element<HTMLButtonElement>("save-design");
  const publishButton = element<HTMLButtonElement>("publish-design");
  let pending: "save_design" | "publish_design" | undefined;
  let saving = false;
  let conflict = false;

  function queueSave(method: "save_design" | "publish_design" = "save_design"): void {
    void request(bridge, { ...binding, method: "mark_dirty" }).catch(() => {});
    if (conflict) {
      report("A newer draft exists. Reopen the design to load it.");
      return;
    }
    if (pending !== "publish_design") pending = method;
    void savePending();
  }

  async function savePending(): Promise<void> {
    if (saving || pending === undefined || designRevision === undefined || conflict) return;
    saving = true;
    const method = pending;
    pending = undefined;
    try {
      const result = await request(bridge, { ...binding, method, revision: designRevision, document: currentDocument() });
      if (!result.ok && result.error === "design_conflict") {
        conflict = true;
        report("A newer draft exists. Reopen the design to load it.");
        return;
      }
      if (!belongsHere(result) || !("published_version" in result)) throw new Error("Save failed");
      designRevision = result.design_revision;
      report(result.published_version === null ? "Draft saved" : `Version ${result.published_version} published`);
    } catch {
      report("This change has not been saved. Try Save draft again.");
    } finally {
      saving = false;
      if (pending !== undefined && !conflict) void savePending();
    }
  }

  if (designRevision !== undefined) {
    saveButton.hidden = false;
    publishButton.hidden = false;
    element("session-note").textContent = "Template draft · Autosave on";
    saveButton.addEventListener("click", () => queueSave());
    publishButton.addEventListener("click", () => queueSave("publish_design"));
    editor.on("update", () => queueSave());
    window.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        queueSave();
      }
    });
  }
  statusElement.textContent = "Editor ready";
  verifyButton.disabled = false;
  verifyButton.addEventListener("click", async () => {
    verifyButton.disabled = true;
    try {
      const sent = currentDocument();
      const result = await request(bridge, { ...binding, method: "verify_document", document: sent });
      if (!belongsHere(result) || !("document" in result) || canonical(result.document) !== canonical(sent)) {
        throw new Error("Document could not be verified");
      }
      statusElement.textContent = canonical(currentDocument()) === canonical(sent)
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
