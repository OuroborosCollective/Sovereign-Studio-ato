/**
 * Configuration Provenance - Canonicalization & Merge Semantics
 *
 * Deterministic serialization and merge rules so that identical input always
 * produces a byte-identical receipt hash.
 *
 * Merge semantics (later/higher-priority source wins):
 *  - Object: deep-merge recursively.
 *  - Array: replace wholesale (no element-level merge) - arrays are opaque.
 *  - null: explicit delete. A `null` from a higher-priority source removes the
 *    key entirely from the resolved projection (it does NOT appear as null).
 *  - missing: a key absent from a source does not affect the resolved value.
 *  - RedactedSecret: carried through as a redacted identity; never expanded.
 *
 * @module runtime/config/configCanonicalize
 */

import type { RedactedSecret } from './configSources';

/**
 * Determine whether a value is a redacted-secret identity.
 */
export function isRedactedSecret(value: unknown): value is RedactedSecret {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { kind?: unknown }).kind === 'secret' &&
    typeof (value as { redactedId?: unknown }).redactedId === 'string'
  );
}

/**
 * Deterministic JSON canonicalization.
 *
 * Sorts object keys lexicographically and produces stable output for numbers,
 * strings, booleans, null, arrays and nested objects. `undefined` fields are
 * omitted. This guarantees byte-identical output for structurally equal input
 * regardless of insertion order.
 */
export function canonicalJson(value: unknown): string {
  return serializeStable(value);
}

function serializeStable(value: unknown): string {
  if (value === null) return 'null';
  if (value === undefined) return 'null';
  const type = typeof value;
  if (type === 'string') return JSON.stringify(value);
  if (type === 'number') {
    // JSON.stringify handles Number formatting (incl. Infinity -> null).
    return Number.isFinite(value as number) ? String(value as number) : 'null';
  }
  if (type === 'boolean') return value ? 'true' : 'false';
  if (type === 'bigint') return JSON.stringify(String(value));
  if (isRedactedSecret(value)) {
    // Redacted identity is safe to serialize - it carries no secret material.
    // Serialize inline to avoid re-entering isRedactedSecret (infinite recursion).
    return '{"kind":"secret","redactedId":' + JSON.stringify(value.redactedId) + '}';
  }
  if (Array.isArray(value)) {
    return '[' + value.map(serializeStable).join(',') + ']';
  }
  if (type === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    const parts: string[] = [];
    for (const key of keys) {
      if (obj[key] === undefined) continue;
      parts.push(JSON.stringify(key) + ':' + serializeStable(obj[key]));
    }
    return '{' + parts.join(',') + '}';
  }
  // Unknown types (functions, symbols) are not representable in config.
  return 'null';
}

/**
 * Deep-merge a higher-priority source onto an accumulator, honoring the
 * explicit-delete (null) and array-replace semantics.
 *
 * Returns a new object; inputs are not mutated.
 */
export function mergeValues(
  base: Readonly<Record<string, unknown>>,
  overlay: Readonly<Record<string, unknown>>,
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  for (const key of Object.keys(overlay)) {
    const overlayValue = overlay[key];
    // Explicit delete: null removes the key entirely.
    if (overlayValue === null) {
      delete result[key];
      continue;
    }
    if (overlayValue === undefined) {
      // Missing / undefined: do not touch the resolved value.
      continue;
    }
    const baseValue = result[key];
    if (
      isPlainObject(baseValue) &&
      isPlainObject(overlayValue) &&
      !isRedactedSecret(baseValue) &&
      !isRedactedSecret(overlayValue)
    ) {
      result[key] = mergeValues(
        baseValue as Readonly<Record<string, unknown>>,
        overlayValue as Readonly<Record<string, unknown>>,
      );
    } else {
      // Arrays, scalars, redacted secrets: replace wholesale.
      result[key] = overlayValue;
    }
  }
  return result;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null) return false;
  if (Array.isArray(value)) return false;
  if (isRedactedSecret(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * Compute a schema hash for a field descriptor list. Identical field sets
 * produce identical hashes regardless of declaration order.
 */
export function schemaHashFromFields(
  fields: ReadonlyArray<{ readonly name: string; readonly kind: string }>,
): string {
  // Stable: sort fields by name, serialize deterministically.
  const sorted = [...fields].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  const serialized = sorted.map(f => `${f.name}:${f.kind}`).join('|');
  return stableHashPrefix + shortHash(serialized);
}

/** sha256 hex of a value's canonical JSON. Async (WebCrypto SubtleCrypto). */
export async function hashValue(value: unknown): Promise<string> {
  const data = new TextEncoder().encode(canonicalJson(value));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', data);
  return bufferToHex(digest);
}

/** sha256 hex of a UTF-8 string. */
export async function hashString(value: string): Promise<string> {
  const data = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', data);
  return bufferToHex(digest);
}

function bufferToHex(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let hex = '';
  for (let i = 0; i < bytes.length; i += 1) {
    hex += bytes[i].toString(16).padStart(2, '0');
  }
  return hex;
}

/**
 * A short, non-cryptographic fold used only for schema-hash derivation where
 * collision resistance beyond the field-list identity is not required (the
 * schema is also bound by name in the source contract). Uses FNV-1a 64-bit-ish
 * folding into a 16-hex-char segment. This keeps schema hashes deterministic
 * without an async dependency, while content/resolved hashes use full sha256.
 */
function shortHash(input: string): string {
  let h1 = 0x811c9dc5;
  let h2 = 0x1000193;
  for (let i = 0; i < input.length; i += 1) {
    const c = input.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
    h2 = Math.imul(h2 ^ (c + 0x9e3779b9), 0x85ebca6b) >>> 0;
  }
  return (h1 >>> 0).toString(16).padStart(8, '0') + (h2 >>> 0).toString(16).padStart(8, '0');
}

const stableHashPrefix = 'sch-';
