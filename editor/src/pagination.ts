import type { PageSettings } from "./protocol";

const pxPerMillimetre = 96 / 25.4;
const tolerance = 0.75;

export type Page = { start: number; end: number; oversized: boolean };

export function paperMetrics(settings: PageSettings) {
  const [shortSide, longSide] = settings.page_size === "A4" ? [210, 297] : [148, 210];
  const landscape = settings.orientation === "landscape";
  const width = (landscape ? longSide : shortSide) * pxPerMillimetre;
  const height = (landscape ? shortSide : longSide) * pxPerMillimetre;
  const top = settings.margin_top * pxPerMillimetre;
  const right = settings.margin_right * pxPerMillimetre;
  const bottom = settings.margin_bottom * pxPerMillimetre;
  const left = settings.margin_left * pxPerMillimetre;
  return { width, height, top, right, bottom, left, bodyHeight: height - top - bottom };
}

export function paginate(height: number, bodyHeight: number, breakpoints: number[], forcedBreaks: number[] = []): Page[] {
  const forced = new Set(forcedBreaks);
  const breaks = [...new Set([...breakpoints, ...forced])]
    .filter((value) => value > 0 && value < height)
    .sort((a, b) => a - b);
  breaks.push(height);
  const pages: Page[] = [];
  let start = 0;
  let cursor = 0;
  while (cursor < breaks.length) {
    let chosen = cursor;
    while (!forced.has(breaks[chosen]) && chosen + 1 < breaks.length
      && breaks[chosen + 1] <= start + bodyHeight + tolerance) chosen += 1;
    const end = breaks[chosen];
    pages.push({ start, end, oversized: end - start > bodyHeight + tolerance });
    start = end;
    cursor = chosen + 1;
  }
  return pages;
}

type VerticalRange = { start: number; end: number };

function textRanges(block: Element, origin: number, scale: number): VerticalRange[] {
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  const ranges: VerticalRange[] = [];
  const range = document.createRange();
  for (let text = walker.nextNode(); text; text = walker.nextNode()) {
    range.selectNodeContents(text);
    for (const rect of range.getClientRects()) {
      if (rect.height > 0) ranges.push({ start: (rect.top - origin) / scale, end: (rect.bottom - origin) / scale });
    }
  }
  ranges.sort((a, b) => a.start - b.start || a.end - b.end);
  return ranges;
}

function lineBoundaries(ranges: VerticalRange[]): number[] {
  const breaks: number[] = [];
  let previousBottom = -Infinity;
  for (const rect of ranges) {
    if (Number.isFinite(previousBottom) && rect.start >= previousBottom) {
      breaks.push((previousBottom + rect.start) / 2);
    }
    previousBottom = Math.max(previousBottom, rect.end);
  }
  return breaks;
}

function safeBreakpoints(breaks: number[], protectedRanges: VerticalRange[]): number[] {
  const spans: VerticalRange[] = [];
  for (const range of protectedRanges.sort((a, b) => a.start - b.start)) {
    const last = spans.at(-1);
    if (last && range.start < last.end) last.end = Math.max(last.end, range.end);
    else spans.push({ ...range });
  }
  let index = 0;
  return breaks.sort((a, b) => a - b).filter((position) => {
    while (index < spans.length && spans[index].end <= position) index += 1;
    return index === spans.length || position <= spans[index].start;
  });
}

export function measureDocument(content: HTMLElement, scale: number, minimumHeight: number) {
  const surface = content.getBoundingClientRect();
  const breaks: number[] = [];
  const protectedRanges: VerticalRange[] = [];
  const vertical = (edge: number) => (edge - surface.top) / scale;
  const bottom = (element: Element) => vertical(element.getBoundingClientRect().bottom);
  const top = (element: Element) => vertical(element.getBoundingClientRect().top);
  for (const block of content.querySelectorAll("p, h1, h2, h3, li, figure, table")) {
    if (block.matches("table") && !block.parentElement?.closest("table")) {
      breaks.push(top(block), bottom(block));
      const rows = [...(block as HTMLTableElement).rows];
      let spanEndsAt = 0;
      let groupStart = top(block);
      for (const [index, row] of rows.entries()) {
        for (const cell of row.cells) {
          spanEndsAt = Math.max(spanEndsAt, index + (cell.rowSpan || rows.length - index));
        }
        if (spanEndsAt <= index + 1 || index === rows.length - 1) {
          const end = bottom(row);
          breaks.push(end);
          protectedRanges.push({ start: groupStart, end });
          groupStart = end;
        }
      }
    } else if (!block.closest("table")) {
      breaks.push(top(block), bottom(block));
      if (block.matches("p, h1, h2, h3")) {
        const ranges = textRanges(block, surface.top, scale);
        protectedRanges.push(...ranges);
        breaks.push(...lineBoundaries(ranges));
      } else if (block.matches("figure")) {
        protectedRanges.push({ start: top(block), end: bottom(block) });
      }
    }
  }
  // The editable surface reserves one body height even when blank.
  const height = protectedRanges.reduce((extent, range) => Math.max(extent, range.end),
    Math.max(minimumHeight, surface.height / scale, content.scrollHeight));
  return { height, width: Math.max(content.clientWidth, content.scrollWidth), breaks: safeBreakpoints(breaks, protectedRanges),
    forcedBreaks: [...content.querySelectorAll(":scope > .manual-page-break")].map(bottom) };
}
