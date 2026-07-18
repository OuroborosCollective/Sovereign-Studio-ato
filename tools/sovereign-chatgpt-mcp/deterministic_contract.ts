import { createHash } from 'node:crypto';

export const KAPPA_SCALE = 1_000_000n;
export const MAX_CANONICAL_BYTES = 250_000;
export const MAX_REPLAY_ACTIONS = 100;

const STATE_METADATA_FIELDS = new Set([
  'stateHash',
  'actionHash',
  'chainHash',
  'previousChainHash',
]);

type CanonicalPrimitive = null | boolean | bigint | string;
export type CanonicalValue =
  | CanonicalPrimitive
  | CanonicalValue[]
  | { [key: string]: CanonicalValue };

export type CanonicalObject = { [key: string]: CanonicalValue };
export type TransitionTable = { [state: string]: { [action: string]: string } };

function assertNoUnpairedSurrogate(value: string, path: string): void {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new RangeError(`${path} contains an unpaired Unicode surrogate`);
      }
      index += 1;
      continue;
    }
    if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw new RangeError(`${path} contains an unpaired Unicode surrogate`);
    }
  }
}

function normalizeText(value: string, path: string): string {
  const normalized = value.normalize('NFC');
  assertNoUnpairedSurrogate(normalized, path);
  return normalized;
}

function compareUtf16(left: string, right: string): number {
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

export function canonicalDecimalToUnits(
  value: string,
  options: { signed?: boolean } = {},
): bigint {
  const signed = options.signed ?? true;
  const raw = normalizeText(String(value ?? '').trim(), 'value');
  const match = /^(-?)(0|[1-9][0-9]*)(?:\.([0-9]+))?$/.exec(raw);
  if (!match) {
    throw new TypeError('value must be canonical decimal text');
  }
  const negative = match[1] === '-';
  if (negative && !signed) {
    throw new RangeError('negative values are not allowed');
  }
  const whole = BigInt(match[2]);
  const fraction = match[3] ?? '';
  const fractionalUnits = BigInt(fraction.slice(0, 6).padEnd(6, '0') || '0');
  const units = whole * KAPPA_SCALE + fractionalUnits;
  return negative && units !== 0n ? -units : units;
}

export function truncDivTowardZero(numerator: bigint, denominator: bigint): bigint {
  if (denominator === 0n) {
    throw new RangeError('division by zero');
  }
  return numerator / denominator;
}

export function multiplyFixed(left: bigint, right: bigint): bigint {
  return truncDivTowardZero(left * right, KAPPA_SCALE);
}

export function divideFixed(left: bigint, right: bigint): bigint {
  return truncDivTowardZero(left * KAPPA_SCALE, right);
}

export function canonicalValue(value: unknown, path = '$'): CanonicalValue {
  if (value === null || typeof value === 'boolean' || typeof value === 'bigint') {
    return value;
  }
  if (typeof value === 'number') {
    throw new TypeError(
      `${path} contains a number; use bigint scaled integers or canonical decimal text`,
    );
  }
  if (typeof value === 'string') {
    return normalizeText(value, path);
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => canonicalValue(item, `${path}[${index}]`));
  }
  if (!isPlainObject(value)) {
    throw new TypeError(`${path} contains an unsupported value`);
  }

  const entries = new Map<string, unknown>();
  for (const [rawKey, item] of Object.entries(value)) {
    const normalizedKey = normalizeText(rawKey, `${path}.<key>`);
    if (entries.has(normalizedKey)) {
      throw new RangeError(`${path} contains duplicate keys after Unicode normalization`);
    }
    entries.set(normalizedKey, item);
  }

  const normalized: CanonicalObject = {};
  for (const key of [...entries.keys()].sort(compareUtf16)) {
    normalized[key] = canonicalValue(entries.get(key), `${path}.${key}`);
  }
  return normalized;
}

function canonicalStringifyNormalized(value: CanonicalValue): string {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'bigint') return value.toString(10);
  if (typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) {
    return `[${value.map(canonicalStringifyNormalized).join(',')}]`;
  }
  const keys = Object.keys(value).sort(compareUtf16);
  return `{${keys
    .map((key) => `${JSON.stringify(key)}:${canonicalStringifyNormalized(value[key])}`)
    .join(',')}}`;
}

export function canonicalBytes(value: unknown): Uint8Array {
  const normalized = canonicalValue(value);
  const bytes = new TextEncoder().encode(canonicalStringifyNormalized(normalized));
  if (bytes.byteLength > MAX_CANONICAL_BYTES) {
    throw new RangeError('canonical payload exceeds the bounded size limit');
  }
  return bytes;
}

export function canonicalSha256(value: unknown): string {
  return createHash('sha256').update(canonicalBytes(value)).digest('hex');
}

export function stateSha256(value: unknown): string {
  const normalized = canonicalValue(value);
  if (!isPlainObject(normalized)) {
    throw new TypeError('state must be a mapping');
  }
  const payload: CanonicalObject = {};
  for (const key of Object.keys(normalized).sort(compareUtf16)) {
    if (!STATE_METADATA_FIELDS.has(key)) {
      payload[key] = normalized[key];
    }
  }
  return canonicalSha256(payload);
}

export function normalizeTransitionTable(value: unknown): TransitionTable {
  if (!isPlainObject(value) || Object.keys(value).length === 0) {
    throw new TypeError('transition_table must be a non-empty mapping');
  }

  const tableEntries = new Map<string, Record<string, unknown>>();
  for (const [rawState, rawActions] of Object.entries(value)) {
    if (!rawState.trim()) {
      throw new TypeError('transition state names must be non-empty strings');
    }
    if (!isPlainObject(rawActions) || Object.keys(rawActions).length === 0) {
      throw new TypeError('each transition state must contain action mappings');
    }
    const state = normalizeText(rawState.trim(), 'transition state');
    if (tableEntries.has(state)) {
      throw new RangeError('duplicate transition state after normalization');
    }
    tableEntries.set(state, rawActions);
  }

  const output: TransitionTable = {};
  for (const state of [...tableEntries.keys()].sort(compareUtf16)) {
    const actionEntries = new Map<string, string>();
    for (const [rawAction, rawTarget] of Object.entries(tableEntries.get(state)!)) {
      if (!rawAction.trim()) {
        throw new TypeError('transition action names must be non-empty strings');
      }
      if (typeof rawTarget !== 'string' || !rawTarget.trim()) {
        throw new TypeError('transition targets must be non-empty strings');
      }
      const action = normalizeText(rawAction.trim(), 'transition action');
      const target = normalizeText(rawTarget.trim(), 'transition target');
      if (actionEntries.has(action)) {
        throw new RangeError('duplicate transition action after normalization');
      }
      actionEntries.set(action, target);
    }
    output[state] = {};
    for (const action of [...actionEntries.keys()].sort(compareUtf16)) {
      output[state][action] = actionEntries.get(action)!;
    }
  }
  return output;
}

function asCanonicalObject(value: unknown, label: string): CanonicalObject {
  const normalized = canonicalValue(value);
  if (!isPlainObject(normalized)) {
    throw new TypeError(`${label} must be a mapping`);
  }
  return normalized;
}

function cloneCanonicalObject(value: CanonicalObject): CanonicalObject {
  return asCanonicalObject(value, 'value');
}

export function transitionPreview(
  currentState: unknown,
  action: unknown,
  transitionTable: unknown,
  options: {
    expectedVersion?: bigint;
    expectedStateHash?: string;
    engineVersion?: string;
  } = {},
): Record<string, unknown> {
  const state = asCanonicalObject(currentState, 'current_state');
  const selectedAction = asCanonicalObject(action, 'action');
  const table = normalizeTransitionTable(transitionTable);

  const currentStatus = state.status;
  const actionType = selectedAction.type;
  if (typeof currentStatus !== 'string' || currentStatus.length === 0) {
    throw new TypeError('current_state.status is required');
  }
  if (typeof actionType !== 'string' || actionType.length === 0) {
    throw new TypeError('action.type is required');
  }

  const currentVersion = state.version ?? 0n;
  if (typeof currentVersion !== 'bigint' || currentVersion < 0n) {
    throw new TypeError('current_state.version must be a non-negative integer');
  }

  const currentHash = stateSha256(state);
  if (
    options.expectedVersion !== undefined &&
    currentVersion !== options.expectedVersion
  ) {
    return {
      ok: false,
      allowed: false,
      status: 'VERSION_CONFLICT',
      currentVersion,
      expectedVersion: options.expectedVersion,
      currentStateHash: currentHash,
      mutationPerformed: false,
    };
  }
  if (
    options.expectedStateHash &&
    currentHash !== options.expectedStateHash
  ) {
    return {
      ok: false,
      allowed: false,
      status: 'STATE_HASH_CONFLICT',
      currentStateHash: currentHash,
      expectedStateHash: options.expectedStateHash,
      mutationPerformed: false,
    };
  }

  const target = table[currentStatus]?.[actionType];
  if (target === undefined) {
    return {
      ok: false,
      allowed: false,
      status: 'TRANSITION_NOT_ALLOWED',
      currentStatus,
      actionType,
      allowedActions: Object.keys(table[currentStatus] ?? {}).sort(compareUtf16),
      currentStateHash: currentHash,
      mutationPerformed: false,
    };
  }

  const requestedTarget = selectedAction.targetStatus;
  if (requestedTarget !== undefined && requestedTarget !== target) {
    return {
      ok: false,
      allowed: false,
      status: 'TARGET_STATUS_MISMATCH',
      currentStatus,
      actionType,
      contractTargetStatus: target,
      requestedTargetStatus: requestedTarget,
      currentStateHash: currentHash,
      mutationPerformed: false,
    };
  }

  const patchValue = selectedAction.patch ?? {};
  if (!isPlainObject(patchValue)) {
    throw new TypeError('action.patch must be a mapping when supplied');
  }
  const patch = asCanonicalObject(patchValue, 'action.patch');
  const protectedFields = new Set([
    'status',
    'version',
    'stateHash',
    'actionHash',
    'chainHash',
    'previousChainHash',
  ]);
  const forbidden = Object.keys(patch)
    .filter((key) => protectedFields.has(key))
    .sort(compareUtf16);
  if (forbidden.length > 0) {
    throw new RangeError(`action.patch contains protected fields: ${forbidden.join(', ')}`);
  }

  const nextState = cloneCanonicalObject(state);
  for (const metadataField of STATE_METADATA_FIELDS) {
    delete nextState[metadataField];
  }
  for (const key of Object.keys(patch).sort(compareUtf16)) {
    nextState[key] = patch[key];
  }
  nextState.status = target;
  nextState.version = currentVersion + 1n;

  const actionHash = canonicalSha256(selectedAction);
  const nextStateHash = stateSha256(nextState);
  const previousChainHash = typeof state.chainHash === 'string' ? state.chainHash : '';
  const engineVersion = normalizeText(
    options.engineVersion?.trim() || 'are-v1',
    'engineVersion',
  );
  const chainMaterial: CanonicalObject = {
    schemaVersion: 'sovereign.are-chain.v1',
    engineVersion,
    sequence: nextState.version,
    previousChainHash,
    actionHash,
    stateHash: nextStateHash,
  };
  const chainHash = canonicalSha256(chainMaterial);

  return {
    ok: true,
    allowed: true,
    status: 'TRANSITION_VALIDATED',
    currentStatus,
    nextStatus: target,
    currentVersion,
    nextVersion: nextState.version,
    currentStateHash: currentHash,
    actionHash,
    nextStateHash,
    previousChainHash,
    chainHash,
    stateHashContract: 'canonical-state-without-chain-metadata',
    nextState,
    mutationPerformed: false,
    truthNotice:
      'Pure transition preview only; persistence, effects and runtime success are not claimed.',
  };
}

export function replayVerify(
  initialState: unknown,
  actions: unknown,
  transitionTable: unknown,
  options: {
    expectedFinalStateHash?: string;
    engineVersion?: string;
  } = {},
): Record<string, unknown> {
  if (!Array.isArray(actions)) {
    throw new TypeError('actions must be a list');
  }
  if (actions.length > MAX_REPLAY_ACTIONS) {
    throw new RangeError(`actions exceed the bounded limit of ${MAX_REPLAY_ACTIONS}`);
  }

  let state = asCanonicalObject(initialState, 'initial_state');
  const steps: Record<string, unknown>[] = [];
  for (let index = 0; index < actions.length; index += 1) {
    const version = state.version ?? 0n;
    if (typeof version !== 'bigint') {
      throw new TypeError('state version must be bigint');
    }
    const result = transitionPreview(state, actions[index], transitionTable, {
      expectedVersion: version,
      expectedStateHash: stateSha256(state),
      engineVersion: options.engineVersion,
    });
    steps.push({
      index: BigInt(index + 1),
      allowed: Boolean(result.allowed),
      status: result.status,
      actionHash: result.actionHash,
      stateHash: result.nextStateHash,
      chainHash: result.chainHash,
    });
    if (!result.allowed) {
      return {
        ok: false,
        status: 'REPLAY_BLOCKED',
        failedStep: BigInt(index + 1),
        steps,
        finalState: state,
        finalStateHash: stateSha256(state),
        finalChainHash: typeof state.chainHash === 'string' ? state.chainHash : null,
        stateHashContract: 'canonical-state-without-chain-metadata',
        mutationPerformed: false,
        crossRuntimeParityProven: false,
      };
    }
    state = cloneCanonicalObject(result.nextState as CanonicalObject);
    state.chainHash = result.chainHash as string;
  }

  const finalStateHash = stateSha256(state);
  const matches =
    !options.expectedFinalStateHash ||
    finalStateHash === options.expectedFinalStateHash;
  return {
    ok: matches,
    status: matches ? 'REPLAY_VERIFIED' : 'FINAL_STATE_HASH_MISMATCH',
    steps,
    finalState: state,
    finalStateHash,
    finalChainHash: typeof state.chainHash === 'string' ? state.chainHash : null,
    stateHashContract: 'canonical-state-without-chain-metadata',
    expectedFinalStateHash: options.expectedFinalStateHash || null,
    mutationPerformed: false,
    crossRuntimeParityProven: false,
    truthNotice:
      'Independent TypeScript reference replay; parity is established only by comparing the same committed vectors with the Python reference.',
  };
}

export function materializeTaggedIntegers(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(materializeTaggedIntegers);
  }
  if (!isPlainObject(value)) {
    return value;
  }
  const keys = Object.keys(value);
  if (
    keys.length === 1 &&
    keys[0] === '$integer' &&
    typeof value.$integer === 'string'
  ) {
    if (!/^-?(?:0|[1-9][0-9]*)$/.test(value.$integer)) {
      throw new TypeError('tagged integer must contain canonical decimal integer text');
    }
    return BigInt(value.$integer);
  }
  const output: Record<string, unknown> = {};
  for (const key of keys) {
    output[key] = materializeTaggedIntegers(value[key]);
  }
  return output;
}

export function tagBigInts(value: unknown): unknown {
  if (typeof value === 'bigint') {
    return { $integer: value.toString(10) };
  }
  if (Array.isArray(value)) {
    return value.map(tagBigInts);
  }
  if (isPlainObject(value)) {
    const output: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort(compareUtf16)) {
      output[key] = tagBigInts(value[key]);
    }
    return output;
  }
  return value;
}
