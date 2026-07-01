/**
 * Pattern Memory Runtime — Issue #447
 * Stores and retrieves learned pattern entries per user scope.
 * No fake state. No percentages. Runtime creates truth; UI only displays it.
 */

export type PatternOwnerScope = 'local-user' | 'remote-user' | 'shared-derived';

export interface LearnedPatternEntry {
  readonly id: string;
  readonly ownerScope: PatternOwnerScope;
  readonly sourceTraceId: string;
  readonly title: string;
  readonly summary: string;
  readonly tags: string[];
  readonly vectorRef: string | null;
  readonly objectRef: string | null;
  readonly verified: boolean;
  readonly localExecutable: boolean;
  readonly reuseCount: number;
  readonly lastUsedAt: number | null;
  readonly createdAt: number;
}

export interface PatternMemoryStore {
  readonly version: 1;
  readonly entries: LearnedPatternEntry[];
  readonly updatedAt: number;
}

export interface PatternMemoryIntake {
  readonly ownerScope: PatternOwnerScope;
  readonly sourceTraceId: string;
  readonly title: string;
  readonly summary: string;
  readonly tags?: string[];
  readonly vectorRef?: string | null;
  readonly objectRef?: string | null;
  readonly verified?: boolean;
  readonly localExecutable?: boolean;
  readonly now?: number;
}

export interface PatternMemoryValidationReport {
  readonly valid: boolean;
  readonly errors: string[];
  readonly warnings: string[];
  readonly summary: string;
}

export interface PatternMemoryRuntimeCounters {
  readonly totalStored: number;
  readonly verifiedCount: number;
  readonly localExecutableCount: number;
  readonly frequentlyUsedCount: number;
  readonly lastSuccessfulReuseAt: number | null;
  readonly localUserCount: number;
  readonly remoteUserCount: number;
  readonly sharedDerivedCount: number;
}

export interface PatternMemoryQuery {
  readonly ownerScope?: PatternOwnerScope;
  readonly verified?: boolean;
  readonly localExecutable?: boolean;
  readonly tag?: string;
  readonly minReuseCount?: number;
  readonly limit?: number;
}

export interface PatternMemoryEraseResult {
  readonly erasedCount: number;
  readonly remainingCount: number;
  readonly summary: string;
}

const MAX_ENTRIES = 500;
const MAX_TAGS = 16;
const MAX_TEXT = 800;
const FREQUENTLY_USED_THRESHOLD = 3;

const SENSITIVE_PATTERNS = [
  /ghp_[A-Za-z0-9_]{8,}/g,
  /github_pat_[A-Za-z0-9_]+/g,
  /sk-[A-Za-z0-9_-]{12,}/g,
  /Bearer\s+[A-Za-z0-9._~+/=-]{10,}/gi,
  /password\s*[:=]\s*\S+/gi,
  /token\s*[:=]\s*\S+/gi,
];

const KNOWN_SCOPES: PatternOwnerScope[] = ['local-user', 'remote-user', 'shared-derived'];

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function sanitizeText(value: string): string {
  let out = value.trim().slice(0, MAX_TEXT);
  for (const re of SENSITIVE_PATTERNS) {
    re.lastIndex = 0;
    out = out.replace(re, '<redacted>');
  }
  return out;
}

function hasSensitive(value: string): boolean {
  return SENSITIVE_PATTERNS.some((re) => {
    re.lastIndex = 0;
    return re.test(value);
  });
}

function normalizeTag(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9:_-]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
}

function normalizeTags(tags: string[] = []): string[] {
  return Array.from(new Set(tags.map(normalizeTag).filter(Boolean))).slice(0, MAX_TAGS);
}

function knownScope(scope: string): scope is PatternOwnerScope {
  return KNOWN_SCOPES.includes(scope as PatternOwnerScope);
}

export function createPatternMemoryStore(now = Date.now()): PatternMemoryStore {
  return { version: 1, entries: [], updatedAt: now };
}

export function validatePatternMemoryIntake(intake: PatternMemoryIntake): PatternMemoryValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!knownScope(intake.ownerScope)) errors.push(`Unknown ownerScope: ${intake.ownerScope}`);
  if (!intake.sourceTraceId.trim()) errors.push('sourceTraceId is required.');
  if (!intake.title.trim()) errors.push('title is required.');
  if (!intake.summary.trim()) errors.push('summary is required.');
  if (intake.title.length > MAX_TEXT) errors.push('title is too long.');
  if (intake.summary.length > MAX_TEXT) errors.push('summary is too long.');

  const textFields = [intake.title, intake.summary, intake.sourceTraceId, ...(intake.tags ?? [])];
  if (textFields.some(hasSensitive)) errors.push('Intake contains sensitive-looking content.');

  if (intake.localExecutable && !intake.verified) {
    warnings.push('localExecutable=true but verified=false — only verified patterns should be locally executable.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in pattern memory intake.`,
  };
}

export function buildLearnedPatternEntry(intake: PatternMemoryIntake): LearnedPatternEntry {
  const now = intake.now ?? Date.now();
  const title = sanitizeText(intake.title);
  const summary = sanitizeText(intake.summary);
  const tags = normalizeTags(intake.tags);
  const id = `pat-${stableHash([intake.ownerScope, intake.sourceTraceId, title, summary, tags.join(',')].join('|'))}`;

  return {
    id,
    ownerScope: intake.ownerScope,
    sourceTraceId: sanitizeText(intake.sourceTraceId),
    title,
    summary,
    tags,
    vectorRef: intake.vectorRef ?? null,
    objectRef: intake.objectRef ?? null,
    verified: intake.verified ?? false,
    localExecutable: (intake.localExecutable ?? false) && (intake.verified ?? false),
    reuseCount: 0,
    lastUsedAt: null,
    createdAt: now,
  };
}

export function validatePatternMemoryStore(store: PatternMemoryStore): PatternMemoryValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (store.version !== 1) errors.push('Unsupported pattern memory store version.');
  if (store.entries.length > MAX_ENTRIES) errors.push(`Pattern memory store exceeds ${MAX_ENTRIES} entries.`);

  const ids = new Set<string>();
  for (const entry of store.entries) {
    if (ids.has(entry.id)) errors.push(`Duplicate entry id: ${entry.id}`);
    ids.add(entry.id);
    if (!entry.id.trim()) errors.push('Entry id is required.');
    if (!knownScope(entry.ownerScope)) errors.push(`Unknown ownerScope: ${entry.ownerScope}`);
    if (!entry.title.trim()) errors.push(`Entry ${entry.id}: title is required.`);
    if (!entry.summary.trim()) errors.push(`Entry ${entry.id}: summary is required.`);
    if (entry.localExecutable && !entry.verified) errors.push(`Entry ${entry.id}: localExecutable=true requires verified=true.`);
    if (entry.reuseCount < 0 || !Number.isFinite(entry.reuseCount)) errors.push(`Entry ${entry.id}: reuseCount must be non-negative.`);
    if (entry.lastUsedAt !== null && (!Number.isFinite(entry.lastUsedAt) || entry.lastUsedAt <= 0)) errors.push(`Entry ${entry.id}: lastUsedAt must be a positive timestamp or null.`);
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${store.entries.length} pattern(s), ${errors.length} error(s), ${warnings.length} warning(s).`,
  };
}

export function assertPatternMemoryStoreValid(store: PatternMemoryStore): void {
  const report = validatePatternMemoryStore(store);
  if (!report.valid) {
    throw new Error(`Pattern memory store invalid: ${report.errors.join(' | ')}`);
  }
}

export function addPatternEntry(store: PatternMemoryStore, intake: PatternMemoryIntake): PatternMemoryStore {
  const validation = validatePatternMemoryIntake(intake);
  if (!validation.valid) {
    throw new Error(`Pattern intake invalid: ${validation.errors.join(' | ')}`);
  }

  const entry = buildLearnedPatternEntry(intake);
  const now = intake.now ?? Date.now();
  const existing = store.entries.find((e) => e.id === entry.id);

  const nextEntries = existing
    ? store.entries.map((e) => e.id === entry.id
        ? { ...e, reuseCount: e.reuseCount + 1, lastUsedAt: now, verified: e.verified || entry.verified, localExecutable: (e.localExecutable || entry.localExecutable) && (e.verified || entry.verified) }
        : e)
    : [entry, ...store.entries].slice(0, MAX_ENTRIES);

  const nextStore: PatternMemoryStore = { version: 1, entries: nextEntries, updatedAt: now };
  assertPatternMemoryStoreValid(nextStore);
  return nextStore;
}

export function recordPatternReuse(store: PatternMemoryStore, entryId: string, now = Date.now()): PatternMemoryStore {
  const nextEntries = store.entries.map((e) =>
    e.id === entryId
      ? { ...e, reuseCount: e.reuseCount + 1, lastUsedAt: now }
      : e,
  );
  const nextStore: PatternMemoryStore = { version: 1, entries: nextEntries, updatedAt: now };
  assertPatternMemoryStoreValid(nextStore);
  return nextStore;
}

export function verifyPatternEntry(store: PatternMemoryStore, entryId: string, localExecutable: boolean, now = Date.now()): PatternMemoryStore {
  const nextEntries = store.entries.map((e) =>
    e.id === entryId
      ? { ...e, verified: true, localExecutable, updatedAt: now }
      : e,
  );
  const nextStore: PatternMemoryStore = { version: 1, entries: nextEntries, updatedAt: now };
  assertPatternMemoryStoreValid(nextStore);
  return nextStore;
}

export function queryPatternEntries(store: PatternMemoryStore, query: PatternMemoryQuery = {}): LearnedPatternEntry[] {
  const limit = Math.max(1, Math.min(query.limit ?? 50, 200));
  const minReuse = query.minReuseCount ?? 0;

  return store.entries
    .filter((e) => !query.ownerScope || e.ownerScope === query.ownerScope)
    .filter((e) => query.verified === undefined || e.verified === query.verified)
    .filter((e) => query.localExecutable === undefined || e.localExecutable === query.localExecutable)
    .filter((e) => !query.tag || e.tags.includes(normalizeTag(query.tag)))
    .filter((e) => e.reuseCount >= minReuse)
    .sort((a, b) => b.reuseCount - a.reuseCount || (b.lastUsedAt ?? 0) - (a.lastUsedAt ?? 0) || b.createdAt - a.createdAt)
    .slice(0, limit);
}

export function eraseUserPatterns(store: PatternMemoryStore, now = Date.now()): { store: PatternMemoryStore; result: PatternMemoryEraseResult } {
  const retained = store.entries.filter((e) => e.ownerScope === 'shared-derived');
  const erasedCount = store.entries.length - retained.length;
  const nextStore: PatternMemoryStore = { version: 1, entries: retained, updatedAt: now };
  assertPatternMemoryStoreValid(nextStore);

  return {
    store: nextStore,
    result: {
      erasedCount,
      remainingCount: retained.length,
      summary: `${erasedCount} user pattern(s) erased. ${retained.length} shared-derived pattern(s) retained (no personal data).`,
    },
  };
}

export function derivePatternMemoryCounters(store: PatternMemoryStore): PatternMemoryRuntimeCounters {
  const entries = store.entries;
  const verifiedEntries = entries.filter((e) => e.verified);
  const localExecutableEntries = entries.filter((e) => e.localExecutable);
  const frequentlyUsed = entries.filter((e) => e.reuseCount >= FREQUENTLY_USED_THRESHOLD);

  const allLastUsed = entries.map((e) => e.lastUsedAt).filter((t): t is number => t !== null);
  const lastSuccessfulReuseAt = allLastUsed.length > 0 ? Math.max(...allLastUsed) : null;

  return {
    totalStored: entries.length,
    verifiedCount: verifiedEntries.length,
    localExecutableCount: localExecutableEntries.length,
    frequentlyUsedCount: frequentlyUsed.length,
    lastSuccessfulReuseAt,
    localUserCount: entries.filter((e) => e.ownerScope === 'local-user').length,
    remoteUserCount: entries.filter((e) => e.ownerScope === 'remote-user').length,
    sharedDerivedCount: entries.filter((e) => e.ownerScope === 'shared-derived').length,
  };
}

export function buildPatternMemorySummaryText(counters: PatternMemoryRuntimeCounters): string {
  const parts: string[] = [];
  parts.push(`${counters.totalStored} gespeicherte Pattern`);
  if (counters.verifiedCount > 0) parts.push(`${counters.verifiedCount} geprüfte lokale Abläufe`);
  if (counters.localExecutableCount > 0) parts.push(`${counters.localExecutableCount} lokal ausführbare Schritte`);
  if (counters.frequentlyUsedCount > 0) parts.push(`${counters.frequentlyUsedCount} häufig genutzte Workflows`);
  return parts.join('\n');
}
