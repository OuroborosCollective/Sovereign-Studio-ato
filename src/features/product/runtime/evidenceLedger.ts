/**
 * Evidence Ledger - Typed evidence tracking for Sovereign Studio runtime decisions
 *
 * Provides traceable evidence entries for:
 * - Draft PR status decisions
 * - Workflow Watch status decisions
 * - Repair status decisions
 * - Runtime Status decisions
 * - Validation decisions
 */

export type EvidenceCategory = 'draft-pr' | 'workflow-watch' | 'repair' | 'runtime-status' | 'validation';

export type EvidenceStatus = 'success' | 'failure' | 'unknown' | 'blocked' | 'pending';

export interface EvidenceSource {
  type: 'github-api' | 'local-runtime' | 'user-action' | 'system-check' | 'telemetry';
  detail?: string;
}

export interface EvidenceLocation {
  filePath?: string;
  runId?: string;
  url?: string;
  commitSha?: string;
  branch?: string;
}

export interface EvidenceLedgerEntry {
  id: string;
  category: EvidenceCategory;
  source: EvidenceSource;
  status: EvidenceStatus;
  reason: string;
  timestamp: number;
  location?: EvidenceLocation;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface EvidenceLedger {
  entries: EvidenceLedgerEntry[];
}

export interface EvidenceValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

// Validation constants
const EVIDENCE_CATEGORIES: EvidenceCategory[] = ['draft-pr', 'workflow-watch', 'repair', 'runtime-status', 'validation'];
const EVIDENCE_STATUSES: EvidenceStatus[] = ['success', 'failure', 'unknown', 'blocked', 'pending'];
const EVIDENCE_SOURCE_TYPES: EvidenceSource['type'][] = ['github-api', 'local-runtime', 'user-action', 'system-check', 'telemetry'];
const MAX_REASON_LENGTH = 800;
const MAX_ENTRIES = 200;

const SECRET_PATTERNS = [
  /ghp_[A-Za-z0-9_]{8,}/g,
  /github_pat_[A-Za-z0-9_]+/g,
  /sk-[A-Za-z0-9_-]{12,}/g,
  /Bearer\s+[A-Za-z0-9._~+/=-]{10,}/gi,
  /password\s*[:=]\s*[^\s]+/gi,
  /token\s*[:=]\s*[^\s]+/gi,
];

function hasSecret(value: string): boolean {
  return SECRET_PATTERNS.some((pattern) => {
    pattern.lastIndex = 0;
    return pattern.test(value);
  });
}

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function generateEvidenceId(
  category: EvidenceCategory,
  status: EvidenceStatus,
  reason: string,
  timestamp: number,
): string {
  const seed = `${category}:${status}:${reason}:${timestamp}`;
  return `ev-${stableHash(seed)}`;
}

export function validateEvidenceEntry(entry: EvidenceLedgerEntry): EvidenceValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!entry.id.trim()) errors.push('Evidence entry id is required.');
  if (!EVIDENCE_CATEGORIES.includes(entry.category)) {
    errors.push(`Unknown evidence category: ${entry.category}`);
  }
  if (!EVIDENCE_STATUSES.includes(entry.status)) {
    errors.push(`Unknown evidence status: ${entry.status}`);
  }
  if (!EVIDENCE_SOURCE_TYPES.includes(entry.source.type)) {
    errors.push(`Unknown evidence source type: ${entry.source.type}`);
  }
  if (!entry.reason.trim()) {
    errors.push('Evidence reason is required.');
  }
  if (entry.reason.length > MAX_REASON_LENGTH) {
    errors.push(`Evidence reason exceeds ${MAX_REASON_LENGTH} characters.`);
  }
  if (!Number.isFinite(entry.timestamp) || entry.timestamp <= 0) {
    errors.push('Evidence timestamp must be a positive number.');
  }

  if (entry.location?.filePath) {
    if (entry.location.filePath.includes('..') || entry.location.filePath.startsWith('/')) {
      errors.push('Evidence location filePath contains invalid path traversal.');
    }
    if (hasSecret(entry.location.filePath)) {
      errors.push('Evidence location filePath contains secret-like content.');
    }
  }
  if (entry.location?.url) {
    if (!/^https?:\/\//i.test(entry.location.url)) {
      warnings.push('Evidence location URL is not an HTTP URL.');
    }
    if (hasSecret(entry.location.url)) {
      errors.push('Evidence location URL contains secret-like content.');
    }
  }

  if (hasSecret(entry.reason)) {
    errors.push('Evidence reason contains secret-like content.');
  }
  if (hasSecret(entry.id)) {
    errors.push('Evidence id contains secret-like content.');
  }

  if (entry.metadata) {
    for (const [key, value] of Object.entries(entry.metadata)) {
      if (!key.trim()) errors.push('Evidence metadata key is empty.');
      if (typeof value === 'string' && hasSecret(value)) {
        errors.push(`Evidence metadata ${key} contains secret-like content.`);
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in evidence entry.`,
  };
}

export function assertEvidenceEntryValid(entry: EvidenceLedgerEntry): void {
  const report = validateEvidenceEntry(entry);
  if (!report.valid) {
    throw new Error(`Evidence entry is invalid: ${report.errors.join(' | ')}`);
  }
}

export function validateEvidenceLedger(ledger: EvidenceLedger): EvidenceValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!Array.isArray(ledger.entries)) {
    errors.push('Evidence ledger entries must be an array.');
    return {
      valid: false,
      errors,
      warnings,
      summary: `Invalid evidence ledger: ${errors.join('; ')}`,
    };
  }
  if (ledger.entries.length > MAX_ENTRIES) {
    errors.push(`Evidence ledger has more than ${MAX_ENTRIES} entries.`);
  }

  const ids = new Set<string>();
  for (const entry of ledger.entries) {
    if (ids.has(entry.id)) {
      warnings.push(`Duplicate evidence entry id: ${entry.id}`);
    }
    ids.add(entry.id);
    const report = validateEvidenceEntry(entry);
    errors.push(...report.errors.map((error) => `${entry.id || 'entry'}: ${error}`));
    warnings.push(...report.warnings.map((warning) => `${entry.id || 'entry'}: ${warning}`));
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${ledger.entries.length} evidence entry(ies), ${errors.length} error(s), ${warnings.length} warning(s).`,
  };
}

export function assertEvidenceLedgerValid(ledger: EvidenceLedger): void {
  const report = validateEvidenceLedger(ledger);
  if (!report.valid) {
    throw new Error(`Evidence ledger is invalid: ${report.errors.join(' | ')}`);
  }
}

export interface CreateEvidenceInput {
  category: EvidenceCategory;
  source: EvidenceSource;
  status: EvidenceStatus;
  reason: string;
  timestamp?: number;
  location?: EvidenceLocation;
  metadata?: Record<string, string | number | boolean | null>;
}

export function createEvidenceEntry(input: CreateEvidenceInput): EvidenceLedgerEntry {
  const timestamp = input.timestamp ?? Date.now();
  const safeReason = input.reason.trim().slice(0, MAX_REASON_LENGTH);
  const id = generateEvidenceId(input.category, input.status, safeReason, timestamp);

  const entry: EvidenceLedgerEntry = {
    id,
    category: input.category,
    source: input.source,
    status: input.status,
    reason: safeReason,
    timestamp,
    location: input.location,
    metadata: input.metadata,
  };

  assertEvidenceEntryValid(entry);
  return entry;
}

export function createInitialEvidenceLedger(): EvidenceLedger {
  return { entries: [] };
}

export function appendEvidenceEntry(
  ledger: EvidenceLedger,
  entry: EvidenceLedgerEntry,
  maxEntries = MAX_ENTRIES,
): EvidenceLedger {
  assertEvidenceLedgerValid(ledger);
  assertEvidenceEntryValid(entry);
  return {
    entries: [...ledger.entries, entry].slice(-Math.max(1, maxEntries)),
  };
}

export function getEvidenceByCategory(
  ledger: EvidenceLedger,
  category: EvidenceCategory,
): EvidenceLedgerEntry[] {
  assertEvidenceLedgerValid(ledger);
  return ledger.entries.filter((entry) => entry.category === category);
}

export function getLatestEvidenceByCategory(
  ledger: EvidenceLedger,
  category: EvidenceCategory,
): EvidenceLedgerEntry | undefined {
  const entries = getEvidenceByCategory(ledger, category);
  if (!entries.length) return undefined;
  return entries[entries.length - 1];
}

export function getEvidenceByStatus(
  ledger: EvidenceLedger,
  status: EvidenceStatus,
): EvidenceLedgerEntry[] {
  assertEvidenceLedgerValid(ledger);
  return ledger.entries.filter((entry) => entry.status === status);
}

export function getBlockedOrUnknownEntries(ledger: EvidenceLedger): EvidenceLedgerEntry[] {
  assertEvidenceLedgerValid(ledger);
  return ledger.entries.filter((entry) => entry.status === 'blocked' || entry.status === 'unknown');
}

export function summarizeEvidenceLedger(ledger: EvidenceLedger): string {
  assertEvidenceLedgerValid(ledger);
  if (!ledger.entries.length) return 'Evidence ledger is empty.';

  const byCategory: Partial<Record<EvidenceCategory, number>> = {};
  const byStatus: Partial<Record<EvidenceStatus, number>> = {};
  const blockedOrUnknown = getBlockedOrUnknownEntries(ledger);

  for (const entry of ledger.entries) {
    byCategory[entry.category] = (byCategory[entry.category] ?? 0) + 1;
    byStatus[entry.status] = (byStatus[entry.status] ?? 0) + 1;
  }

  const categorySummary = Object.entries(byCategory)
    .map(([cat, count]) => `${cat}:${count}`)
    .join(' ');
  const statusSummary = Object.entries(byStatus)
    .map(([st, count]) => `${st}:${count}`)
    .join(' ');

  return `${ledger.entries.length} evidence entries. Categories: ${categorySummary}. Statuses: ${statusSummary}. Blocked/unknown: ${blockedOrUnknown.length}.`;
}

export function formatEvidenceEntryLine(entry: EvidenceLedgerEntry): string {
  assertEvidenceEntryValid(entry);
  const date = new Date(entry.timestamp).toISOString();
  const locationText = entry.location
    ? ` [${[entry.location.filePath, entry.location.runId, entry.location.url].filter(Boolean).join('|')}]`
    : '';
  return `[${date}] [${entry.category}] [${entry.status}] [${entry.source.type}] ${entry.reason}${locationText}`;
}

export function filterEvidenceEntries(
  ledger: EvidenceLedger,
  predicate: (entry: EvidenceLedgerEntry) => boolean,
): EvidenceLedgerEntry[] {
  assertEvidenceLedgerValid(ledger);
  return ledger.entries.filter(predicate);
}

export function getEvidenceSummaryByCategory(ledger: EvidenceLedger): Record<EvidenceCategory, { total: number; success: number; failure: number; unknown: number; blocked: number; pending: number }> {
  assertEvidenceLedgerValid(ledger);
  const summary: Record<EvidenceCategory, { total: number; success: number; failure: number; unknown: number; blocked: number; pending: number }> = {
    'draft-pr': { total: 0, success: 0, failure: 0, unknown: 0, blocked: 0, pending: 0 },
    'workflow-watch': { total: 0, success: 0, failure: 0, unknown: 0, blocked: 0, pending: 0 },
    repair: { total: 0, success: 0, failure: 0, unknown: 0, blocked: 0, pending: 0 },
    'runtime-status': { total: 0, success: 0, failure: 0, unknown: 0, blocked: 0, pending: 0 },
    validation: { total: 0, success: 0, failure: 0, unknown: 0, blocked: 0, pending: 0 },
  };

  for (const entry of ledger.entries) {
    summary[entry.category].total++;
    if (entry.status === 'success') summary[entry.category].success++;
    else if (entry.status === 'failure') summary[entry.category].failure++;
    else if (entry.status === 'unknown') summary[entry.category].unknown++;
    else if (entry.status === 'blocked') summary[entry.category].blocked++;
    else if (entry.status === 'pending') summary[entry.category].pending++;
  }

  return summary;
}