import type { ScanFindingCategory, ScanFindingSeverity } from './scanFindingRegistry';

export type SolutionPatternNode =
  | 'scan-finding-registry'
  | 'workflow-watch'
  | 'workflow-repair-plan'
  | 'generated-file-diff'
  | 'generated-file-review'
  | 'action-builder'
  | 'draft-pr-publisher'
  | 'learning-memory'
  | 'telemetry';

export type SolutionPatternConfidence = 'reported' | 'completed' | 'manual' | 'inferred';
export type SolutionPatternStatus = 'active' | 'rejected';

export interface SolutionProblemSnapshot {
  findingId?: string;
  category: ScanFindingCategory;
  severity?: ScanFindingSeverity;
  filePath: string;
  lineNumber?: number;
  description: string;
  beforeSnippet?: string;
  contextPaths: string[];
  contextSignals: string[];
}

export interface SolutionFixSnapshot {
  summary: string;
  afterSnippet?: string;
  changedFiles: string[];
  steps: string[];
  completed: boolean;
  proof?: string;
}

export interface SolutionPatternLearningInput {
  intakeNode: SolutionPatternNode;
  processingNode: SolutionPatternNode;
  outputNodes: SolutionPatternNode[];
  problem: SolutionProblemSnapshot;
  fix: SolutionFixSnapshot;
  confidence: SolutionPatternConfidence;
  tags?: string[];
  now?: number;
}

export interface SolutionPattern {
  id: string;
  status: SolutionPatternStatus;
  problemSignature: string;
  contextFingerprint: string;
  fixFingerprint: string;
  category: ScanFindingCategory;
  filePathHint: string;
  fileExtension: string;
  problemSummary: string;
  beforeFingerprint: string;
  solutionSummary: string;
  afterFingerprint: string;
  conditions: string[];
  recommendedSteps: string[];
  evidence: string;
  intakeNode: SolutionPatternNode;
  processingNode: SolutionPatternNode;
  outputNodes: SolutionPatternNode[];
  confidence: SolutionPatternConfidence;
  tags: string[];
  hits: number;
  successfulUses: number;
  rejectedUses: number;
  createdAt: number;
  updatedAt: number;
}

export interface SolutionPatternRejection {
  id: string;
  reason: string;
  errors: string[];
  warnings: string[];
  intakeNode?: SolutionPatternNode;
  filePath?: string;
  at: number;
}

export interface SolutionPatternStore {
  version: 1;
  patterns: SolutionPattern[];
  rejections: SolutionPatternRejection[];
  updatedAt: number;
}

export interface SolutionPatternValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export interface SolutionPatternLearnResult {
  accepted: boolean;
  store: SolutionPatternStore;
  pattern?: SolutionPattern;
  rejection?: SolutionPatternRejection;
  validation: SolutionPatternValidationReport;
  summary: string;
}

export interface SolutionPatternQuery {
  category?: ScanFindingCategory;
  filePath?: string;
  description?: string;
  contextSignals?: string[];
  outputNode?: SolutionPatternNode;
  minSuccesses?: number;
  limit?: number;
}

export interface SolutionPatternMatch {
  pattern: SolutionPattern;
  score: number;
  reasons: string[];
  aha: string;
}

const KNOWN_NODES: SolutionPatternNode[] = [
  'scan-finding-registry',
  'workflow-watch',
  'workflow-repair-plan',
  'generated-file-diff',
  'generated-file-review',
  'action-builder',
  'draft-pr-publisher',
  'learning-memory',
  'telemetry',
];

const MAX_PATTERNS = 300;
const MAX_REJECTIONS = 120;
const MAX_TEXT = 1600;
const MAX_LIST = 24;
const SENSITIVE_TEXT = /(password|credential|private[_-]?key)\s*[:=]\s*\S+/gi;

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function sanitizeText(value = ''): string {
  return value.trim().slice(0, MAX_TEXT).replace(SENSITIVE_TEXT, '<redacted-sensitive>');
}

function hasSensitiveText(value = ''): boolean {
  SENSITIVE_TEXT.lastIndex = 0;
  return SENSITIVE_TEXT.test(value);
}

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9:_./-]+/g, '-').replace(/^-|-$/g, '').slice(0, 80);
}

function normalizeList(values: string[] = []): string[] {
  return Array.from(new Set(values.map((value) => normalizeToken(value)).filter(Boolean))).slice(0, MAX_LIST);
}

function fileExtension(path: string): string {
  const clean = path.toLowerCase().split(/[?#]/)[0];
  const name = clean.split('/').pop() ?? clean;
  const index = name.lastIndexOf('.');
  return index >= 0 ? name.slice(index) : 'no-extension';
}

function textFingerprint(value?: string): string {
  return stableHash(sanitizeText(value ?? '').toLowerCase());
}

function knownNode(node: string): node is SolutionPatternNode {
  return KNOWN_NODES.includes(node as SolutionPatternNode);
}

export function createSolutionPatternStore(now = Date.now()): SolutionPatternStore {
  return { version: 1, patterns: [], rejections: [], updatedAt: now };
}

export function validateSolutionPatternLearningInput(input: SolutionPatternLearningInput): SolutionPatternValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!knownNode(input.intakeNode)) errors.push(`Unknown intake node: ${input.intakeNode}`);
  if (!knownNode(input.processingNode)) errors.push(`Unknown processing node: ${input.processingNode}`);
  if (!input.outputNodes.length) errors.push('At least one output node is required.');
  for (const node of input.outputNodes) if (!knownNode(node)) errors.push(`Unknown output node: ${node}`);

  if (!input.problem.filePath.trim()) errors.push('Problem filePath is required.');
  if (!input.problem.description.trim()) errors.push('Problem description is required.');
  if (!input.fix.summary.trim()) errors.push('Fix summary is required.');
  if (!input.fix.changedFiles.length) errors.push('Fix changedFiles must include at least one file.');
  if (!input.fix.steps.length) errors.push('Fix steps must include at least one step.');
  if (input.confidence === 'completed' && !input.fix.completed) errors.push('Completed confidence requires fix.completed=true.');
  if (input.fix.completed && !input.fix.proof?.trim()) warnings.push('Completed fix should include proof such as clean workflow result or test output.');

  const textFields = [
    input.problem.findingId ?? '',
    input.problem.filePath,
    input.problem.description,
    input.problem.beforeSnippet ?? '',
    ...input.problem.contextPaths,
    ...input.problem.contextSignals,
    input.fix.summary,
    input.fix.afterSnippet ?? '',
    ...input.fix.changedFiles,
    ...input.fix.steps,
    input.fix.proof ?? '',
    ...(input.tags ?? []),
  ];
  if (textFields.some(hasSensitiveText)) errors.push('Learning input contains unredacted sensitive-looking content.');

  return { valid: errors.length === 0, errors, warnings, summary: `${errors.length} error(s), ${warnings.length} warning(s) in solution pattern input.` };
}

export function buildSolutionPattern(input: SolutionPatternLearningInput): SolutionPattern {
  const now = input.now ?? Date.now();
  const problemSummary = sanitizeText(input.problem.description);
  const solutionSummary = sanitizeText(input.fix.summary);
  const contextPaths = normalizeList(input.problem.contextPaths);
  const contextSignals = normalizeList(input.problem.contextSignals);
  const changedFiles = normalizeList(input.fix.changedFiles);
  const steps = input.fix.steps.map(sanitizeText).filter(Boolean).slice(0, MAX_LIST);
  const tags = normalizeList(input.tags ?? []);
  const outputNodes = Array.from(new Set(input.outputNodes));
  const extension = fileExtension(input.problem.filePath);
  const problemSignature = stableHash([input.problem.category, extension, normalizeToken(problemSummary), contextSignals.join(',')].join('|'));
  const contextFingerprint = stableHash([...contextPaths, ...contextSignals].sort().join('|'));
  const fixFingerprint = stableHash([normalizeToken(solutionSummary), changedFiles.join(','), steps.join('|')].join('|'));

  return {
    id: `solve-${stableHash(`${problemSignature}|${contextFingerprint}|${fixFingerprint}`)}`,
    status: 'active',
    problemSignature,
    contextFingerprint,
    fixFingerprint,
    category: input.problem.category,
    filePathHint: sanitizeText(input.problem.filePath),
    fileExtension: extension,
    problemSummary,
    beforeFingerprint: textFingerprint(input.problem.beforeSnippet),
    solutionSummary,
    afterFingerprint: textFingerprint(input.fix.afterSnippet),
    conditions: Array.from(new Set([...contextPaths, ...contextSignals, extension].filter(Boolean))).slice(0, MAX_LIST),
    recommendedSteps: steps,
    evidence: sanitizeText(input.fix.proof || input.fix.afterSnippet || input.fix.summary),
    intakeNode: input.intakeNode,
    processingNode: input.processingNode,
    outputNodes,
    confidence: input.confidence,
    tags,
    hits: 1,
    successfulUses: input.fix.completed ? 1 : 0,
    rejectedUses: 0,
    createdAt: now,
    updatedAt: now,
  };
}

export function validateSolutionPattern(pattern: SolutionPattern): SolutionPatternValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!pattern.id.trim()) errors.push('Pattern id is required.');
  if (pattern.status !== 'active' && pattern.status !== 'rejected') errors.push(`Unknown pattern status: ${pattern.status}`);
  if (!pattern.problemSignature.trim()) errors.push('Problem signature is required.');
  if (!pattern.contextFingerprint.trim()) errors.push('Context fingerprint is required.');
  if (!pattern.fixFingerprint.trim()) errors.push('Fix fingerprint is required.');
  if (!pattern.filePathHint.trim()) errors.push('File path hint is required.');
  if (!pattern.problemSummary.trim()) errors.push('Problem summary is required.');
  if (!pattern.solutionSummary.trim()) errors.push('Solution summary is required.');
  if (!pattern.recommendedSteps.length) errors.push('At least one recommended step is required.');
  if (!pattern.evidence.trim()) errors.push('Evidence is required.');
  if (!knownNode(pattern.intakeNode)) errors.push(`Unknown intake node: ${pattern.intakeNode}`);
  if (!knownNode(pattern.processingNode)) errors.push(`Unknown processing node: ${pattern.processingNode}`);
  if (!pattern.outputNodes.length) errors.push('At least one output node is required.');
  for (const node of pattern.outputNodes) if (!knownNode(node)) errors.push(`Unknown output node: ${node}`);
  if (pattern.hits < 1 || !Number.isFinite(pattern.hits)) errors.push('Hits must be positive.');
  if (pattern.successfulUses < 0 || !Number.isFinite(pattern.successfulUses)) errors.push('successfulUses must be finite and non-negative.');
  if (pattern.rejectedUses < 0 || !Number.isFinite(pattern.rejectedUses)) errors.push('rejectedUses must be finite and non-negative.');
  if (pattern.createdAt > pattern.updatedAt) errors.push('createdAt must not be newer than updatedAt.');
  if (pattern.confidence === 'completed' && pattern.successfulUses < 1) errors.push('Completed pattern requires at least one successful use.');
  if (pattern.confidence === 'reported' && pattern.successfulUses > 0) warnings.push('Reported pattern has successfulUses; consider upgrading confidence to completed.');

  const textFields = [pattern.id, pattern.filePathHint, pattern.problemSummary, pattern.solutionSummary, pattern.evidence, ...pattern.conditions, ...pattern.recommendedSteps, ...pattern.tags];
  if (textFields.some(hasSensitiveText)) errors.push('Pattern contains unredacted sensitive-looking content.');

  return { valid: errors.length === 0, errors, warnings, summary: `${errors.length} error(s), ${warnings.length} warning(s) in solution pattern.` };
}

export function validateSolutionPatternStore(store: SolutionPatternStore): SolutionPatternValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (store.version !== 1) errors.push('Unsupported solution pattern store version.');
  if (store.patterns.length > MAX_PATTERNS) errors.push(`Too many solution patterns: ${store.patterns.length}`);
  if (store.rejections.length > MAX_REJECTIONS) errors.push(`Too many solution pattern rejections: ${store.rejections.length}`);

  const ids = new Set<string>();
  for (const pattern of store.patterns) {
    if (ids.has(pattern.id)) errors.push(`Duplicate solution pattern id: ${pattern.id}`);
    ids.add(pattern.id);
    const report = validateSolutionPattern(pattern);
    errors.push(...report.errors.map((error) => `${pattern.id}: ${error}`));
    warnings.push(...report.warnings.map((warning) => `${pattern.id}: ${warning}`));
  }

  for (const rejection of store.rejections) {
    if (!rejection.id.trim()) errors.push('Rejection id is required.');
    if (!rejection.reason.trim()) errors.push('Rejection reason is required.');
    if (!Number.isFinite(rejection.at) || rejection.at <= 0) errors.push('Rejection timestamp must be positive.');
  }

  return { valid: errors.length === 0, errors, warnings, summary: `${store.patterns.length} solution pattern(s), ${store.rejections.length} rejection(s), ${errors.length} error(s), ${warnings.length} warning(s).` };
}

export function assertSolutionPatternStoreValid(store: SolutionPatternStore): void {
  const report = validateSolutionPatternStore(store);
  if (!report.valid) throw new Error(`Solution pattern store is invalid: ${report.errors.join(' | ')}`);
}

function appendRejection(store: SolutionPatternStore, reason: string, validation: SolutionPatternValidationReport, input: Partial<SolutionPatternLearningInput>, now: number): { store: SolutionPatternStore; rejection: SolutionPatternRejection } {
  const rejection: SolutionPatternRejection = {
    id: `reject-${stableHash(`${reason}|${now}`)}`,
    reason: sanitizeText(reason),
    errors: validation.errors.map(sanitizeText),
    warnings: validation.warnings.map(sanitizeText),
    intakeNode: input.intakeNode,
    filePath: sanitizeText(input.problem?.filePath ?? ''),
    at: now,
  };
  return { rejection, store: { ...store, rejections: [rejection, ...store.rejections].slice(0, MAX_REJECTIONS), updatedAt: now } };
}

export function learnSolutionPattern(store: SolutionPatternStore, input: SolutionPatternLearningInput): SolutionPatternLearnResult {
  const now = input.now ?? Date.now();
  const storeValidation = validateSolutionPatternStore(store);
  if (!storeValidation.valid) {
    const rejected = appendRejection(store, 'Store rejected before learning.', storeValidation, input, now);
    return { accepted: false, store: rejected.store, rejection: rejected.rejection, validation: storeValidation, summary: `Pattern rejected softly: ${storeValidation.summary}` };
  }

  const inputValidation = validateSolutionPatternLearningInput(input);
  if (!inputValidation.valid) {
    const rejected = appendRejection(store, 'Input rejected before pattern build.', inputValidation, input, now);
    return { accepted: false, store: rejected.store, rejection: rejected.rejection, validation: inputValidation, summary: `Pattern rejected softly: ${inputValidation.summary}` };
  }

  const pattern = buildSolutionPattern(input);
  const patternValidation = validateSolutionPattern(pattern);
  if (!patternValidation.valid) {
    const rejected = appendRejection(store, 'Pattern rejected after build.', patternValidation, input, now);
    return { accepted: false, store: rejected.store, rejection: rejected.rejection, validation: patternValidation, summary: `Pattern rejected softly: ${patternValidation.summary}` };
  }

  const existing = store.patterns.find((item) => item.id === pattern.id);
  const nextPatterns = existing
    ? store.patterns.map((item) => item.id === pattern.id ? { ...item, hits: item.hits + 1, successfulUses: item.successfulUses + (input.fix.completed ? 1 : 0), confidence: input.fix.completed ? 'completed' as const : item.confidence, evidence: pattern.evidence || item.evidence, updatedAt: now } : item)
    : [pattern, ...store.patterns].slice(0, MAX_PATTERNS);

  const nextStore = { version: 1 as const, patterns: nextPatterns, rejections: store.rejections, updatedAt: now };
  const nextValidation = validateSolutionPatternStore(nextStore);
  if (!nextValidation.valid) {
    const rejected = appendRejection(store, 'Merged store rejected after learning.', nextValidation, input, now);
    return { accepted: false, store: rejected.store, rejection: rejected.rejection, validation: nextValidation, summary: `Pattern rejected softly: ${nextValidation.summary}` };
  }

  return { accepted: true, store: nextStore, pattern: nextStore.patterns.find((item) => item.id === pattern.id) ?? pattern, validation: nextValidation, summary: existing ? `Solution pattern extended: ${pattern.id}.` : `Solution pattern learned: ${pattern.id}.` };
}

function overlapScore(a: string[], b: string[]): number {
  const left = new Set(a.map(normalizeToken));
  const right = new Set(b.map(normalizeToken));
  let score = 0;
  for (const item of left) if (right.has(item)) score += 1;
  return score;
}

export function validateSolutionPatternMatches(matches: SolutionPatternMatch[]): SolutionPatternValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  for (const match of matches) {
    if (!Number.isFinite(match.score) || match.score < 0) errors.push(`Invalid match score for ${match.pattern.id}.`);
    if (!match.aha.trim()) errors.push(`Missing aha output for ${match.pattern.id}.`);
    if (!match.reasons.length) warnings.push(`Match ${match.pattern.id} has no explanation reasons.`);
    const report = validateSolutionPattern(match.pattern);
    errors.push(...report.errors.map((error) => `${match.pattern.id}: ${error}`));
    warnings.push(...report.warnings.map((warning) => `${match.pattern.id}: ${warning}`));
  }
  return { valid: errors.length === 0, errors, warnings, summary: `${matches.length} solution pattern match(es), ${errors.length} error(s), ${warnings.length} warning(s).` };
}

export function matchSolutionPatterns(store: SolutionPatternStore, query: SolutionPatternQuery): SolutionPatternMatch[] {
  assertSolutionPatternStoreValid(store);
  const limit = Math.max(1, Math.min(query.limit ?? 8, 50));
  const querySignals = normalizeList(query.contextSignals ?? []);
  const queryExtension = query.filePath ? fileExtension(query.filePath) : undefined;
  const queryText = normalizeToken(query.description ?? '');

  const matches = store.patterns
    .filter((pattern) => pattern.status === 'active')
    .filter((pattern) => !query.outputNode || pattern.outputNodes.includes(query.outputNode))
    .filter((pattern) => !query.category || pattern.category === query.category)
    .filter((pattern) => pattern.successfulUses >= (query.minSuccesses ?? 0))
    .map((pattern): SolutionPatternMatch => {
      const reasons: string[] = [];
      let score = 0;
      if (query.category && pattern.category === query.category) { score += 4; reasons.push('same category'); }
      if (queryExtension && pattern.fileExtension === queryExtension) { score += 3; reasons.push('same file extension'); }
      const sharedSignals = overlapScore(pattern.conditions, querySignals);
      if (sharedSignals) { score += sharedSignals * 2; reasons.push(`${sharedSignals} shared context signal(s)`); }
      if (queryText && normalizeToken(pattern.problemSummary).includes(queryText.slice(0, 24))) { score += 2; reasons.push('similar problem wording'); }
      score += Math.min(pattern.successfulUses, 5);
      if (pattern.successfulUses) reasons.push(`${pattern.successfulUses} completed fix proof(s)`);
      return { pattern, score, reasons, aha: `Aha: ${pattern.category} in ${pattern.fileExtension} with ${pattern.conditions.slice(0, 3).join(', ') || 'similar context'} was solved by: ${pattern.solutionSummary}` };
    })
    .filter((match) => match.score > 0)
    .sort((a, b) => b.score - a.score || b.pattern.updatedAt - a.pattern.updatedAt)
    .slice(0, limit);

  validateSolutionPatternMatches(matches);
  return matches;
}

export function buildSolutionPatternRuntimeSummary(store: SolutionPatternStore): string {
  const validation = validateSolutionPatternStore(store);
  const completed = store.patterns.filter((pattern) => pattern.confidence === 'completed').length;
  const reported = store.patterns.filter((pattern) => pattern.confidence === 'reported').length;
  const successProofs = store.patterns.reduce((sum, pattern) => sum + pattern.successfulUses, 0);
  return `${validation.summary} ${completed} completed pattern(s), ${reported} reported pattern(s), ${successProofs} proof-backed success(es).`;
}
