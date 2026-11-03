/**
 * Browser-safe deterministic SHA-256 helpers for predictive evidence.
 *
 * Values are canonicalized before hashing so object key insertion order cannot
 * change an evidence digest. Unsupported or non-finite values fail closed.
 */

const SHA256_INITIAL = new Uint32Array([
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
  0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]);

const SHA256_K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
  0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
  0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
  0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

// Module-scoped reused buffers and utilities to eliminate per-call heap allocations
const SHA_ENCODER = new TextEncoder();
const SHA256_SCHEDULE = new Uint32Array(64);
const SHA256_STATE = new Uint32Array(8);

function rotateRight(value: number, bits: number): number {
  return (value >>> bits) | (value << (32 - bits));
}

export function canonicalJson(value: unknown): string {
  if (value === null) return 'null';

  const valueType = typeof value;
  if (valueType === 'string' || valueType === 'boolean') {
    return JSON.stringify(value);
  }

  if (valueType === 'number') {
    const num = value as number;
    if (!Number.isFinite(num)) {
      throw new TypeError('Predictive evidence cannot contain non-finite numbers');
    }
    return Object.is(num, -0) ? '0' : JSON.stringify(num);
  }

  if (Array.isArray(value)) {
    // Single-pass string builder avoids intermediate .map() array allocations
    let result = '[';
    const len = value.length;
    for (let index = 0; index < len; index += 1) {
      if (index > 0) result += ',';
      const item = value[index];
      result += item === undefined ? 'null' : canonicalJson(item);
    }
    return `${result}]`;
  }

  if (valueType === 'object') {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new TypeError('Predictive evidence must use plain objects');
    }

    const record = value as Record<string, unknown>;
    // Native lexicographical sorting without intermediate .filter() or .map() passes
    const keys = Object.keys(record).sort();
    let result = '{';
    let isFirstKey = true;
    const keyCount = keys.length;
    for (let index = 0; index < keyCount; index += 1) {
      const key = keys[index];
      const entryVal = record[key];
      if (entryVal !== undefined) {
        if (!isFirstKey) result += ',';
        result += `${JSON.stringify(key)}:${canonicalJson(entryVal)}`;
        isFirstKey = false;
      }
    }
    return `${result}}`;
  }

  throw new TypeError(`Unsupported predictive evidence value: ${typeof value}`);
}

export function sha256Hex(message: string): string {
  const bytes = SHA_ENCODER.encode(message);
  const len = bytes.length;
  const paddedLength = Math.ceil((len + 9) / 64) * 64;
  const data = new Uint8Array(paddedLength);
  data.set(bytes);
  data[len] = 0x80;

  // Encode 64-bit BigEndian length using 32-bit shift operations to avoid BigInt overhead
  const bitLenHi = Math.floor((len * 8) / 0x100000000);
  const bitLenLo = (len * 8) >>> 0;

  data[paddedLength - 8] = (bitLenHi >>> 24) & 0xff;
  data[paddedLength - 7] = (bitLenHi >>> 16) & 0xff;
  data[paddedLength - 6] = (bitLenHi >>> 8) & 0xff;
  data[paddedLength - 5] = bitLenHi & 0xff;

  data[paddedLength - 4] = (bitLenLo >>> 24) & 0xff;
  data[paddedLength - 3] = (bitLenLo >>> 16) & 0xff;
  data[paddedLength - 2] = (bitLenLo >>> 8) & 0xff;
  data[paddedLength - 1] = bitLenLo & 0xff;

  SHA256_STATE.set(SHA256_INITIAL);

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      const position = offset + index * 4;
      SHA256_SCHEDULE[index] = (
        (data[position] << 24) |
        (data[position + 1] << 16) |
        (data[position + 2] << 8) |
        data[position + 3]
      ) >>> 0;
    }

    for (let index = 16; index < 64; index += 1) {
      const value15 = SHA256_SCHEDULE[index - 15];
      const value2 = SHA256_SCHEDULE[index - 2];
      const sigma0 = rotateRight(value15, 7) ^ rotateRight(value15, 18) ^ (value15 >>> 3);
      const sigma1 = rotateRight(value2, 17) ^ rotateRight(value2, 19) ^ (value2 >>> 10);
      SHA256_SCHEDULE[index] = (
        SHA256_SCHEDULE[index - 16] + sigma0 + SHA256_SCHEDULE[index - 7] + sigma1
      ) >>> 0;
    }

    let a = SHA256_STATE[0];
    let b = SHA256_STATE[1];
    let c = SHA256_STATE[2];
    let d = SHA256_STATE[3];
    let e = SHA256_STATE[4];
    let f = SHA256_STATE[5];
    let g = SHA256_STATE[6];
    let h = SHA256_STATE[7];

    for (let index = 0; index < 64; index += 1) {
      const sigma1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temp1 = (h + sigma1 + choice + SHA256_K[index] + SHA256_SCHEDULE[index]) >>> 0;
      const sigma0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (sigma0 + majority) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    SHA256_STATE[0] = (SHA256_STATE[0] + a) >>> 0;
    SHA256_STATE[1] = (SHA256_STATE[1] + b) >>> 0;
    SHA256_STATE[2] = (SHA256_STATE[2] + c) >>> 0;
    SHA256_STATE[3] = (SHA256_STATE[3] + d) >>> 0;
    SHA256_STATE[4] = (SHA256_STATE[4] + e) >>> 0;
    SHA256_STATE[5] = (SHA256_STATE[5] + f) >>> 0;
    SHA256_STATE[6] = (SHA256_STATE[6] + g) >>> 0;
    SHA256_STATE[7] = (SHA256_STATE[7] + h) >>> 0;
  }

  // Direct hex formatting eliminates Array.from().join() allocation overhead
  let hexResult = '';
  for (let index = 0; index < 8; index += 1) {
    hexResult += SHA256_STATE[index].toString(16).padStart(8, '0');
  }
  return hexResult;
}

export function hashCanonical(value: unknown): string {
  return sha256Hex(canonicalJson(value));
}
