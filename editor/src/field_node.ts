import { Node, type Editor } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import { NodeSelection } from "@tiptap/pm/state";
import type { FieldDefinition } from "./field_schema";

export const DocumentWithFields = Document.extend({
  content: "(block | pageBreak)+",
  addAttributes() {
    return { fields: { default: [], rendered: false } };
  },
});

export function definitions(editor: Editor): FieldDefinition[] {
  return editor.state.doc.attrs.fields;
}

export function selectedField(editor: Editor): string | undefined {
  const selection = editor.state.selection;
  return selection instanceof NodeSelection && selection.node.type.name === "field"
    ? selection.node.attrs.fieldId : undefined;
}

export function fieldNode(sessionId: string) {
  return Node.create({
    name: "field",
    inline: true,
    group: "inline",
    atom: true,
    selectable: true,
    marks: "",
    addAttributes() {
      return { fieldId: { default: null, rendered: false } };
    },
    parseHTML() {
      return [{
        tag: "span[data-field-id]",
        getAttrs: (element) => {
          const { fieldId, fieldSession } = (element as HTMLElement).dataset;
          return this.editor && fieldSession === sessionId && definitions(this.editor).some((field) => field.id === fieldId)
            ? { fieldId } : false;
        },
      }];
    },
    renderHTML({ node }) {
      const definition = this.editor && definitions(this.editor).find(({ id }) => id === node.attrs.fieldId);
      return ["span", { class: "document-field", "data-field-id": node.attrs.fieldId, "data-field-session": sessionId },
        definition?.label ?? "Missing field"];
    },
    addNodeView() {
      return ({ editor, node, getPos }) => {
        const dom = document.createElement("span");
        dom.className = "document-field";
        dom.contentEditable = "false";
        let fieldId = node.attrs.fieldId;
        const refresh = () => {
          const field = definitions(editor).find(({ id }) => id === fieldId);
          const label = field?.label ?? "Missing field";
          if (dom.textContent !== label) dom.textContent = label;
          dom.title = field ? field.key : label;
        };
        dom.addEventListener("click", () => {
          const position = getPos();
          if (editor.isEditable && position !== undefined) editor.commands.setNodeSelection(position);
        });
        refresh();
        editor.on("transaction", refresh);
        return {
          dom,
          update(next) {
            if (next.type !== node.type) return false;
            fieldId = next.attrs.fieldId;
            refresh();
            return true;
          },
          ignoreMutation: (mutation) => mutation.type !== "selection",
          destroy: () => editor.off("transaction", refresh),
        };
      };
    },
  });
}
