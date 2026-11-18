export const fieldTypes = {
  text: "Text", multiline: "Multiline Text", number: "Number", currency: "Currency (MYR)",
  date: "Date", date_range: "Date Range", dropdown: "Dropdown", checkbox: "Checkbox",
  boolean: "Boolean", phone: "Phone", email: "Email", address: "Address",
};
export type FieldType = keyof typeof fieldTypes;
type DateRange = { start: string; end: string };
export type FieldDefinition = {
  id: string; key: string; label: string; type: FieldType; required: boolean;
  default: string | boolean | DateRange | null;
  validation: { min_length?: number; max_length?: number; min?: string; max?: string; options?: string[] };
  formatting: { style?: string; decimals?: number };
};

export const fieldIdPattern = /^[0-9a-f]{32}$/;
export const textTypes = new Set(["text", "multiline", "phone", "email", "address"]);
export const numericTypes = new Set(["number", "currency"]);
export const dateTypes = new Set(["date", "date_range"]);
export const flagTypes = new Set(["checkbox", "boolean"]);

export function displayStyles(kind: FieldType): [string, string][] {
  if (textTypes.has(kind)) return [["upper", "Uppercase"], ["lower", "Lowercase"]];
  if (dateTypes.has(kind)) return [["iso", "YYYY-MM-DD"], ["dmy", "DD/MM/YYYY"], ["long", "Long date"]];
  if (flagTypes.has(kind)) return [["yes_no", "Yes / No"], ["true_false", "True / False"]];
  return kind === "currency" ? [["symbol", "RM symbol"], ["code", "MYR code"]] : [];
}

function object(value: unknown, allowed: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || Object.keys(value).some((key) => !allowed.includes(key))) {
    throw new Error("Unsupported field property or rule.");
  }
  return value as Record<string, unknown>;
}

function length(value: unknown, max: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= max;
}

function string(value: unknown, message: string): string {
  if (typeof value !== "string") throw new Error(message);
  return value;
}

function decimal(value: unknown, kind: string): bigint {
  const fraction = kind === "currency" ? 2 : 6;
  const raw = string(value, "Enter a decimal value.");
  if (!new RegExp("^-?[0-9]{1,15}(?:\\.[0-9]{1," + fraction + "})?$").test(raw)) {
    throw new Error("Enter a decimal value with up to " + fraction + " decimal places.");
  }
  const [whole, part = ""] = raw.replace(/^-/, "").split(".");
  const magnitude = BigInt(whole + part.padEnd(6, "0"));
  return raw.startsWith("-") ? -magnitude : magnitude;
}

function date(value: unknown): string {
  const raw = string(value, "Use YYYY-MM-DD.");
  const parsed = new Date(raw + "T00:00:00Z");
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(raw) || raw.startsWith("0000") ||
      !Number.isFinite(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== raw) {
    throw new Error("Enter a valid date in YYYY-MM-DD format.");
  }
  return raw;
}

function bounds<T extends bigint | number | string>(low: T | undefined, high: T | undefined, values: T[]): void {
  if (low !== undefined && high !== undefined && low > high) throw new Error("Minimum exceeds maximum.");
  if (values.some((value) => (low !== undefined && value < low) || (high !== undefined && value > high))) {
    throw new Error("The default falls outside the allowed range.");
  }
}

export function parseField(value: unknown): FieldDefinition {
  const field = object(value, ["id", "key", "label", "type", "required", "default", "validation", "formatting"]);
  if (typeof field.id !== "string" || !fieldIdPattern.test(field.id)) throw new Error("Invalid field ID.");
  if (typeof field.key !== "string" || !/^[a-z][a-z0-9_]{0,63}$/.test(field.key)) {
    throw new Error("Use a lowercase letter first, followed by lowercase letters, digits or underscores.");
  }
  if (typeof field.label !== "string" || !field.label.trim() || Array.from(field.label).length > 120) {
    throw new Error("Enter a label of up to 120 characters.");
  }
  if (typeof field.type !== "string" || !Object.hasOwn(fieldTypes, field.type) || typeof field.required !== "boolean"
      || !Object.hasOwn(field, "default")) throw new Error("Invalid field type or configuration.");
  const kind = field.type as FieldType;
  const allowed = textTypes.has(kind) ? ["min_length", "max_length"] : numericTypes.has(kind) || dateTypes.has(kind)
    ? ["min", "max"] : kind === "dropdown" ? ["options"] : [];
  const rules = object(field.validation, allowed);
  const format = object(field.formatting, ["style", "decimals"]);
  if ("style" in format && !displayStyles(kind).some(([style]) => style === format.style)) throw new Error("Unsupported display style.");
  if ("decimals" in format && (kind !== "number" || !length(format.decimals, 6))) throw new Error("Enter 0–6 display decimals for Number.");

  const initial = field.default;
  if (flagTypes.has(kind)) {
    if (initial !== null && typeof initial !== "boolean") throw new Error("Choose a boolean default.");
  } else if (kind === "date_range" || kind === "date") {
    const defaults = [];
    if (initial !== null) {
      if (kind === "date") defaults.push(date(initial));
      else {
        const range = object(initial, ["start", "end"]);
        defaults.push(date(range.start), date(range.end));
        if (defaults[0] > defaults[1]) throw new Error("The end date must not precede the start date.");
      }
    }
    bounds("min" in rules ? date(rules.min) : undefined, "max" in rules ? date(rules.max) : undefined, defaults);
  } else if (numericTypes.has(kind)) {
    bounds("min" in rules ? decimal(rules.min, kind) : undefined,
      "max" in rules ? decimal(rules.max, kind) : undefined, initial === null ? [] : [decimal(initial, kind)]);
  } else if (kind === "dropdown") {
    const options = rules.options;
    if (!Array.isArray(options) || !options.length || options.length > 100 || new Set(options).size !== options.length
        || options.some((option) => typeof option !== "string" || !option.trim() || Array.from(option).length > 120)) {
      throw new Error("Enter distinct dropdown choices, one per line.");
    }
    if (initial !== null && !options.includes(initial)) throw new Error("Choose a listed default.");
  } else {
    const minimum = rules.min_length, maximum = rules.max_length;
    if (("min_length" in rules && !length(minimum, 4000)) || ("max_length" in rules && !length(maximum, 4000))) {
      throw new Error("Enter a length between 0 and 4000.");
    }
    const raw = initial === null ? null : string(initial, "Enter a text default.");
    const size = raw === null ? 0 : Array.from(raw).length;
    bounds(minimum as number | undefined, maximum as number | undefined, raw === null ? [] : [size]);
    if (raw !== null) {
      if (size > 4000 || (kind !== "multiline" && kind !== "address" && /[\r\n]/.test(raw))) {
        throw new Error("The text default is too long or contains a line break.");
      }
      if (kind === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/u.test(raw)) throw new Error("Enter an email address.");
      if (kind === "phone" && (!/^\+?[0-9 ().-]+$/.test(raw) || !/^.{3,20}$/.test(raw.replace(/\D/g, "")))) {
        throw new Error("Enter a phone number.");
      }
    }
  }
  return field as FieldDefinition;
}

export function parseFields(value: unknown): FieldDefinition[] {
  if (!Array.isArray(value) || value.length > 200) throw new Error("Use up to 200 fields.");
  const fields = value.map(parseField);
  if (new Set(fields.map(({ id }) => id)).size !== fields.length || new Set(fields.map(({ key }) => key)).size !== fields.length) {
    throw new Error("Each field key and ID must be unique.");
  }
  return fields;
}
