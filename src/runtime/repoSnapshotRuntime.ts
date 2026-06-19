import type { RepoFile } from '../features/github/types';

import {
  clearDurableRepoSnapshot,
  createDurableRepoSnapshot,
  loadDurableRepoSnapshot,
  saveDurableRepoSnapshot,
  validateDurableRepoSnapshot,
  type DurableRepoSnapshot,
  type DurableRepoSnapshotValidationReport,
} from '../features/github/repoSnapshotPersistence';

export interface RuntimeRepoSnapshotInput {
  repoUrl: string;
  repoBranch: string;
  repoStatus: string;
  repoFiles: RepoFile[];
}

export interface RuntimeRepoSnapshotResult {
  ok: boolean;
  snapshot: DurableRepoSnapshot | null;
  report: DurableRepoSnapshotValidationReport;
}

export interface RuntimeRepoSnapshotStorageStatus {
  available: boolean;
  readable: boolean;
  writable: boolean;
  clearable: boolean;
  length: number | null;
  errors: string[];
  warnings: string[];
}

export interface RuntimeRepoSnapshotHealth {
  ok: boolean;
  storage: RuntimeRepoSnapshotStorageStatus;
  hasSnapshot: boolean;
  snapshotValid: boolean;
  report: DurableRepoSnapshotValidationReport;
}

export interface RuntimeRepoSnapshotClearResult {
  ok: boolean;
  report: DurableRepoSnapshotValidationReport;
}

export interface RuntimeRepoSnapshotReadyGate {
  ready: boolean;
  result: RuntimeRepoSnapshotResult;
  health: RuntimeRepoSnapshotHealth;
  reason: string;
}

const STORAGE_REQUIRED_MESSAGE = 'storage is required.';
const NO_VALID_SNAPSHOT_MESSAGE = 'no valid durable repo snapshot found.';
const SAVE_FAILED_MESSAGE = 'snapshot could not be saved.';
const SAVE_VERIFY_FAILED_MESSAGE = 'snapshot was saved but verification failed.';
const CLEAR_FAILED_MESSAGE = 'snapshot could not be cleared.';
const RUNTIME_REPO_SNAPSHOT_STORAGE_PROBE_KEY = '__runtime_repo_snapshot_probe__';

function createReport(
  valid: boolean,
  summary: string,
  errors: string[] = [],
  warnings: string[] = [],
): DurableRepoSnapshotValidationReport {
  return {
    valid,
    errors,
    warnings,
    summary,
  };
}

function okReport(summary: string, warnings: string[] = []): DurableRepoSnapshotValidationReport {
  return createReport(true, summary, [], warnings);
}

function errorReport(
  message: string,
  warnings: string[] = [],
): DurableRepoSnapshotValidationReport {
  return createReport(false, message, [message], warnings);
}

function mergeReportWarnings(
  report: DurableRepoSnapshotValidationReport,
  warnings: string[],
): DurableRepoSnapshotValidationReport {
  const mergedWarnings = [...warnings, ...report.warnings];

  return {
    ...report,
    warnings: Array.from(new Set(mergedWarnings)),
  };
}

function errorToMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;

  try {
    return JSON.stringify(error);
  } catch {
    return 'unknown runtime repo snapshot error';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function safeTrim(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeRuntimeRepoSnapshotInput(
  input: RuntimeRepoSnapshotInput,
): RuntimeRepoSnapshotInput {
  return {
    repoUrl: input.repoUrl.trim(),
    repoBranch: input.repoBranch.trim(),
    repoStatus: input.repoStatus.trim(),
    repoFiles: [...input.repoFiles],
  };
}

function buildInvalidResult(report: DurableRepoSnapshotValidationReport): RuntimeRepoSnapshotResult {
  return {
    ok: false,
    snapshot: null,
    report,
  };
}

function buildValidResult(
  snapshot: DurableRepoSnapshot,
  report: DurableRepoSnapshotValidationReport,
): RuntimeRepoSnapshotResult {
  return {
    ok: true,
    snapshot,
    report,
  };
}

function stableSerialize(value: unknown): string {
  const seen = new WeakSet<object>();

  const normalize = (input: unknown): unknown => {
    if (input === null || input === undefined) return input;

    if (typeof input !== 'object') return input;

    if (seen.has(input)) return '[CIRCULAR]';
    seen.add(input);

    if (Array.isArray(input)) {
      return input.map(normalize);
    }

    const record = input as Record<string, unknown>;
    const sorted: Record<string, unknown> = {};

    for (const key of Object.keys(record).sort()) {
      sorted[key] = normalize(record[key]);
    }

    return sorted;
  };

  try {
    return JSON.stringify(normalize(value));
  } catch {
    return '';
  }
}

function createStorageProbeValue(): string {
  return `runtime-probe-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function validateRuntimeRepoSnapshotInput(
  input: unknown,
): DurableRepoSnapshotValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!isRecord(input)) {
    return errorReport('runtime repo snapshot input must be an object.');
  }

  const repoUrl = safeTrim(input.repoUrl);
  const repoBranch = safeTrim(input.repoBranch);
  const repoStatus = safeTrim(input.repoStatus);
  const repoFiles = input.repoFiles;

  if (!repoUrl) {
    errors.push('repoUrl is required.');
  }

  if (!repoBranch) {
    errors.push('repoBranch is required.');
  }

  if (!repoStatus) {
    errors.push('repoStatus is required.');
  }

  if (!Array.isArray(repoFiles)) {
    errors.push('repoFiles must be an array.');
  } else if (repoFiles.length === 0) {
    errors.push('repoFiles must contain at least one file.');
  } else {
    const invalidFileIndex = repoFiles.findIndex((file) => !isRecord(file));

    if (invalidFileIndex >= 0) {
      errors.push(`repoFiles[${invalidFileIndex}] must be an object.`);
    }
  }

  try {
    if (repoUrl) {
      new URL(repoUrl);
    }
  } catch {
    warnings.push('repoUrl is not a valid absolute URL.');
  }

  if (errors.length > 0) {
    return createReport(
      false,
      `runtime repo snapshot input invalid: ${errors.length} error(s).`,
      errors,
      warnings,
    );
  }

  return okReport('runtime repo snapshot input is valid.', warnings);
}

export function validateLoadedRuntimeRepoSnapshot(
  snapshot: unknown,
): DurableRepoSnapshotValidationReport {
  if (!snapshot) {
    return errorReport(NO_VALID_SNAPSHOT_MESSAGE);
  }

  if (!isRecord(snapshot)) {
    return errorReport('loaded runtime repo snapshot must be an object.');
  }

  try {
    return validateDurableRepoSnapshot(snapshot as DurableRepoSnapshot);
  } catch (error) {
    return errorReport(`loaded runtime repo snapshot validation failed: ${errorToMessage(error)}`);
  }
}

export function inspectRuntimeRepoSnapshotStorage(
  storage: Storage | null,
): RuntimeRepoSnapshotStorageStatus {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!storage) {
    return {
      available: false,
      readable: false,
      writable: false,
      clearable: false,
      length: null,
      errors: [STORAGE_REQUIRED_MESSAGE],
      warnings,
    };
  }

  let length: number | null = null;
  let readable = false;
  let writable = false;
  let clearable = false;

  try {
    length = storage.length;
    readable = true;
  } catch (error) {
    errors.push(`storage is not readable: ${errorToMessage(error)}`);
  }

  const probeKey = RUNTIME_REPO_SNAPSHOT_STORAGE_PROBE_KEY;
  const probeValue = createStorageProbeValue();

  try {
    storage.setItem(probeKey, probeValue);
    writable = storage.getItem(probeKey) === probeValue;
    storage.removeItem(probeKey);
    clearable = storage.getItem(probeKey) === null;

    if (!writable) {
      errors.push('storage probe write verification failed.');
    }

    if (!clearable) {
      warnings.push('storage probe cleanup verification failed.');
    }
  } catch (error) {
    errors.push(`storage is not writable: ${errorToMessage(error)}`);

    try {
      storage.removeItem(probeKey);
    } catch {
      warnings.push('storage probe cleanup failed after write error.');
    }
  }

  return {
    available: true,
    readable,
    writable,
    clearable,
    length,
    errors,
    warnings,
  };
}

export function createRuntimeRepoSnapshot(
  input: RuntimeRepoSnapshotInput,
): RuntimeRepoSnapshotResult {
  const inputReport = validateRuntimeRepoSnapshotInput(input);

  if (!inputReport.valid) {
    return buildInvalidResult(inputReport);
  }

  try {
    const normalizedInput = normalizeRuntimeRepoSnapshotInput(input);
    const snapshot = createDurableRepoSnapshot(normalizedInput);
    const report = mergeReportWarnings(
      validateDurableRepoSnapshot(snapshot),
      inputReport.warnings,
    );

    if (!report.valid) {
      return buildInvalidResult(report);
    }

    return buildValidResult(snapshot, report);
  } catch (error) {
    return buildInvalidResult(
      errorReport(`runtime repo snapshot creation failed: ${errorToMessage(error)}`),
    );
  }
}

export function saveRuntimeRepoSnapshot(
  storage: Storage | null,
  input: RuntimeRepoSnapshotInput,
): RuntimeRepoSnapshotResult {
  const storageStatus = inspectRuntimeRepoSnapshotStorage(storage);

  if (!storageStatus.available) {
    return buildInvalidResult(errorReport(STORAGE_REQUIRED_MESSAGE));
  }

  if (!storageStatus.writable) {
    return buildInvalidResult(
      errorReport('storage is not writable.', storageStatus.errors),
    );
  }

  const created = createRuntimeRepoSnapshot(input);

  if (!created.ok || !created.snapshot) {
    return created;
  }

  try {
    const saved = saveDurableRepoSnapshot(storage as Storage, created.snapshot);

    if (!saved) {
      return buildInvalidResult(errorReport(SAVE_FAILED_MESSAGE));
    }

    const loadedSnapshot = loadDurableRepoSnapshot(storage as Storage);

    if (!loadedSnapshot) {
      return buildInvalidResult(errorReport(SAVE_VERIFY_FAILED_MESSAGE));
    }

    const verifyReport = validateLoadedRuntimeRepoSnapshot(loadedSnapshot);

    if (!verifyReport.valid) {
      return buildInvalidResult(verifyReport);
    }

    const createdHash = stableSerialize(created.snapshot);
    const loadedHash = stableSerialize(loadedSnapshot);

    const verificationWarnings =
      createdHash && loadedHash && createdHash !== loadedHash
        ? ['saved snapshot differs from loaded snapshot after storage roundtrip.']
        : [];

    return buildValidResult(
      loadedSnapshot,
      mergeReportWarnings(verifyReport, verificationWarnings),
    );
  } catch (error) {
    return buildInvalidResult(
      errorReport(`runtime repo snapshot save failed: ${errorToMessage(error)}`),
    );
  }
}

export function loadRuntimeRepoSnapshot(storage: Storage | null): RuntimeRepoSnapshotResult {
  const storageStatus = inspectRuntimeRepoSnapshotStorage(storage);

  if (!storageStatus.available) {
    return buildInvalidResult(errorReport(STORAGE_REQUIRED_MESSAGE));
  }

  if (!storageStatus.readable) {
    return buildInvalidResult(
      errorReport('storage is not readable.', storageStatus.errors),
    );
  }

  try {
    const snapshot = loadDurableRepoSnapshot(storage as Storage);

    if (!snapshot) {
      return buildInvalidResult(errorReport(NO_VALID_SNAPSHOT_MESSAGE));
    }

    const report = validateLoadedRuntimeRepoSnapshot(snapshot);

    if (!report.valid) {
      return buildInvalidResult(report);
    }

    return buildValidResult(snapshot, report);
  } catch (error) {
    return buildInvalidResult(
      errorReport(`runtime repo snapshot load failed: ${errorToMessage(error)}`),
    );
  }
}

export function clearRuntimeRepoSnapshotResult(
  storage: Storage | null,
): RuntimeRepoSnapshotClearResult {
  const storageStatus = inspectRuntimeRepoSnapshotStorage(storage);

  if (!storageStatus.available) {
    return {
      ok: false,
      report: errorReport(STORAGE_REQUIRED_MESSAGE),
    };
  }

  if (!storageStatus.writable) {
    return {
      ok: false,
      report: errorReport('storage is not writable.', storageStatus.errors),
    };
  }

  try {
    clearDurableRepoSnapshot(storage as Storage);

    const loaded = loadDurableRepoSnapshot(storage as Storage);

    if (loaded) {
      return {
        ok: false,
        report: errorReport(CLEAR_FAILED_MESSAGE),
      };
    }

    return {
      ok: true,
      report: okReport('runtime repo snapshot cleared.'),
    };
  } catch (error) {
    return {
      ok: false,
      report: errorReport(`runtime repo snapshot clear failed: ${errorToMessage(error)}`),
    };
  }
}

export function clearRuntimeRepoSnapshot(storage: Storage | null): boolean {
  return clearRuntimeRepoSnapshotResult(storage).ok;
}

export function hasRuntimeRepoSnapshot(storage: Storage | null): boolean {
  return loadRuntimeRepoSnapshot(storage).ok;
}

export function getRuntimeRepoSnapshotHealth(storage: Storage | null): RuntimeRepoSnapshotHealth {
  const storageStatus = inspectRuntimeRepoSnapshotStorage(storage);

  if (!storageStatus.available) {
    return {
      ok: false,
      storage: storageStatus,
      hasSnapshot: false,
      snapshotValid: false,
      report: errorReport(STORAGE_REQUIRED_MESSAGE),
    };
  }

  if (!storageStatus.readable) {
    return {
      ok: false,
      storage: storageStatus,
      hasSnapshot: false,
      snapshotValid: false,
      report: errorReport('storage is not readable.', storageStatus.errors),
    };
  }

  try {
    const snapshot = loadDurableRepoSnapshot(storage as Storage);

    if (!snapshot) {
      return {
        ok: false,
        storage: storageStatus,
        hasSnapshot: false,
        snapshotValid: false,
        report: errorReport(NO_VALID_SNAPSHOT_MESSAGE),
      };
    }

    const report = validateLoadedRuntimeRepoSnapshot(snapshot);

    return {
      ok: report.valid,
      storage: storageStatus,
      hasSnapshot: true,
      snapshotValid: report.valid,
      report,
    };
  } catch (error) {
    return {
      ok: false,
      storage: storageStatus,
      hasSnapshot: false,
      snapshotValid: false,
      report: errorReport(`runtime repo snapshot health check failed: ${errorToMessage(error)}`),
    };
  }
}

export function getRuntimeRepoSnapshotReadyGate(
  storage: Storage | null,
): RuntimeRepoSnapshotReadyGate {
  const result = loadRuntimeRepoSnapshot(storage);
  const health = getRuntimeRepoSnapshotHealth(storage);

  if (!health.storage.available) {
    return {
      ready: false,
      result,
      health,
      reason: STORAGE_REQUIRED_MESSAGE,
    };
  }

  if (!health.storage.readable) {
    return {
      ready: false,
      result,
      health,
      reason: 'storage is not readable.',
    };
  }

  if (!health.hasSnapshot) {
    return {
      ready: false,
      result,
      health,
      reason: NO_VALID_SNAPSHOT_MESSAGE,
    };
  }

  if (!health.snapshotValid) {
    return {
      ready: false,
      result,
      health,
      reason: health.report.summary,
    };
  }

  return {
    ready: true,
    result,
    health,
    reason: 'runtime repo snapshot ready.',
  };
}

export function assertRuntimeRepoSnapshotReady(storage: Storage | null): RuntimeRepoSnapshotResult {
  const gate = getRuntimeRepoSnapshotReadyGate(storage);

  if (!gate.ready) {
    return buildInvalidResult(gate.health.report);
  }

  return gate.result;
}

/**
 * In-memory Storage implementation for deterministic runtime tests,
 * isolated workbenches, Android WebView fallback checks, and sandbox flows.
 */
export function createRuntimeMemoryStorage(seed: Record<string, string> = {}): Storage {
  const map = new Map<string, string>(Object.entries(seed));

  return {
    get length() {
      return map.size;
    },

    clear() {
      map.clear();
    },

    getItem(key: string) {
      return map.has(key) ? map.get(key) ?? null : null;
    },

    key(index: number) {
      return Array.from(map.keys())[index] ?? null;
    },

    removeItem(key: string) {
      map.delete(key);
    },

    setItem(key: string, value: string) {
      map.set(String(key), String(value));
    },
  };
      }
