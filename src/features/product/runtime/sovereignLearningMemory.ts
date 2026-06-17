export type LearningMemoryNode =
  | 'repo-snapshot'
  | 'readiness-report'
  | 'file-integrity'
  | 'generated-file-review'
  | 'diff-preview'
  | 'workflow-watch'
  | 'workflow-repair-plan'
  | 'health-report'
  | 'telemetry'
  | 'user-mission'
  | 'action-builder'
  | 'draft-pr-publisher';

export type LearningMemoryKind = 'risk' | 'repair' | 'workflow' | 'guard' | 'docs' | 'user-intent' | 'system-pattern';
export type LearningMemoryConfidence = 'observed' | 'inferred' | 'manual';

export interface LearningMemoryPattern {
  id: string;
  kind: LearningMemoryKind;
  sourceNode: LearningMemoryNode;
  outputNodes: LearningMemoryNode[];
  summary: string;
  evidence: string;
  tags: string[];
  confidence: LearningMemoryConfidence;
  hits: number;
  createdAt: number;
  updatedAt: number;
}

export interface LearningMemoryIntake {
  kind: LearningMemoryKind;
  sourceNode: LearningMemoryNode;
  outputNodes: LearningMemoryNode[];
  summary: string;
  evidence: string;
  tags?: string[];
  confidence: LearningMemoryConfidence;
  now?: number;
}

export interface LearningMemoryValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export interface LearningMemoryStore {
  version: 1;
  patterns: LearningMemoryPattern[];
  updatedAt: number;
}

export interface LearningMemoryQuery {
  outputNode?: LearningMemoryNode;
  kind?: LearningMemoryKind;
  tag?: string;
  minHits?: number;
  limit?: number;
}

const KNOWN_NODES: LearningMemoryNode[] = [
  'repo-snapshot',
  'readiness-report',
  'file-integrity',
  'generated-file-review',
  'diff-preview',
  'workflow-watch',
  'workflow-repair-plan',
  'health-report',
  'telemetry',
  'user-mission',
  'action-builder',
  'draft-pr-publisher',
];

const SECRET_PATTERNS = [
  /ghp_[A-Za-z0-9_]{8,}/g,
  /github_pat_[A-Za-z0-9_]+/g,
  /sk-[A-Za-z0-9_-]{12,}/g,
  /Bearer\s+[A-Za-z0-9._~+/=-]{10,}/gi,
  /password\s*[:=]\s*[^\s]+/gi,
  /token\s*[:=]\s*[^\s]+/gi,
];

const MAX_PATTERNS = 250;
const MAX_TEXT = 1200;
const MAX_TAGS = 12;

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function sanitizeText(value: string): string {
  let output = value.trim().slice(0, MAX_TEXT);
  for (const pattern of SECRET_PATTERNS) {
    output = output.replace(pattern, '<redacted-secret>');
  }
  return output;
}

function normalizeTag(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9:_-]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
}

function hasSecret(value: string): boolean {
  return SECRET_PATTERNS.some((pattern) => {
    pattern.lastIndex = 0;
    return pattern.test(value);
  });
}

function knownNode(node: string): node is LearningMemoryNode {
  return KNOWN_NODES.includes(node as LearningMemoryNode);
}

export function createLearningMemoryStore(now = Date.now()): LearningMemoryStore {
  return { version: 1, patterns: [], updatedAt: now };
}

export function buildLearningMemoryPattern(input: LearningMemoryIntake): LearningMemoryPattern {
  const now = input.now ?? Date.now();
  const summary = sanitizeText(input.summary);
  const evidence = sanitizeText(input.evidence);
  const tags = Array.from(new Set((input.tags ?? []).map(normalizeTag).filter(Boolean))).slice(0, MAX_TAGS);
  const id = `learn-${stableHash([
    input.kind,
    input.sourceNode,
    input.outputNodes.join(','),
    summary,
    evidence,
    tags.join(','),
  ].join('|'))}`;

  return {
    id,
    kind: input.kind,
    sourceNode: input.sourceNode,
    outputNodes: Array.from(new Set(input.outputNodes)),
    summary,
    evidence,
    tags,
    confidence: input.confidence,
    hits: 1,
    createdAt: now,
    updatedAt: now,
  };
}

export function validateLearningMemoryPattern(pattern: LearningMemoryPattern): LearningMemoryValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!pattern.id.trim()) errors.push('Pattern id is required.');
  if (!knownNode(pattern.sourceNode)) errors.push(`Unknown source node: ${pattern.sourceNode}`);
  if (!pattern.outputNodes.length) errors.push('At least one output node is required.');
  for (const node of pattern.outputNodes) {
    if (!knownNode(node)) errors.push(`Unknown output node: ${node}`);
  }
  if (!pattern.summary.trim()) errors.push('Pattern summary is required.');
  if (!pattern.evidence.trim()) errors.push('Pattern evidence is required.');
  if (pattern.summary.length > MAX_TEXT) errors.push('Pattern summary is too long.');
  if (pattern.evidence.length > MAX_TEXT) errors.push('Pattern evidence is too long.');
  if (hasSecret(pattern.summary) || hasSecret(pattern.evidence) || pattern.tags.some(hasSecret)) {
    errors.push('Pattern contains unredacted secret-like content.');
  }
  if (pattern.hits < 1 || !Number.isFinite(pattern.hits)) errors.push('Pattern hits must be a positive number.');
  if (pattern.createdAt > pattern.updatedAt) errors.push('Pattern createdAt must not be newer than updatedAt.');
  if (pattern.confidence === 'inferred' && pattern.evidence.length < 12) {
    warnings.push('Inferred pattern has weak evidence.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in learning memory pattern.`,
  };
}

export function assertLearningMemoryPatternValid(pattern: LearningMemoryPattern): void {
  const report = validateLearningMemoryPattern(pattern);
  if (!report.valid) {
    throw new Error(`Learning memory pattern is invalid: ${report.errors.join(' | ')}`);
  }
}

export function validateLearningMemoryStore(store: LearningMemoryStore): LearningMemoryValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (store.version !== 1) errors.push('Unsupported learning memory store version.');
  if (store.patterns.length > MAX_PATTERNS) errors.push(`Learning memory store exceeds ${MAX_PATTERNS} patterns.`);

  const ids = new Set<string>();
  for (const pattern of store.patterns) {
    if (ids.has(pattern.id)) errors.push(`Duplicate learning pattern id: ${pattern.id}`);
    ids.add(pattern.id);
    const report = validateLearningMemoryPattern(pattern);
    errors.push(...report.errors.map((error) => `${pattern.id}: ${error}`));
    warnings.push(...report.warnings.map((warning) => `${pattern.id}: ${warning}`));
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${store.patterns.length} learning pattern(s), ${errors.length} error(s), ${warnings.length} warning(s).`,
  };
}

export function assertLearningMemoryStoreValid(store: LearningMemoryStore): void {
  const report = validateLearningMemoryStore(store);
  if (!report.valid) {
    throw new Error(`Learning memory store is invalid: ${report.errors.join(' | ')}`);
  }
}

export function addLearningMemoryPattern(store: LearningMemoryStore, pattern: LearningMemoryPattern, now = Date.now()): LearningMemoryStore {
  assertLearningMemoryPatternValid(pattern);
  assertLearningMemoryStoreValid(store);

  const existing = store.patterns.find((item) => item.id === pattern.id);
  const nextPatterns = existing
    ? store.patterns.map((item) => item.id === pattern.id
      ? { ...item, hits: item.hits + 1, updatedAt: now }
      : item)
    : [pattern, ...store.patterns].slice(0, MAX_PATTERNS);

  const nextStore = { version: 1 as const, patterns: nextPatterns, updatedAt: now };
  assertLearningMemoryStoreValid(nextStore);
  return nextStore;
}

export function intakeLearningMemory(store: LearningMemoryStore, input: LearningMemoryIntake): LearningMemoryStore {
  const pattern = buildLearningMemoryPattern(input);
  return addLearningMemoryPattern(store, pattern, input.now ?? Date.now());
}

export function queryLearningMemory(store: LearningMemoryStore, query: LearningMemoryQuery = {}): LearningMemoryPattern[] {
  assertLearningMemoryStoreValid(store);
  const minHits = query.minHits ?? 1;
  const limit = Math.max(1, Math.min(query.limit ?? 20, 100));

  return store.patterns
    .filter((pattern) => !query.outputNode || pattern.outputNodes.includes(query.outputNode))
    .filter((pattern) => !query.kind || pattern.kind === query.kind)
    .filter((pattern) => !query.tag || pattern.tags.includes(normalizeTag(query.tag)))
    .filter((pattern) => pattern.hits >= minHits)
    .sort((a, b) => b.updatedAt - a.updatedAt || b.hits - a.hits)
    .slice(0, limit);
}

export function buildLearningMemoryRuntimeSummary(store: LearningMemoryStore): string {
  const report = validateLearningMemoryStore(store);
  const observed = store.patterns.filter((pattern) => pattern.confidence === 'observed').length;
  const inferred = store.patterns.filter((pattern) => pattern.confidence === 'inferred').length;
  const manual = store.patterns.filter((pattern) => pattern.confidence === 'manual').length;
  return `${report.summary} Confidence: ${observed} observed, ${inferred} inferred, ${manual} manual.`;
}
