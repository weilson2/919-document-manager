import assert from "node:assert/strict";
import { test } from "node:test";
import { paginate, paperMetrics } from "../src/pagination.ts";

test("manual page breaks keep all measured content in flow", () => {
  const pages = paginate(270, 100, [20, 35, 60, 75, 100, 155, 205, 255], [35, 205]);
  assert.deepEqual(pages.map(({ start, end }) => [start, end]), [[0, 35], [35, 100], [100, 155], [155, 205], [205, 270]]);
});

test("oversized unbreakable content remains in the document", () => {
  const pages = paginate(250, 100, [25, 225]);
  assert.equal(pages[1].oversized, true);
  assert.equal(pages[1].end - pages[1].start, 200);
});

test("paper metrics honor A5 landscape and custom margins", () => {
  const settings = { page_size: "A5", orientation: "landscape", margin_top: 10, margin_bottom: 15,
    margin_left: 20, margin_right: 20 };
  const paper = paperMetrics(settings);
  assert.ok(paper.width > paper.height);
  assert.ok(Math.abs(paper.bodyHeight * 25.4 / 96 - 123) < 0.01);
});
