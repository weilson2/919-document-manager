import { type Page, measureDocument, paginate, paperMetrics } from "./pagination";
import type { PageSettings } from "./protocol";

function element<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

export class PageCanvas {
  private canvas = element("canvas");
  private stage = element("stage");
  private layer = element("zoom-layer");
  private paper = element("edit-paper");
  private guides = element("page-guides");
  private preview = element("preview-pages");
  private navigation = element("page-nav");
  private warning = element("layout-warning");
  private scale = 1;
  private zoom = "fit";
  private metrics;
  private pages: Page[] = [];
  private overflowWidth = 0;
  private previewing = false;
  private updateFrame = 0;
  private observer: IntersectionObserver | undefined;

  constructor(private content: HTMLElement, settings: PageSettings) {
    this.metrics = paperMetrics(settings);
    this.setPageSettings(settings);
    new ResizeObserver(() => this.schedule()).observe(content);
    new ResizeObserver(() => this.applyScale()).observe(this.canvas);
    content.addEventListener("load", () => this.schedule(), true);
    void document.fonts.ready.then(() => this.schedule());
  }

  setPageSettings(settings: PageSettings): void {
    this.metrics = paperMetrics(settings);
    const { width, height, top, right, bottom, left } = this.metrics;
    const sizes = {
      "--paper-width": width, "--paper-height": height,
      "--margin-top": top, "--margin-right": right, "--margin-bottom": bottom, "--margin-left": left,
    };
    for (const [name, value] of Object.entries(sizes)) this.layer.style.setProperty(name, value + "px");
    this.applyScale();
    this.schedule();
  }

  schedule(): void {
    if (!this.updateFrame) this.updateFrame = requestAnimationFrame(() => {
      this.updateFrame = 0;
      this.update();
    });
  }

  setZoom(zoom: string): void {
    this.zoom = zoom;
    this.applyScale();
  }

  setPreview(preview: boolean): void {
    this.previewing = preview;
    this.layer.classList.toggle("previewing", preview);
    this.preview.hidden = !preview;
    this.canvas.scrollTop = 0;
    this.update();
  }

  reveal(position: HTMLElement): void {
    if (this.previewing) {
      const y = (position.getBoundingClientRect().top - this.content.getBoundingClientRect().top) / this.scale;
      const index = this.pages.findIndex((page) => y < page.end);
      if (index >= 0) this.goToPage(index);
      return;
    }
    this.canvas.scrollTop += position.getBoundingClientRect().top - this.canvas.getBoundingClientRect().top - 16;
  }

  private goToPage(index: number): void {
    const offset = this.previewing ? (this.preview.children[index] as HTMLElement).offsetTop
      : this.metrics.top + this.pages[index].start;
    this.canvas.scrollTop = index === 0 ? 0 : offset * this.scale;
  }

  private applyScale(): void {
    const { width } = this.metrics;
    this.scale = this.zoom === "fit" ? Math.min(1, Math.max(0.2, (this.canvas.clientWidth - 32) / width)) : Number(this.zoom);
    this.layer.style.transform = `scale(${this.scale})`;
    this.stage.style.width = `${Math.ceil((width + this.overflowWidth) * this.scale)}px`;
    const height = this.previewing ? this.preview.offsetHeight : this.paper.offsetHeight;
    this.stage.style.height = `${Math.ceil(height * this.scale)}px`;
  }

  private update(): void {
    this.applyScale();
    const { bodyHeight, top } = this.metrics;
    const measured = measureDocument(this.content, this.scale, bodyHeight);
    this.pages = paginate(measured.height, bodyHeight, measured.breaks);
    this.overflowWidth = Math.max(0, measured.width - this.content.clientWidth);
    this.warning.textContent = this.pages.some((page) => page.oversized) || this.overflowWidth > 1
      ? "Oversized content extends beyond the paper size." : "";
    this.guides.replaceChildren(...this.pages.slice(1).map((page, index) => {
      const rule = document.createElement("div");
      rule.className = "page-guide";
      rule.style.top = `${top + page.start}px`;
      const label = document.createElement("span");
      label.textContent = `Page ${index + 2}`;
      rule.append(label);
      return rule;
    }));
    this.navigation.replaceChildren(...this.pages.map((page, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `Page ${index + 1}`;
      button.dataset.start = String(Math.round(page.start * 10) / 10);
      button.dataset.end = String(Math.round(page.end * 10) / 10);
      button.addEventListener("click", () => this.goToPage(index));
      return button;
    }));
    this.renderPreview(measured.width);
    this.applyScale();
  }

  private renderPreview(contentWidth: number): void {
    this.observer?.disconnect();
    this.preview.replaceChildren();
    if (!this.previewing) return;
    const { width, height, bodyHeight, top, bottom } = this.metrics;
    this.observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const index = Number((entry.target as HTMLElement).dataset.page);
        const clip = entry.target.firstElementChild!;
        if (entry.isIntersecting) {
          if (clip.childElementCount) continue;
          const snapshot = this.content.cloneNode(true) as HTMLElement;
          snapshot.removeAttribute("contenteditable");
          snapshot.removeAttribute("role");
          snapshot.querySelectorAll(".image-resize-handle").forEach((handle) => handle.remove());
          snapshot.setAttribute("aria-hidden", "true");
          snapshot.style.top = `-${this.pages[index].start}px`;
          snapshot.style.width = `${this.content.clientWidth}px`;
          clip.append(snapshot);
        } else clip.replaceChildren();
      }
    }, { root: this.canvas, rootMargin: "240px" });
    for (const [index, page] of this.pages.entries()) {
      const printPage = document.createElement("article");
      printPage.className = "paper preview-page";
      printPage.dataset.page = String(index);
      printPage.setAttribute("aria-label", `Preview page ${index + 1}`);
      printPage.style.width = `${width + this.overflowWidth}px`;
      const span = page.end - page.start;
      printPage.style.height = `${Math.max(height, top + span + bottom)}px`;
      const clip = document.createElement("div");
      clip.className = "preview-window";
      clip.style.right = "auto";
      clip.style.width = `${contentWidth}px`;
      // Clip at the measured boundary, keeping the rest of an ordinary sheet blank.
      clip.style.height = `${Math.min(Math.max(span, 0), page.oversized ? span : bodyHeight + 0.75)}px`;
      const number = document.createElement("span");
      number.className = "preview-page-number";
      number.textContent = String(index + 1);
      printPage.append(clip);
      if (bottom >= 16) printPage.append(number);
      this.preview.append(printPage);
      this.observer.observe(printPage);
    }
  }
}
