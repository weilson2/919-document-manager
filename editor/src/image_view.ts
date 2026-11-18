import type { NodeViewRendererProps } from "@tiptap/core";
import { closeHistory } from "@tiptap/pm/history";
import type { Node } from "@tiptap/pm/model";
import { NodeSelection, type Transaction } from "@tiptap/pm/state";

export function managedImageAttributes(node: Node, sessionId: string) {
  const { assetId, alt, width } = node.attrs;
  return {
    src: typeof assetId === "string" && /^[0-9a-f]{64}$/.test(assetId)
      ? `image/${sessionId}/${assetId}.png` : "",
    alt: typeof alt === "string" ? alt : "",
    width: typeof width === "number" && Number.isInteger(width) && width >= 10 && width <= 100 ? width : 70,
  };
}

export function updateImageAttributes(transaction: Transaction, position: number, attributes: object): boolean {
  const image = transaction.doc.nodeAt(position);
  if (image?.type.name !== "image") return false;
  transaction.setNodeMarkup(position, undefined, { ...image.attrs, ...attributes });
  transaction.setSelection(NodeSelection.create(transaction.doc, position));
  closeHistory(transaction);
  return true;
}

export function managedImageView({ node, view, getPos }: NodeViewRendererProps, sessionId: string) {
  const dom = document.createElement("figure");
  const frame = document.createElement("div");
  frame.className = "managed-image-frame";
  const image = document.createElement("img");
  image.draggable = false;
  const handle = document.createElement("button");
  handle.type = "button";
  handle.className = "image-resize-handle";
  handle.title = "Drag to resize";
  handle.setAttribute("aria-label", "Resize image. Use Left or Right Arrow to change the width.");
  frame.append(image, handle);
  dom.append(frame);

  let drag: { pointer: number; startX: number; figureWidth: number; startWidth: number; width: number } | undefined;
  const clamp = (width: number) => Math.max(10, Math.min(100, Math.round(width)));

  function updateImage(): void {
    const attributes = managedImageAttributes(node, sessionId);
    if (image.getAttribute("src") !== attributes.src) image.setAttribute("src", attributes.src);
    image.alt = attributes.alt;
    frame.style.width = attributes.width + "%";
  }

  function commit(width: number): void {
    const position = getPos();
    if (position === undefined || !view.editable || width === node.attrs.width) return;
    const transaction = view.state.tr;
    if (updateImageAttributes(transaction, position, { width })) view.dispatch(transaction);
  }

  handle.addEventListener("pointerdown", (event) => {
    const figureWidth = dom.getBoundingClientRect().width;
    if (!view.editable || event.button !== 0 || drag || figureWidth <= 0) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    const startWidth = managedImageAttributes(node, sessionId).width;
    drag = { pointer: event.pointerId, startX: event.clientX, figureWidth, startWidth, width: startWidth };
  });
  handle.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointer) return;
    drag.width = clamp(drag.startWidth + (event.clientX - drag.startX) * 100 / drag.figureWidth);
    frame.style.width = drag.width + "%";
  });
  handle.addEventListener("pointerup", (event) => {
    if (!drag || event.pointerId !== drag.pointer) return;
    const width = drag.width;
    drag = undefined;
    updateImage();
    commit(width);
  });
  for (const event of ["pointercancel", "lostpointercapture"]) {
    handle.addEventListener(event, (event) => {
      if (drag && (event as PointerEvent).pointerId === drag.pointer) {
        drag = undefined;
        updateImage();
      }
    });
  }
  handle.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    commit(clamp(managedImageAttributes(node, sessionId).width + direction * (event.shiftKey ? 5 : 1)));
  });

  updateImage();
  return {
    dom,
    update(next: Node) {
      if (next.type !== node.type) return false;
      node = next;
      updateImage();
      return true;
    },
    stopEvent: (event: Event) => event.target === handle,
    ignoreMutation: (mutation: { type: string }) => mutation.type !== "selection",
  };
}
