const RUNTIME_REPO_SNAPSHOT_KEY = 'sovereign-runtime-repo-snapshot';
const RUNTIME_REPO_SNAPSHOT_VERSION = 1 as const;
const NO_VALID_SNAPSHOT_MESSAGE = 'No valid runtime repo snapshot is loaded.';
const STORAGE_REQUIRED_MESSAGE = 'runtime repo snapshot storage is not available.';

export type RuntimeRepoFileType = 'blob' | 'tree' | 'file' | 'directory' | 'unknown';

export interface RuntimeRepoFileSnapshot {
  path: string;
  type?: RuntimeRepoFileType;
  size?: number;
  sha?: string;
  content?: string;
}

export interface RuntimeRepoSnapshotInput {
  repoUrl: string;
  repoBranch: string;
  repoStatus: string;
  repoFiles: RuntimeRepoFileSnapshot[];
}

export interface DurableRepoSnapshot extends RuntimeRepoSnapshotInput {
  version: typeof RUNTIME_REPO_SNAPSHOT_VERSION;
  savedAt: number;
  fileCount: number;
}

export interface DurableRepoSnapshotValidationReport {
  valid: boolean;
  ready: boolean;
  message: string;
  errors: string[];
  warnings: string[];
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

export interface RuntimeRepoSnapshotReadyGate {
  ready: boolean;
  message: string;
  report: DurableRepoSnapshotValidationReport;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function errorToMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function createReport(valid: boolean, message: string, errors: string[] = [], warnings: string[] = []): DurableRepoSnapshotValidationReport {
  return { valid, ready: valid && errors.length === 0, message, errors, warnings };
}

function okReport(message: string, warnings: string[] = []): DurableRepoSnapshotValidationReport {
  return createReport(true, message, [], warnings);
}

function errorReport(message: string, errors: string[] = [message]): DurableRepoSnapshotValidationReport {
  return createReport(false, message, errors, []);
}

function normalizeRepoFiles(files: RuntimeRepoFileSnapshot[]): RuntimeRepoFileSnapshot[] {
  return files.map((file) => ({ ...file, path: file.path.trim(), type: file.type ?? 'unknown' }));
}

export function createRuntimeRepoSnapshot(input: RuntimeRepoSnapshotInput): DurableRepoSnapshot {
  const repoFiles = normalizeRepoFiles(input.repoFiles);
  return {
    version: RUNTIME_REPO_SNAPSHOT_VERSION,
    repoUrl: input.repoUrl.trim(),
    repoBranch: input.repoBranch.trim(),
    repoStatus: input.repoStatus.trim(),
    repoFiles,
    savedAt: Date.now(),
    fileCount: repoFiles.length,
  };
}

export function validateDurableRepoSnapshot(snapshot: DurableRepoSnapshot): DurableRepoSnapshotValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (snapshot.version !== RUNTIME_REPO_SNAPSHOT_VERSION) errors.push(`unsupported runtime repo snapshot version: ${String(snapshot.version)}`);
  if (!snapshot.repoUrl.trim()) errors.push('repoUrl is required.');
  if (!snapshot.repoBranch.trim()) errors.push('repoBranch is required.');
  if (!snapshot.repoStatus.trim()) errors.push('repoStatus is required.');

  if (!Array.isArray(snapshot.repoFiles)) {
    errors.push('repoFiles must be an array.');
  } else {
    if (snapshot.repoFiles.length === 0) warnings.push('repoFiles is empty.');
    const invalidIndex = snapshot.repoFiles.findIndex((file) => !isRecord(file) || typeof file.path !== 'string' || !file.path.trim());
    if (invalidIndex >= 0) errors.push(`repoFiles[${invalidIndex}] must include a non-empty path.`);
  }

  if (snapshot.fileCount !== snapshot.repoFiles.length) warnings.push('fileCount does not match repoFiles.length.');

  try {
    if (snapshot.repoUrl) new URL(snapshot.repoUrl);
  } catch {
    warnings.push('repoUrl is not a valid absolute URL.');
  }

  if (errors.length > 0) return createReport(false, `runtime repo snapshot invalid: ${errors.length} error(s).`, errors, warnings);
  return okReport('runtime repo snapshot is valid.', warnings);
}

export function validateRuntimeRepoSnapshotInput(input: RuntimeRepoSnapshotInput): DurableRepoSnapshotValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!input.repoUrl.trim()) errors.push('repoUrl is required.');
  if (!input.repoBranch.trim()) errors.push('repoBranch is required.');
  if (!input.repoStatus.trim()) errors.push('repoStatus is required.');

  if (!Array.isArray(input.repoFiles)) {
    errors.push('repoFiles must be an array.');
  } else {
    if (input.repoFiles.length === 0) warnings.push('repoFiles is empty.');
    const invalidFileIndex = input.repoFiles.findIndex((file) => !isRecord(file) || typeof file.path !== 'string' || !file.path.trim());
    if (invalidFileIndex >= 0) errors.push(`repoFiles[${invalidFileIndex}] must be an object.`);
  }

  try {
    if (input.repoUrl) new URL(input.repoUrl);
  } catch {
    warnings.push('repoUrl is not a valid absolute URL.');
  }

  if (errors.length > 0) return createReport(false, `runtime repo snapshot input invalid: ${errors.length} error(s).`, errors, warnings);
  return okReport('runtime repo snapshot input is valid.', warnings);
}

export function validateLoadedRuntimeRepoSnapshot(snapshot: unknown): DurableRepoSnapshotValidationReport {
  if (!snapshot) return errorReport(NO_VALID_SNAPSHOT_MESSAGE);
  if (!isRecord(snapshot)) return errorReport('loaded runtime repo snapshot must be an object.');
  try {
    return validateDurableRepoSnapshot(snapshot as unknown as DurableRepoSnapshot);
  } catch (error) {
    return errorReport(`loaded runtime repo snapshot validation failed: ${errorToMessage(error)}`);
  }
}

export function inspectRuntimeRepoSnapshotStorage(storage: Storage | null): RuntimeRepoSnapshotStorageStatus {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!storage) return { available: false, readable: false, writable: false, clearable: false, length: null, errors: [STORAGE_REQUIRED_MESSAGE], warnings };

  let readable = false;
  let writable = false;
  let clearable = false;
  let length: number | null = null;

  try { length = storage.length; readable = true; } catch (error) { errors.push(`storage length read failed: ${errorToMessage(error)}`); }
  try { storage.setItem('__sovereign_runtime_probe__', '1'); storage.removeItem('__sovereign_runtime_probe__'); writable = true; } catch (error) { errors.push(`storage write probe failed: ${errorToMessage(error)}`); }
  try { storage.removeItem('__sovereign_runtime_clear_probe__'); clearable = true; } catch (error) { errors.push(`storage clear probe failed: ${errorToMessage(error)}`); }

  return { available: true, readable, writable, clearable, length, errors, warnings };
}

export function saveRuntimeRepoSnapshot(input: RuntimeRepoSnapshotInput, storage: Storage | null = typeof window === 'undefined' ? null : window.localStorage): DurableRepoSnapshotValidationReport {
  const inputReport = validateRuntimeRepoSnapshotInput(input);
  if (!inputReport.valid) return inputReport;
  if (!storage) return errorReport(STORAGE_REQUIRED_MESSAGE);

  const snapshot = createRuntimeRepoSnapshot(input);
  const snapshotReport = validateDurableRepoSnapshot(snapshot);
  if (!snapshotReport.valid) return snapshotReport;

  try {
    storage.setItem(RUNTIME_REPO_SNAPSHOT_KEY, JSON.stringify(snapshot));
    return okReport('runtime repo snapshot saved.', snapshotReport.warnings);
  } catch (error) {
    return errorReport(`runtime repo snapshot save failed: ${errorToMessage(error)}`);
  }
}

export function loadRuntimeRepoSnapshot(storage: Storage | null = typeof window === 'undefined' ? null : window.localStorage): DurableRepoSnapshot | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(RUNTIME_REPO_SNAPSHOT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    const report = validateLoadedRuntimeRepoSnapshot(parsed);
    return report.valid ? (parsed as DurableRepoSnapshot) : null;
  } catch {
    return null;
  }
}

export function clearRuntimeRepoSnapshot(storage: Storage | null = typeof window === 'undefined' ? null : window.localStorage): boolean {
  if (!storage) return false;
  try { storage.removeItem(RUNTIME_REPO_SNAPSHOT_KEY); return true; } catch { return false; }
}

export function clearRuntimeRepoSnapshotResult(storage: Storage | null = typeof window === 'undefined' ? null : window.localStorage): DurableRepoSnapshotValidationReport {
  return clearRuntimeRepoSnapshot(storage) ? okReport('runtime repo snapshot cleared.') : errorReport('runtime repo snapshot clear failed.');
}

export function hasRuntimeRepoSnapshot(storage: Storage | null = typeof window === 'undefined' ? null : window.localStorage): boolean {
  return loadRuntimeRepoSnapshot(storage) !== null;
}

export function getRuntimeRepoSnapshotReadyGate(storage: Storage | null = typeof window === 'undefined' ? null : window.localStorage): RuntimeRepoSnapshotReadyGate {
  const snapshot = loadRuntimeRepoSnapshot(storage);
  const report = validateLoadedRuntimeRepoSnapshot(snapshot);
  return { ready: report.ready, message: report.message, report };
}

export function assertRuntimeRepoSnapshotReady(storage: Storage | null = typeof window === 'undefined' ? null : window.localStorage): DurableRepoSnapshot {
  const snapshot = loadRuntimeRepoSnapshot(storage);
  const report = validateLoadedRuntimeRepoSnapshot(snapshot);
  if (!snapshot || !report.ready) throw new Error(report.message);
  return snapshot;
}

export function getRuntimeRepoSnapshotHealth(storage: Storage | null = typeof window === 'undefined' ? null : window.localStorage): DurableRepoSnapshotValidationReport {
  const snapshot = loadRuntimeRepoSnapshot(storage);
  return validateLoadedRuntimeRepoSnapshot(snapshot);
}

export function createRuntimeMemoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length(): number { return values.size; },
    clear(): void { values.clear(); },
    getItem(key: string): string | null { return values.get(key) ?? null; },
    key(index: number): string | null { return Array.from(values.keys())[index] ?? null; },
    removeItem(key: string): void { values.delete(key); },
    setItem(key: string, value: string): void { values.set(key, value); },
  };
}
