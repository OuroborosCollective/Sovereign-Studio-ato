import { createHash } from "node:crypto";

const MAX_TOOLS = 500;
const MAX_CATALOG_BYTES = 2_000_000;

export function validateLoopbackTarget(raw) {
  if (typeof raw !== "string" || raw.length > 256) throw new Error("INVALID_ENDPOINT");
  let url;
  try { url = new URL(raw); } catch { throw new Error("INVALID_ENDPOINT"); }
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" ||
      url.pathname !== "/mcp" || !url.port ||
      url.username || url.password || url.search || url.hash ||
      raw !== `http://127.0.0.1:${url.port}/mcp`) {
    throw new Error("NON_LOOPBACK_OR_NONCANONICAL_ENDPOINT");
  }
  return raw;
}

function normalizeJson(value, depth = 0, ancestors = new WeakSet()) {
  if (depth > 32) throw new Error("SCHEMA_TOO_DEEP");
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (!value || typeof value !== "object") throw new Error("NON_JSON_SCHEMA");
  if (ancestors.has(value)) throw new Error("CYCLIC_SCHEMA");
  ancestors.add(value);
  let result;
  if (Array.isArray(value)) {
    result = value.map((item) => normalizeJson(item, depth + 1, ancestors));
  } else {
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null) throw new Error("NON_PLAIN_JSON_SCHEMA");
    result = {};
    for (const key of Object.keys(value).sort()) {
      result[key] = normalizeJson(value[key], depth + 1, ancestors);
    }
  }
  ancestors.delete(value);
  return result;
}

export function inventoryFingerprint(tools) {
  if (!Array.isArray(tools) || tools.length < 1 || tools.length > MAX_TOOLS) {
    throw new Error("INVALID_TOOL_COUNT");
  }
  const names = new Set();
  const normalized = tools.map((tool) => {
    if (!tool || typeof tool !== "object" || Array.isArray(tool) ||
        typeof tool.name !== "string" || !/^[a-zA-Z0-9_.:-]{1,128}$/.test(tool.name) ||
        names.has(tool.name) || !Object.hasOwn(tool, "inputSchema")) {
      throw new Error("INVALID_TOOL_DEFINITION");
    }
    names.add(tool.name);
    return {
      name: tool.name,
      description: typeof tool.description === "string" ? tool.description : "",
      inputSchema: normalizeJson(tool.inputSchema),
      outputSchema: tool.outputSchema === undefined ? null : normalizeJson(tool.outputSchema),
    };
  }).sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
  const bytes = Buffer.from(JSON.stringify(normalized), "utf8");
  if (bytes.length > MAX_CATALOG_BYTES) throw new Error("TOOL_CATALOG_TOO_LARGE");
  return {
    schemaVersion: "mcp-use.readonly-inventory.v1",
    authority: "METADATA_ONLY",
    count: normalized.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
  };
}
