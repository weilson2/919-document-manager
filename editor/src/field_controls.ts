import type { Editor } from "@tiptap/core";
import { closeHistory } from "@tiptap/pm/history";
import { NodeSelection } from "@tiptap/pm/state";
import { element } from "./controls";
import { definitions, selectedField } from "./field_node";
import {
  type FieldDefinition, type FieldType, bindings, dateTypes, displayStyles, fieldTypes, flagTypes,
  numericTypes, parseField, parseFields, referenceTypes, textTypes,
} from "./field_schema";

type Input = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

function labelControl(parent: HTMLElement, label: string, control: Input, id: string): void {
  const container = document.createElement("label");
  container.textContent = label;
  control.id = id;
  container.append(control);
  parent.append(container);
}

function input(type = "text"): HTMLInputElement {
  const control = document.createElement("input");
  control.type = type;
  return control;
}

function select(options: [string, string][]): HTMLSelectElement {
  const control = document.createElement("select");
  for (const [value, label] of options) control.add(new Option(label, value));
  return control;
}

function newId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function bindFields(editor: Editor): void {
  const library = element<HTMLSelectElement>("field-library");
  const insert = element<HTMLButtonElement>("insert-field");
  const panel = element("field-properties");
  const form = element<HTMLFormElement>("field-form");
  const values = element("field-type-values");
  const message = element("field-message");
  const usage = element("field-usage");
  const key = element<HTMLInputElement>("field-key");
  const label = element<HTMLInputElement>("field-label");
  const description = element<HTMLInputElement>("field-description");
  const kind = element<HTMLSelectElement>("field-type");
  const required = element<HTMLInputElement>("field-required");
  const remove = element<HTMLButtonElement>("delete-field");
  const available = element("field-tools");
  for (const [value, caption] of Object.entries(fieldTypes)) kind.add(new Option(caption, value));

  let id: string | undefined;
  let creating = false;
  let registry = definitions(editor);
  let formDefinition: FieldDefinition | undefined;
  let readValues: () => Pick<FieldDefinition, "default" | "validation" | "formatting" | "binding">;

  function optionsFor(type: FieldType, previous?: FieldDefinition): void {
    values.replaceChildren();
    const limits = previous?.validation ?? {};
    const formatting = previous?.formatting ?? {};
    const original = previous?.default ?? null;
    const add = <T extends Input>(caption: string, control: T, name: string, value?: string | number | null): T => {
      if (value != null) control.value = String(value);
      labelControl(values, caption, control, name);
      return control;
    };
    let readDefault: () => FieldDefinition["default"];
    const readers: Partial<Record<keyof FieldDefinition["validation"], () => string | number | string[] | undefined>> = {};
    if (referenceTypes.has(type)) {
      readDefault = () => typeof original === "string" ? original : null;
    } else if (flagTypes.has(type)) {
      const options: [string, string][] = type === "checkbox" ? [["true", "Checked"], ["false", "Unchecked"]]
        : [["true", "True"], ["false", "False"]];
      const control = add("Default when filling", select([["", "No default"], ...options]), "field-default",
        original === null ? "" : String(original));
      readDefault = () => control.value === "" ? null : control.value === "true";
    } else if (type === "date_range") {
      const range = typeof original === "object" ? original : null;
      const start = add("Default start date", input("date"), "field-default-start", range?.start);
      const end = add("Default end date", input("date"), "field-default-end", range?.end);
      readDefault = () => start.value || end.value ? { start: start.value, end: end.value } : null;
    } else {
      const control = add("Default when filling", type === "multiline" || type === "address"
        ? document.createElement("textarea") : input(type === "date" ? "date" : "text"),
      "field-default", typeof original === "string" ? original : null);
      readDefault = () => control.value === "" ? null : control.value;
    }
    if (textTypes.has(type)) {
      for (const bound of ["min_length", "max_length"] as const) {
        const control = add(bound === "min_length" ? "Minimum characters" : "Maximum characters",
          input("number"), "field-" + bound, limits[bound]);
        control.min = "0";
        control.max = "4000";
        readers[bound] = () => control.value ? control.valueAsNumber : undefined;
      }
    }
    if (numericTypes.has(type) || dateTypes.has(type)) {
      for (const bound of ["min", "max"] as const) {
        const control = add(bound === "min" ? "Minimum value" : "Maximum value", input(dateTypes.has(type) ? "date" : "text"),
          "field-" + bound, limits[bound]);
        readers[bound] = () => control.value || undefined;
      }
    }
    if (type === "dropdown") {
      const options = add("Choices (one per line)", document.createElement("textarea"), "field-options", limits.options?.join("\n"));
      readers.options = () => options.value.split(/\r?\n/).map((option) => option.trim()).filter(Boolean);
    }
    const styles = displayStyles(type);
    const binding = referenceTypes.has(type) ? null : add("Prefill from", select([
      ["", "No record binding"],
      ...bindings.map((entry): [string, string] => [entry, entry.replace(".", " › ").replaceAll("_", " ")]),
    ]), "field-binding", previous?.binding);
    const style = styles.length ? add("Display format", select([["", "Default"], ...styles]), "field-format", formatting.style) : null;
    const decimals = type === "number" || type === "decimal"
      ? add("Display decimals", input("number"), "field-decimals", formatting.decimals) : null;
    if (decimals) {
      decimals.min = "0";
      decimals.max = "6";
    }
    readValues = () => ({
      default: readDefault(),
      ...(binding?.value ? { binding: binding.value } : {}),
      validation: Object.fromEntries(Object.entries(readers).flatMap(([rule, read]) => {
        const value = read();
        return value === undefined ? [] : [[rule, value]];
      })),
      formatting: {
        ...(style?.value ? { style: style.value } : {}),
        ...(decimals?.value ? { decimals: decimals.valueAsNumber } : {}),
      },
    });
  }

  function referenceCount(): number {
    let count = 0;
    editor.state.doc.descendants((node) => {
      if (node.type.name === "field" && node.attrs.fieldId === id || node.attrs.showWhenFieldId === id) count += 1;
    });
    return count;
  }

  function refreshUsage(): void {
    if (!formDefinition) {
      usage.textContent = "";
      return;
    }
    const count = referenceCount();
    if (count === 0) usage.textContent = "Ready to insert.";
    else if (count === 1) usage.textContent = "Used in 1 place.";
    else usage.textContent = "Used in " + count + " places. They all share these settings.";
  }

  function show(field?: FieldDefinition): void {
    formDefinition = field;
    panel.hidden = !creating && !field;
    library.value = id ?? "";
    insert.disabled = !field;
    remove.hidden = !field;
    refreshUsage();
    if (panel.hidden) return;
    key.value = field?.key ?? "";
    label.value = field?.label ?? "";
    description.value = field?.description ?? "";
    required.checked = field?.required ?? false;
    kind.value = field?.type ?? "text";
    optionsFor(kind.value as FieldType, field);
    message.textContent = "";
  }

  function refreshLibrary(): void {
    library.replaceChildren(new Option("Choose a field", ""), ...registry.map((field) => new Option(field.label, field.id)));
    library.value = id ?? "";
  }

  function choose(next?: string): void {
    id = next;
    creating = false;
    show(registry.find((field) => field.id === id));
    if (!panel.hidden) panel.closest(".properties")!.scrollTop = 0;
  }

  function writeFields(next: FieldDefinition[]): void {
    editor.view.dispatch(closeHistory(editor.state.tr.setDocAttribute("fields", next)));
  }

  element("new-field").addEventListener("click", () => {
    id = undefined;
    creating = true;
    show();
    panel.closest(".properties")!.scrollTop = 0;
    key.focus();
  });
  library.addEventListener("change", () => choose(library.value || undefined));
  kind.addEventListener("change", () => optionsFor(kind.value as FieldType,
    formDefinition?.type === kind.value ? formDefinition : undefined));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      const field = parseField({
        id: id ?? newId(), key: key.value.trim(), label: label.value.trim(), type: kind.value,
        required: required.checked, ...(description.value.trim() ? { description: description.value.trim() } : {}), ...readValues(),
      });
      const next = id ? registry.map((entry) => entry.id === id ? field : entry) : [...registry, field];
      const validated = parseFields(next);
      id = field.id;
      creating = false;
      writeFields(validated);
      message.textContent = "Field settings saved.";
    } catch (error) {
      message.textContent = error instanceof Error ? error.message : "Could not save the field.";
    }
  });
  insert.addEventListener("click", () => {
    if (!id || !registry.some((field) => field.id === id)) return;
    const node = editor.schema.nodes.field.create({ fieldId: id });
    const transaction = closeHistory(editor.state.tr);
    if (transaction.selection instanceof NodeSelection && transaction.selection.node.type.name === "field") {
      transaction.insert(transaction.selection.to, node);
    } else {
      transaction.replaceSelectionWith(node, false);
    }
    if (transaction.docChanged) {
      editor.view.dispatch(transaction.scrollIntoView());
      editor.view.focus();
    }
  });
  remove.addEventListener("click", () => {
    if (referenceCount() > 0) {
      message.textContent = "Remove all references from the document before deleting this field.";
      return;
    }
    const next = registry.filter((field) => field.id !== id);
    choose();
    writeFields(next);
  });

  editor.on("transaction", ({ transaction }) => {
    if (registry !== definitions(editor)) {
      registry = definitions(editor);
      refreshLibrary();
      const field = registry.find((entry) => entry.id === id);
      if (!creating && formDefinition !== field) show(field);
    }
    const selection = selectedField(editor);
    if (transaction.selectionSet && selection && (selection !== id || creating)) choose(selection);
    else if (transaction.docChanged) refreshUsage();
  });
  refreshLibrary();
  available.hidden = false;
}
