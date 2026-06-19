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

function emptyReport(message: string): DurableRepoSnapshotValidationReport {
  return { valid: false, errors: [message], warnings: [], summary: message };
}

export function createRuntimeRepoSnapshot(input: RuntimeRepoSnapshotInput): RuntimeRepoSnapshotResult {
  const snapshot = createDurableRepoSnapshot(input);
  const report = validateDurableRepoSnapshot(snapshot);
  return { ok: report.valid, snapshot: report.valid ? snapshot : null, report };
}

export function saveRuntimeRepoSnapshot(storage: Storage | null, input: RuntimeRepoSnapshotInput): RuntimeRepoSnapshotResult {
  if (!storage) return { ok: false, snapshot: null, report: emptyReport('storage is required.') };
  const snapshot = createDurableRepoSnapshot(input);
  const report = validateDurableRepoSnapshot(snapshot);
  if (!report.valid) return { ok: false, snapshot: null, report };
  const ok = saveDurableRepoSnapshot(storage, snapshot);
  return { ok, snapshot: ok ? snapshot : null, report: ok ? report : emptyReport('snapshot could not be saved.') };
}

export function loadRuntimeRepoSnapshot(storage: Storage | null): RuntimeRepoSnapshotResult {
  if (!storage) return { ok: false, snapshot: null, report: emptyReport('storage is required.') };
  const snapshot = loadDurableRepoSnapshot(storage);
  if (!snapshot) return { ok: false, snapshot: null, report: emptyReport('no valid durable repo snapshot found.') };
  const report = validateDurableRepoSnapshot(snapshot);
  return { ok: report.valid, snapshot: report.valid ? snapshot : null, report };
}

export function clearRuntimeRepoSnapshot(storage: Storage | null): boolean {
  if (!storage) return false;
  clearDurableRepoSnapshot(storage);
  return true;
}
