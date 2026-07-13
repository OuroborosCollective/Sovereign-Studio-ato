declare const KAPPA_POS_BRAND: unique symbol;
declare const MICRO_USD_BRAND: unique symbol;

export type KappaPos = bigint & {
  readonly [KAPPA_POS_BRAND]: 'KappaPos';
};

export type MicroUsd = bigint & {
  readonly [MICRO_USD_BRAND]: 'MicroUsd';
};

export const KAPPA_SCALE = 1_000_000n;
export const KAPPA_ZERO = 0n as KappaPos;
export const KAPPA_ONE = KAPPA_SCALE as KappaPos;

const KAPPA_VECTOR_MAGIC = new Uint8Array([0x4b, 0x50, 0x4f, 0x53]); // KPOS
const KAPPA_VECTOR_VERSION = 1;
const KAPPA_VECTOR_HEADER_BYTES = 16;
const KAPPA_VECTOR_VALUE_BYTES = 8;
const UINT64_MAX = (1n << 64n) - 1n;
const FNV64_OFFSET_BASIS = 14_695_981_039_346_656_037n;
const FNV64_PRIME = 1_099_511_628_211n;
const UINT64_MASK = UINT64_MAX;

function assertKappaUnits(value: bigint): void {
  if (value < 0n || value > KAPPA_SCALE) {
    throw new RangeError(`KappaPos muss zwischen 0 und ${KAPPA_SCALE} liegen.`);
  }
}

export function kappaFromUnits(value: bigint): KappaPos {
  assertKappaUnits(value);
  return value as KappaPos;
}

/**
 * Liest ausschließlich kanonischen Dezimaltext. Zusätzliche Nachkommastellen
 * werden deterministisch in Richtung null auf sechs Kappa-Stellen gekürzt.
 */
export function kappaFromDecimalString(value: string): KappaPos {
  const match = /^(0|1)(?:\.([0-9]+))?$/.exec(value);
  if (!match) {
    throw new TypeError(`Ungültiger Kappa-Dezimaltext: ${value}`);
  }

  const whole = match[1];
  const fraction = match[2] ?? '';

  if (whole === '1' && /[1-9]/.test(fraction)) {
    throw new RangeError('KappaPos darf 1.000000 nicht überschreiten.');
  }

  const fractionalUnits = BigInt(fraction.slice(0, 6).padEnd(6, '0') || '0');
  const units = BigInt(whole) * KAPPA_SCALE + fractionalUnits;
  return kappaFromUnits(units);
}

export function kappaToDecimalString(value: KappaPos): string {
  assertKappaUnits(value);
  const whole = value / KAPPA_SCALE;
  const fraction = (value % KAPPA_SCALE).toString().padStart(6, '0');
  return `${whole}.${fraction}`;
}

export function multiplyKappa(left: KappaPos, right: KappaPos): KappaPos {
  return kappaFromUnits((left * right) / KAPPA_SCALE);
}

export function subtractKappa(left: KappaPos, right: KappaPos): KappaPos {
  if (right > left) {
    throw new RangeError('KappaPos-Subtraktion darf nicht negativ werden.');
  }
  return kappaFromUnits(left - right);
}

export function microUsdFromUnits(value: bigint): MicroUsd {
  if (value < 0n) {
    throw new RangeError('MicroUsd darf nicht negativ sein.');
  }
  return value as MicroUsd;
}

/** Deterministische ganzzahlige Quadratwurzel, abgerundet. */
export function integerSqrt(value: bigint): bigint {
  if (value < 0n) {
    throw new RangeError('integerSqrt akzeptiert keine negativen Werte.');
  }
  if (value < 2n) {
    return value;
  }

  let current = value;
  let next = (current + 1n) >> 1n;
  while (next < current) {
    current = next;
    next = (current + value / current) >> 1n;
  }
  return current;
}

/**
 * Kosinusähnlichkeit als KappaPos. Alle Multiplikationen, Normen und die
 * Quadratwurzel bleiben vollständig im BigInt-Raum.
 */
export function cosineSimilarityKappa(
  left: readonly KappaPos[],
  right: readonly KappaPos[],
): KappaPos {
  const length = left.length < right.length ? left.length : right.length;
  let dotProduct = 0n;
  let leftNormSquared = 0n;
  let rightNormSquared = 0n;

  for (let index = 0; index < length; index += 1) {
    const leftValue = left[index];
    const rightValue = right[index];
    dotProduct += leftValue * rightValue;
    leftNormSquared += leftValue * leftValue;
    rightNormSquared += rightValue * rightValue;
  }

  if (leftNormSquared === 0n || rightNormSquared === 0n) {
    return KAPPA_ZERO;
  }

  const denominator = integerSqrt(leftNormSquared * rightNormSquared);
  if (denominator === 0n) {
    return KAPPA_ZERO;
  }

  const scaled = (dotProduct * KAPPA_SCALE) / denominator;
  return kappaFromUnits(scaled > KAPPA_SCALE ? KAPPA_SCALE : scaled);
}

/**
 * Kanonisches SQLite/R2-Vektorformat:
 * KPOS-Magic, uint16 Version, uint16 Headergröße, uint32 Scale,
 * uint32 Länge und danach uint64-Werte; sämtliche Zahlen Little-Endian.
 */
export function encodeKappaVectorLittleEndian(
  values: readonly KappaPos[],
): Uint8Array {
  const output = new Uint8Array(
    KAPPA_VECTOR_HEADER_BYTES + values.length * KAPPA_VECTOR_VALUE_BYTES,
  );
  output.set(KAPPA_VECTOR_MAGIC, 0);

  const view = new DataView(output.buffer, output.byteOffset, output.byteLength);
  view.setUint16(4, KAPPA_VECTOR_VERSION, true);
  view.setUint16(6, KAPPA_VECTOR_HEADER_BYTES, true);
  view.setUint32(8, Number(KAPPA_SCALE), true);
  view.setUint32(12, values.length, true);

  values.forEach((value, index) => {
    assertKappaUnits(value);
    view.setBigUint64(
      KAPPA_VECTOR_HEADER_BYTES + index * KAPPA_VECTOR_VALUE_BYTES,
      value,
      true,
    );
  });

  return output;
}

export function decodeKappaVectorLittleEndian(bytes: Uint8Array): KappaPos[] {
  if (bytes.byteLength < KAPPA_VECTOR_HEADER_BYTES) {
    throw new RangeError('Kappa-Vektor ist kürzer als der kanonische Header.');
  }

  for (let index = 0; index < KAPPA_VECTOR_MAGIC.length; index += 1) {
    if (bytes[index] !== KAPPA_VECTOR_MAGIC[index]) {
      throw new TypeError('Kappa-Vektor besitzt kein gültiges KPOS-Magic.');
    }
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const version = view.getUint16(4, true);
  const headerBytes = view.getUint16(6, true);
  const scale = view.getUint32(8, true);
  const length = view.getUint32(12, true);

  if (version !== KAPPA_VECTOR_VERSION) {
    throw new RangeError(`Nicht unterstützte Kappa-Vektor-Version: ${version}`);
  }
  if (headerBytes !== KAPPA_VECTOR_HEADER_BYTES) {
    throw new RangeError(`Ungültige Kappa-Headergröße: ${headerBytes}`);
  }
  if (BigInt(scale) !== KAPPA_SCALE) {
    throw new RangeError(`Ungültige Kappa-Skalierung: ${scale}`);
  }

  const expectedBytes = headerBytes + length * KAPPA_VECTOR_VALUE_BYTES;
  if (bytes.byteLength !== expectedBytes) {
    throw new RangeError(
      `Kappa-Vektorlänge stimmt nicht: ${bytes.byteLength} statt ${expectedBytes}.`,
    );
  }

  const values: KappaPos[] = [];
  for (let index = 0; index < length; index += 1) {
    values.push(
      kappaFromUnits(
        view.getBigUint64(
          headerBytes + index * KAPPA_VECTOR_VALUE_BYTES,
          true,
        ),
      ),
    );
  }
  return values;
}

export function fnv1a64Hex(input: string | Uint8Array): string {
  const bytes = typeof input === 'string' ? new TextEncoder().encode(input) : input;
  let hash = FNV64_OFFSET_BASIS;
  for (const byte of bytes) {
    hash ^= BigInt(byte);
    hash = (hash * FNV64_PRIME) & UINT64_MASK;
  }
  return hash.toString(16).padStart(16, '0');
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new Error('WebCrypto SubtleCrypto ist für SHA-256 nicht verfügbar.');
  }

  const digest = await subtle.digest('SHA-256', new Uint8Array(bytes));
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');
}
