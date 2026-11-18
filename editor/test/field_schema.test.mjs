import assert from "node:assert/strict";
import { test } from "node:test";
import { parseField, parseFields } from "../src/field_schema.ts";

const currency = {
  id: "ab".repeat(16), key: "deposit", label: "押金 · Deposit", type: "currency",
  required: true, default: "125.50", validation: { min: "0", max: "999.99" },
  formatting: { style: "symbol" },
};

test("currency and Unicode survive unchanged", () => {
  assert.deepEqual(parseField(currency), currency);
  assert.throws(() => parseField({ ...currency, default: "125.505" }), /2 decimal/);
  assert.throws(() => parseField({ ...currency, default: "999.991" }), /2 decimal/);
  assert.throws(() => parseField({ ...currency, default: "1000.00" }), /allowed range/);
});

test("registry rejects duplicate IDs and keys and unknown types", () => {
  assert.throws(() => parseFields([currency, { ...currency, id: "12".repeat(16) }]), /unique/);
  assert.throws(() => parseFields([currency, { ...currency, key: "other" }]), /unique/);
  assert.throws(() => parseField({ ...currency, type: "unsupported" }), /Invalid field type/);
  assert.throws(() => parseField({ ...currency, validation: { regex: ".*" } }), /Unsupported/);
});

test("date range and dropdown defaults must match their rules", () => {
  const range = {
    ...currency, type: "date_range", default: { start: "2028-02-29", end: "2028-03-01" },
    validation: {}, formatting: { style: "dmy" },
  };
  assert.deepEqual(parseField(range), range);
  assert.throws(() => parseField({ ...range, default: { start: "2027-02-29", end: "2027-03-01" } }), /valid date/);
  const dropdown = { ...currency, type: "dropdown", default: "A", validation: { options: ["A", "B"] }, formatting: {} };
  assert.deepEqual(parseField(dropdown), dropdown);
  assert.throws(() => parseField({ ...dropdown, default: "C" }), /listed default/);
});
