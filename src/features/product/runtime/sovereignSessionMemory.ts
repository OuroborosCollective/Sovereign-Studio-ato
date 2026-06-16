import type { RepoFile } from '../../github/types';

export interface SovereignSessionMemorySnapshot {
  version: 1;
  repoUrl: string;
  repoBranch: string;
  repoStatus: string;
  repoFiles: RepoFile[];
  mission: string;
  sovereignSummary: string;
  sovereignPreview: string;
  savedAt: number;
}

export const SOVEREIGN_SESSION_MEMORY_KEY = 'sovereign-studio.session-memory.v1';
const MAX_FILES = 500;
const MAX_PREVIEW_CHARS = 80_000;

function trimPreview(value: string): string {
  return value.length > MAX_PREVIEW_CHARS ? value.slice(0, MAX_PREVIEW_CHARS) : value;
}

export function createSessionMemorySnapshot(input: Omit<SovereignSessionMemorySnapshot, 'version' | 'savedAt'>): SovereignSessionMemorySnapshot {
  return {
    version: 1,
    repoUrl: input.repoUrl,
    repoBranch: input.repoBranch,
    repoStatus: input.repoStatus,
    repoFiles: input.repoFiles.slice(0, MAX_FILES),
    mission: input.mission,
    sovereignSummary: input.sovereignSummary,
    sovereignPreview: trimPreview(input.sovereignPreview),
    savedAt: Date.now(),
  };
}

export function serializeSessionMemory(snapshot: SovereignSessionMemorySnapshot): string {
  return JSON.stringify(snapshot);
}

export function parseSessionMemory(raw: string | null): SovereignSessionMemorySnapshot | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<SovereignSessionMemorySnapshot>;
    if (parsed.version !== 1) return null;
    if (typeof parsed.repoUrl !== 'string') return null;
    if (typeof parsed.repoBranch !== 'string') return null;
    if (typeof parsed.repoStatus !== 'string') return null;
    if (!Array.isArray(parsed.repoFiles)) return null;
    if (typeof parsed.mission !== 'string') return null;
    if (typeof parsed.sovereignSummary !== 'string') return null;
    if (typeof parsed.sovereignPreview !== 'string') return null;
    if (typeof parsed.savedAt !== 'number') return null;
    return parsed as SovereignSessionMemorySnapshot;
  } catch {
    return null;
  }
}

export function saveSessionMemory(storage: Storage, snapshot: SovereignSessionMemorySnapshot): void {
  storage.setItem(SOVEREIGN_SESSION_MEMORY_KEY, serializeSessionMemory(snapshot));
}

export function loadSessionMemory(storage: Storage): SovereignSessionMemorySnapshot | null {
  return parseSessionMemory(storage.getItem(SOVEREIGN_SESSION_MEMORY_KEY));
}

export function clearSessionMemory(storage: Storage): void {
  storage.removeItem(SOVEREIGN_SESSION_MEMORY_KEY);
}

export function formatSessionMemoryAge(snapshot: SovereignSessionMemorySnapshot, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - snapshot.savedAt) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}
