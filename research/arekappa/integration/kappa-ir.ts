export const KAPPA_SCALE = 1_000_000n;

export function normalizeWeightsLargestRemainder(
  weights: readonly bigint[],
  scale: bigint = KAPPA_SCALE,
): readonly bigint[] {
  if (scale <= 0n) throw new Error("scale must be positive");
  if (weights.length === 0) throw new Error("weights must not be empty");
  if (weights.some((value) => value < 0n)) throw new Error("weights must be non-negative");

  const total = weights.reduce((sum, value) => sum + value, 0n);
  if (total <= 0n) throw new Error("weight sum must be positive");

  const numerators = weights.map((value) => value * scale);
  const floors = numerators.map((numerator) => numerator / total);
  let remaining = scale - floors.reduce((sum, value) => sum + value, 0n);
  const order = weights.map((_, index) => index).sort((left, right) => {
    const leftRemainder = numerators[left] % total;
    const rightRemainder = numerators[right] % total;
    if (leftRemainder === rightRemainder) return left - right;
    return leftRemainder > rightRemainder ? -1 : 1;
  });
  for (const index of order) {
    if (remaining === 0n) break;
    floors[index] += 1n;
    remaining -= 1n;
  }
  return floors;
}

export function matrixVectorProduct(
  matrix: readonly (readonly bigint[])[],
  vector: readonly bigint[],
): readonly bigint[] {
  if (matrix.length === 0 || vector.length === 0 || matrix.some((row) => row.length !== vector.length)) {
    throw new Error("matrix and vector dimensions must be non-empty and compatible");
  }
  return matrix.map((row) => row.reduce((sum, coefficient, index) => sum + coefficient * vector[index], 0n));
}

function normalizeJson(value: unknown): unknown {
  if (value === null || typeof value === "boolean" || typeof value === "string") return value;
  if (typeof value === "bigint") return value.toString(10);
  if (typeof value === "number") throw new Error("JavaScript numbers are forbidden in canonical AREKappa JSON");
  if (Array.isArray(value)) return value.map(normalizeJson);
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return Object.fromEntries(Object.keys(record).sort().map((key) => [key, normalizeJson(record[key])]));
  }
  throw new Error(`unsupported canonical JSON value: ${typeof value}`);
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(normalizeJson(value));
}
