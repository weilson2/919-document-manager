import type { Editor } from "@tiptap/core";
import { NodeSelection } from "@tiptap/pm/state";
import type { PageCanvas } from "./canvas";
import { updateImageAttributes } from "./image_view";
import { definitions } from "./field_node";
import { type PageSettings, margins, parsePageSettings } from "./protocol";

export function element<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

type Control = HTMLInputElement | HTMLSelectElement;
type Command = () => void | boolean | Promise<void>;

export function bindControls(
  editor: Editor, canvas: PageCanvas, initialSettings: PageSettings,
  importImage: () => Promise<void>, report: (text: string) => void, settingsChanged: () => void = () => {},
) {
  const editTools = element<HTMLFieldSetElement>("edit-tools");
  const insert = element<HTMLFieldSetElement>("insert-tools");
  const inspector = element<HTMLFieldSetElement>("properties");
  const preview = element<HTMLButtonElement>("preview-toggle");
  const zoom = element<HTMLSelectElement>("zoom");
  const outline = element("outline");
  const visibility = element<HTMLSelectElement>("show-when-field");
  let pageSettings = initialSettings;
  const chain = () => editor.chain().focus();

  const commands: Record<string, Command> = {
    undo: () => chain().undo().run(),
    redo: () => chain().redo().run(),
    bold: () => chain().toggleBold().run(),
    italic: () => chain().toggleItalic().run(),
    underline: () => chain().toggleUnderline().run(),
    "bullet-list": () => chain().toggleBulletList().run(),
    "ordered-list": () => chain().toggleOrderedList().run(),
    heading: () => chain().setHeading({ level: 1 }).run(),
    table: () => chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
    image: importImage,
    "page-break": () => chain().command(({ tr, dispatch, state }) => {
      const end = tr.selection.$to;
      const after = end.depth ? end.after(1) : end.pos;
      if (dispatch) {
        tr.insert(after, state.schema.nodes.pageBreak.create());
        if (tr.doc.content.size === after + 1) tr.insert(after + 1, state.schema.nodes.paragraph.create());
      }
      return true;
    }).run(),
    "add-row": () => chain().addRowAfter().run(),
    "delete-row": () => chain().deleteRow().run(),
    "add-column": () => chain().addColumnAfter().run(),
    "delete-column": () => chain().deleteColumn().run(),
    "header-row": () => chain().toggleHeaderRow().run(),
    "merge-cells": () => chain().mergeCells().run(),
    "split-cell": () => chain().splitCell().run(),
    "delete-table": () => chain().deleteTable().run(),
    "delete-image": () => chain().deleteSelection().run(),
  };
  const buttons = [...document.querySelectorAll<HTMLButtonElement>("button[data-command]")];
  for (const button of buttons) {
    // Pointer activation should keep the selection in the document until the command runs.
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => void commands[button.dataset.command!]());
  }

  function onChange(id: string, action: (control: Control) => void): void {
    const control = element<Control>(id);
    control.addEventListener("change", () => action(control));
  }

  const setParagraph = (attrs: object) => chain()
    .updateAttributes("paragraph", attrs)
    .updateAttributes("heading", attrs)
    .run();
  onChange("block-format", ({ value }) => {
    if (value === "0") chain().setParagraph().run();
    else chain().setHeading({ level: Number(value) as 1 | 2 | 3 }).run();
  });
  for (const control of ["toolbar-alignment", "alignment"]) {
    onChange(control, ({ value }) => setParagraph({ textAlign: value }));
  }
  onChange("line-spacing", ({ value }) => setParagraph({ lineSpacing: value || null }));
  onChange("space-after", (control) => {
    if (control.checkValidity()) setParagraph({ spaceAfter: control.value === "" ? null : Number(control.value) });
  });
  onChange("show-when-field", ({ value }) => setParagraph({ showWhenFieldId: value || null }));
  onChange("font-family", ({ value }) => chain().setMark("textStyle", { fontFamily: value || null }).run());
  onChange("font-size", ({ value }) => chain().setMark("textStyle", { fontSize: value ? Number(value) : null }).run());
  onChange("text-color", ({ value }) => chain().setMark("textStyle", { color: value }).run());
  onChange("table-borders", ({ value }) => chain().updateAttributes("table", { borderStyle: value }).run());
  const setImageProperties = (attributes: object) => chain().command(({ tr, dispatch }) => {
    if (!(tr.selection instanceof NodeSelection) || tr.selection.node.type.name !== "image") return false;
    return !dispatch || updateImageAttributes(tr, tr.selection.from, attributes);
  }).run();
  onChange("image-width", (control) => {
    if (control.value && control.checkValidity()) setImageProperties({ width: Number(control.value) });
  });
  onChange("image-alt", ({ value }) => setImageProperties({ alt: value }));

  function setPageSettings(update: Partial<PageSettings>): void {
    try {
      pageSettings = parsePageSettings({ ...pageSettings, ...update });
      canvas.setPageSettings(pageSettings);
      settingsChanged();
      report("Ready to verify");
    } catch {
      report("Choose a margin between 0 and 60 mm.");
    }
  }

  const paper = element<HTMLSelectElement>("page-size");
  const orientation = element<HTMLSelectElement>("orientation");
  paper.value = initialSettings.page_size;
  orientation.value = initialSettings.orientation;
  onChange("page-size", ({ value }) => setPageSettings({ page_size: value as PageSettings["page_size"] }));
  onChange("orientation", ({ value }) => setPageSettings({ orientation: value as PageSettings["orientation"] }));
  for (const key of margins) {
    const input = document.querySelector<HTMLInputElement>(`[data-margin="${key}"]`)!;
    input.value = String(initialSettings[key]);
    input.addEventListener("change", () => {
      if (input.value && input.checkValidity()) setPageSettings({ [key]: input.valueAsNumber });
      else input.value = String(pageSettings[key]);
    });
  }

  zoom.addEventListener("change", () => canvas.setZoom(zoom.value));
  preview.addEventListener("click", () => {
    const enabled = preview.getAttribute("aria-pressed") !== "true";
    preview.setAttribute("aria-pressed", String(enabled));
    preview.textContent = enabled ? "Back to editing" : "Preview";
    element("workspace").classList.toggle("preview-mode", enabled);
    for (const group of [editTools, inspector, insert]) group.disabled = enabled;
    editor.setEditable(!enabled);
    canvas.setPreview(enabled);
    if (!enabled) editor.commands.focus();
  });

  function refreshSelection(): void {
    const activeMarks = { bold: "bold", italic: "italic", underline: "underline", "bullet-list": "bulletList", "ordered-list": "orderedList" };
    for (const button of buttons) {
      const action = button.dataset.command!;
      if (action in activeMarks) button.setAttribute("aria-pressed", String(editor.isActive(activeMarks[action as keyof typeof activeMarks])));
      if (action === "undo") button.disabled = !editor.can().undo();
      if (action === "redo") button.disabled = !editor.can().redo();
      if (action === "merge-cells") button.disabled = !editor.can().mergeCells();
      if (action === "split-cell") button.disabled = !editor.can().splitCell();
    }
    const setValue = (id: string, value: unknown) => {
      const control = element<Control>(id);
      if (document.activeElement !== control) control.value = value == null ? "" : String(value);
    };
    const heading = editor.isActive("heading");
    const paragraph = editor.getAttributes(heading ? "heading" : "paragraph");
    visibility.replaceChildren(new Option("Always show", ""), ...definitions(editor)
      .map((field) => new Option(field.label, field.id)));
    visibility.value = paragraph.showWhenFieldId ?? "";
    setValue("block-format", heading ? paragraph.level : 0);
    setValue("toolbar-alignment", paragraph.textAlign ?? "left");
    setValue("alignment", paragraph.textAlign ?? "left");
    setValue("line-spacing", paragraph.lineSpacing);
    setValue("space-after", paragraph.spaceAfter);
    const text = editor.getAttributes("textStyle");
    setValue("font-family", text.fontFamily);
    setValue("font-size", text.fontSize);
    setValue("text-color", text.color ?? "#152740");
    element("table-properties").hidden = !editor.isActive("table");
    setValue("table-borders", editor.getAttributes("table").borderStyle ?? "grid");
    const imageProperties = element("image-properties");
    const imageSelected = editor.isActive("image");
    if (imageSelected && imageProperties.hidden) inspector.parentElement!.scrollTop = 0;
    imageProperties.hidden = !imageSelected;
    const image = editor.getAttributes("image");
    setValue("image-width", image.width);
    setValue("image-alt", image.alt);
  }

  function refreshOutline(): void {
    const entries: HTMLElement[] = [];
    editor.state.doc.descendants((node, position) => {
      if (node.type.name !== "heading") return;
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.level = String(node.attrs.level);
      button.textContent = node.textContent || "Untitled heading";
      button.title = button.textContent;
      button.addEventListener("click", () => {
        const heading = editor.view.nodeDOM(position);
        if (heading instanceof HTMLElement) canvas.reveal(heading);
        if (editor.isEditable) editor.commands.focus(position + 1, { scrollIntoView: false });
      });
      entries.push(button);
    });
    if (!entries.length) {
      const empty = document.createElement("p");
      empty.textContent = "Headings appear here.";
      entries.push(empty);
    }
    outline.replaceChildren(...entries);
  }

  editor.on("transaction", ({ transaction }) => {
    refreshSelection();
    if (transaction.docChanged) {
      refreshOutline();
      canvas.schedule();
      report("Ready to verify");
    }
  });
  for (const group of [editTools, inspector, insert]) group.disabled = false;
  preview.disabled = false;
  zoom.disabled = false;
  refreshSelection();
  refreshOutline();
  return () => pageSettings;
}
