import { Extension, Mark, Node } from "@tiptap/core";
import Bold from "@tiptap/extension-bold";
import Heading from "@tiptap/extension-heading";
import Italic from "@tiptap/extension-italic";
import { BulletList, ListItem, ListKeymap, OrderedList } from "@tiptap/extension-list";
import Paragraph from "@tiptap/extension-paragraph";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import Text from "@tiptap/extension-text";
import Underline from "@tiptap/extension-underline";
import { UndoRedo } from "@tiptap/extensions";
import { managedImageAttributes, managedImageView } from "./image_view";
import { DocumentWithFields, fieldNode } from "./field_node";

const alignments = ["left", "center", "right", "justify"];
const fonts = ["Arial", "Calibri", "Georgia", "Segoe UI", "Times New Roman", "Verdana", "Courier New"];
const lineSpacings = ["1", "1.15", "1.5", "2"];

function choice(value: unknown, choices: string[]): string | null {
  return typeof value === "string" && choices.includes(value) ? value : null;
}

function integer(value: unknown, min: number, max: number): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= max ? value : null;
}

function points(value: string, min: number, max: number): number | null {
  return /^\d+pt$/.test(value) ? integer(Number.parseInt(value, 10), min, max) : null;
}

function hexColor(value: string): string | null {
  if (/^#[0-9a-f]{6}$/i.test(value)) return value.toLowerCase();
  const rgb = value.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/);
  if (!rgb) return null;
  return "#" + rgb.slice(1).map((part) => Number(part).toString(16).padStart(2, "0")).join("");
}

const ParagraphProperties = Extension.create({
  name: "paragraphProperties",
  addGlobalAttributes() {
    return [{
      types: ["paragraph", "heading"],
      attributes: {
        showWhenFieldId: { default: null, rendered: false },
        textAlign: {
          default: null,
          parseHTML: (element) => choice(element.style.textAlign, alignments),
          renderHTML: ({ textAlign }) => {
            const align = choice(textAlign, alignments);
            return align ? { style: `text-align:${align}` } : {};
          },
        },
        lineSpacing: {
          default: null,
          parseHTML: (element) => choice(element.style.lineHeight, lineSpacings),
          renderHTML: ({ lineSpacing }) => {
            const spacing = choice(lineSpacing, lineSpacings);
            return spacing ? { style: `line-height:${spacing}` } : {};
          },
        },
        spaceAfter: {
          default: null,
          parseHTML: (element) => points(element.style.marginBottom, 0, 48),
          renderHTML: ({ spaceAfter }) => {
            const spacing = integer(spaceAfter, 0, 48);
            return spacing === null ? {} : { style: `margin-bottom:${spacing}pt` };
          },
        },
      },
    }];
  },
});

const TextProperties = Mark.create({
  name: "textStyle",
  addAttributes() {
    return {
      fontFamily: {
        default: null,
        parseHTML: (element) => choice(element.style.fontFamily.replace(/^['"]|['"]$/g, ""), fonts),
        renderHTML: ({ fontFamily }) => {
          const family = choice(fontFamily, fonts);
          return family ? { style: `font-family:"${family}"` } : {};
        },
      },
      fontSize: {
        default: null,
        parseHTML: (element) => points(element.style.fontSize, 8, 72),
        renderHTML: ({ fontSize }) => {
          const size = integer(fontSize, 8, 72);
          return size === null ? {} : { style: `font-size:${size}pt` };
        },
      },
      color: {
        default: null,
        parseHTML: (element) => hexColor(element.style.color),
        renderHTML: ({ color }) => {
          const hex = typeof color === "string" ? hexColor(color) : null;
          return hex ? { style: `color:${hex}` } : {};
        },
      },
    };
  },
  parseHTML() {
    return [{
      tag: "span[style]",
      getAttrs(node) {
        return node instanceof HTMLElement && (node.style.fontFamily || node.style.fontSize || node.style.color)
          ? null : false;
      },
    }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["span", HTMLAttributes, 0];
  },
});

const EditableTable = Table.extend({
  addAttributes() {
    return {
      borderStyle: {
        default: "grid",
        parseHTML: (element) => element.dataset.borders === "none" ? "none" : "grid",
        renderHTML: ({ borderStyle }) => ({ "data-borders": borderStyle === "none" ? "none" : "grid" }),
      },
    };
  },
}).configure({ View: null, renderWrapper: true });

function managedImage(sessionId: string) {
  return Node.create({
    name: "image",
    group: "block",
    atom: true,
    selectable: true,
    addAttributes() {
      return { assetId: { default: null }, alt: { default: "" }, width: { default: 70 } };
    },
    renderHTML({ node }) {
      const { src, alt, width } = managedImageAttributes(node, sessionId);
      return ["figure", {}, ["img", { src, alt, style: `width:${width}%` }]];
    },
    addNodeView() {
      return (props) => managedImageView(props, sessionId);
    },
  });
}

const PageBreak = Node.create({
  name: "pageBreak",
  group: "pageBreak",
  atom: true,
  selectable: true,
  renderHTML: () => ["hr", { class: "manual-page-break", "aria-label": "Page break" }],
});

export function editorExtensions(sessionId: string) {
  return [
    DocumentWithFields, Paragraph, Text, Heading.configure({ levels: [1, 2, 3] }), Bold, Italic, Underline,
    BulletList, OrderedList, ListItem, ListKeymap, UndoRedo, ParagraphProperties, TextProperties,
    EditableTable, TableRow, TableCell, TableHeader, managedImage(sessionId), fieldNode(sessionId), PageBreak,
  ];
}
