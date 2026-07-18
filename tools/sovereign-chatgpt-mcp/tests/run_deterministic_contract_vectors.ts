import { readFile } from 'node:fs/promises';
import {
  canonicalDecimalToUnits,
  canonicalSha256,
  canonicalBytes,
  divideFixed,
  materializeTaggedIntegers,
  multiplyFixed,
  replayVerify,
  stateSha256,
  tagBigInts,
  transitionPreview,
  truncDivTowardZero,
} from '../deterministic_contract.ts';

type VectorDocument = {
  schemaVersion: string;
  decimalVectors: Array<{ name: string; value: string; signed?: boolean }>;
  arithmeticVectors: Array<{
    name: string;
    operation: 'truncDiv' | 'multiplyFixed' | 'divideFixed';
    left: unknown;
    right: unknown;
  }>;
  canonicalVectors: Array<{ name: string; value: unknown }>;
  rejectionVectors: Array<{
    name: string;
    operation: 'canonical' | 'decimalUnsigned';
    value: unknown;
  }>;
  stateVectors: Array<{ name: string; state: unknown }>;
  transitionVectors: Array<{
    name: string;
    currentState: unknown;
    action: unknown;
    transitionTable: unknown;
    expectedVersion?: unknown;
    expectedStateHash?: string;
    engineVersion?: string;
  }>;
  replayVectors: Array<{
    name: string;
    initialState: unknown;
    actions: unknown;
    transitionTable: unknown;
    expectedFinalStateHash?: string;
    engineVersion?: string;
  }>;
};

const inputPath = process.argv[2];
if (!inputPath) {
  throw new Error('Usage: node --experimental-strip-types run_deterministic_contract_vectors.ts <vectors.json>');
}

const document = JSON.parse(await readFile(inputPath, 'utf8')) as VectorDocument;
const output = {
  schemaVersion: 'sovereign.deterministic-cross-runtime-results.v1',
  sourceSchemaVersion: document.schemaVersion,
  decimalVectors: document.decimalVectors.map((vector) => ({
    name: vector.name,
    units: canonicalDecimalToUnits(vector.value, { signed: vector.signed }).toString(10),
  })),
  arithmeticVectors: document.arithmeticVectors.map((vector) => {
    const left = materializeTaggedIntegers(vector.left);
    const right = materializeTaggedIntegers(vector.right);
    if (typeof left !== 'bigint' || typeof right !== 'bigint') {
      throw new TypeError(`arithmetic vector ${vector.name} requires tagged integers`);
    }
    const result = vector.operation === 'truncDiv'
      ? truncDivTowardZero(left, right)
      : vector.operation === 'multiplyFixed'
        ? multiplyFixed(left, right)
        : divideFixed(left, right);
    return { name: vector.name, result: result.toString(10) };
  }),
  canonicalVectors: document.canonicalVectors.map((vector) => {
    const value = materializeTaggedIntegers(vector.value);
    return {
      name: vector.name,
      canonicalUtf8Hex: Buffer.from(canonicalBytes(value)).toString('hex'),
      sha256: canonicalSha256(value),
    };
  }),
  rejectionVectors: document.rejectionVectors.map((vector) => {
    let rejected = false;
    try {
      if (vector.operation === 'canonical') {
        canonicalSha256(materializeTaggedIntegers(vector.value));
      } else {
        canonicalDecimalToUnits(String(vector.value), { signed: false });
      }
    } catch {
      rejected = true;
    }
    return { name: vector.name, rejected };
  }),
  stateVectors: document.stateVectors.map((vector) => ({
    name: vector.name,
    stateSha256: stateSha256(materializeTaggedIntegers(vector.state)),
  })),
  transitionVectors: document.transitionVectors.map((vector) => {
    const expectedVersion = vector.expectedVersion === undefined
      ? undefined
      : materializeTaggedIntegers(vector.expectedVersion);
    if (expectedVersion !== undefined && typeof expectedVersion !== 'bigint') {
      throw new TypeError(`expectedVersion for ${vector.name} must be a tagged integer`);
    }
    const result = transitionPreview(
      materializeTaggedIntegers(vector.currentState),
      materializeTaggedIntegers(vector.action),
      materializeTaggedIntegers(vector.transitionTable),
      {
        expectedVersion,
        expectedStateHash: vector.expectedStateHash,
        engineVersion: vector.engineVersion,
      },
    );
    delete result.truthNotice;
    return { name: vector.name, result: tagBigInts(result) };
  }),
  replayVectors: document.replayVectors.map((vector) => {
    const result = replayVerify(
      materializeTaggedIntegers(vector.initialState),
      materializeTaggedIntegers(vector.actions),
      materializeTaggedIntegers(vector.transitionTable),
      {
        expectedFinalStateHash: vector.expectedFinalStateHash,
        engineVersion: vector.engineVersion,
      },
    );
    delete result.truthNotice;
    return { name: vector.name, result: tagBigInts(result) };
  }),
};

process.stdout.write(`${JSON.stringify(output)}\n`);
