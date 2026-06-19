import type { RepoFile } from './types';

export interface DurableRepoSnapshot {
  version: 1;
  repoUrl: string;
  repoBranch: string;
  repoStatus: string;
  repoFiles: RepoFile[];
  savedAt: number;
}

export interface DurableRepoSnapshotValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export const DURABLE_REPO_SNAPSHOT_KEY = 'sovereign-studio.repo-snapshot.v1';
const MAX_FILES = 500;
const MAX_TEXT = 700;

function cleanText(value: unknown, maxLength = MAX_TEXT): string {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : '';
}

function normalizeRepoFile(value: unknown): RepoFile | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as Partial<RepoFile>;
  const path = cleanText(item.path, 800);
  const type = item.type === 'blob' || item.type === 'tree' ? item.type : null;
  if (!path || !type) return null;
  const size = typeof item.size === 'number' && Number.isFinite(item.size) && item.size >= 0 ? item.size : undefined;
  return { path, type, size };
}

export function createDurableRepoSnapshot(input: {
  repoUrl: string;
  repoBranch: string;
  repoStatus: string;
  repoFiles: RepoFile[];
  savedAt?: number;
}): DurableRepoSnapshot {
  return {
    version: 1,
    repoUrl: cleanText(input.repoUrl),
    repoBranch: cleanText(input.repoBranch, 160),
    repoStatus: cleanText(input.repoStatus, 1000),
    repoFiles: input.repoFiles.map(normalizeRepoFile).filter((file): file is RepoFile => Boolean(file)).slice(0, MAX_FILES),
    savedAt: typeof input.savedAt === 'number' && Number.isFinite(input.savedAt) && input.savedAt > 0 ? input.savedAt : Date.now(),
  };
}

export function validateDurableRepoSnapshot(snapshot: DurableRepoSnapshot): DurableRepoSnapshotValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (snapshot.version !== 1) errors.push('version must be 1.');
  if (!snapshot.repoUrl) errors.push('repoUrl is required.');
  if (!Array.isArray(snapshot.repoFiles)) errors.push('repoFiles must be an array.');
  if (snapshot.repoFiles.length === 0) errors.push('repoFiles must not be empty.');
  if (snapshot.repoFiles.length > MAX_FILES) errors.push('repoFiles exceeds max persisted files.');
  if (!Number.isFinite(snapshot.savedAt) || snapshot.savedAt <= 0) errors.push('savedAt must be a positive timestamp.');
  if (!snapshot.repoStatus) warnings.push('repoStatus is empty.');
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in durable repo snapshot.`,
  };
}

export function serializeDurableRepoSnapshot(snapshot: DurableRepoSnapshot): string {
  const report = validateDurableRepoSnapshot(snapshot);
  if (!report.valid) throw new Error(`Durable repo snapshot is invalid: ${report.errors.join(' | ')}`);
  return JSON.stringify(snapshot);
}

export function parseDurableRepoSnapshot(raw: string | null): DurableRepoSnapshot | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<DurableRepoSnapshot>;
    const snapshot = createDurableRepoSnapshot({
      repoUrl: parsed.repoUrl ?? '',
      repoBranch: parsed.repoBranch ?? '',
      repoStatus: parsed.repoStatus ?? '',
      repoFiles: Array.isArray(parsed.repoFiles) ? parsed.repoFiles as RepoFile[] : [],
      savedAt: parsed.savedAt,
    });
    return validateDurableRepoSnapshot(snapshot).valid ? snapshot : null;
  } catch {
    return null;
  }
}

export function saveDurableRepoSnapshot(storage: Storage, snapshot: DurableRepoSnapshot): boolean {
  const report = validateDurableRepoSnapshot(snapshot);
  if (!report.valid) return false;
  storage.setItem(DURABLE_REPO_SNAPSHOT_KEY, serializeDurableRepoSnapshot(snapshot));
  return true;
}

export function loadDurableRepoSnapshot(storage: Storage): DurableRepoSnapshot | null {
  return parseDurableRepoSnapshot(storage.getItem(DURABLE_REPO_SNAPSHOT_KEY));
}

export function clearDurableRepoSnapshot(storage: Storage): void {
  storage.removeItem(DURABLE_REPO_SNAPSHOT_KEY);
}
