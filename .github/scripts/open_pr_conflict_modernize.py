from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text('utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected exact block once, found {count}')
    target.write_text(text.replace(old, new, 1), 'utf-8')


# PR #1770: stable non-global detection regexes + single-pass queries/counters.
path = 'src/features/product/runtime/patternMemoryRuntime.ts'
replace_once(path, """const SENSITIVE_PATTERNS = [
  /ghp_[A-Za-z0-9_]{8,}/g,
  /github_pat_[A-Za-z0-9_]+/g,
  /sk-[A-Za-z0-9_-]{12,}/g,
  /Bearer\\s+[A-Za-z0-9._~+/=-]{10,}/gi,
  /password\\s*[:=]\\s*\\S+/gi,
  /token\\s*[:=]\\s*\\S+/gi,
];""", """const SENSITIVE_PATTERNS = [
  /ghp_[A-Za-z0-9_]{8,}/,
  /github_pat_[A-Za-z0-9_]+/,
  /sk-[A-Za-z0-9_-]{12,}/,
  /Bearer\\s+[A-Za-z0-9._~+/=-]{10,}/i,
  /password\\s*[:=]\\s*\\S+/i,
  /token\\s*[:=]\\s*\\S+/i,
];

const SENSITIVE_REPLACE_PATTERNS = [
  /ghp_[A-Za-z0-9_]{8,}/g,
  /github_pat_[A-Za-z0-9_]+/g,
  /sk-[A-Za-z0-9_-]{12,}/g,
  /Bearer\\s+[A-Za-z0-9._~+/=-]{10,}/gi,
  /password\\s*[:=]\\s*\\S+/gi,
  /token\\s*[:=]\\s*\\S+/gi,
];""")
replace_once(path, """  for (const re of SENSITIVE_PATTERNS) {
    re.lastIndex = 0;
    out = out.replace(re, '<redacted>');
  }""", """  for (const re of SENSITIVE_REPLACE_PATTERNS) {
    re.lastIndex = 0;
    out = out.replace(re, '<redacted>');
  }""")
replace_once(path, """function hasSensitive(value: string): boolean {
  return SENSITIVE_PATTERNS.some((re) => {
    re.lastIndex = 0;
    return re.test(value);
  });
}""", """function hasSensitive(value: string): boolean {
  return SENSITIVE_PATTERNS.some((re) => re.test(value));
}""")
replace_once(path, """  const minReuse = query.minReuseCount ?? 0;

  return store.entries
    .filter((e) => !query.ownerScope || e.ownerScope === query.ownerScope)
    .filter((e) => query.verified === undefined || e.verified === query.verified)
    .filter((e) => query.localExecutable === undefined || e.localExecutable === query.localExecutable)
    .filter((e) => !query.tag || e.tags.includes(normalizeTag(query.tag)))
    .filter((e) => e.reuseCount >= minReuse)""", """  const minReuse = query.minReuseCount ?? 0;
  const normalizedTag = query.tag ? normalizeTag(query.tag) : null;

  return store.entries
    .filter((e) => {
      if (query.ownerScope && e.ownerScope !== query.ownerScope) return false;
      if (query.verified !== undefined && e.verified !== query.verified) return false;
      if (query.localExecutable !== undefined && e.localExecutable !== query.localExecutable) return false;
      if (normalizedTag && !e.tags.includes(normalizedTag)) return false;
      if (e.reuseCount < minReuse) return false;
      return true;
    })""")
replace_once(path, """export function derivePatternMemoryCounters(store: PatternMemoryStore): PatternMemoryRuntimeCounters {
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
}""", """export function derivePatternMemoryCounters(store: PatternMemoryStore): PatternMemoryRuntimeCounters {
  const entries = store.entries;
  let verifiedCount = 0;
  let localExecutableCount = 0;
  let frequentlyUsedCount = 0;
  let localUserCount = 0;
  let remoteUserCount = 0;
  let sharedDerivedCount = 0;
  let lastSuccessfulReuseAt: number | null = null;

  for (const entry of entries) {
    if (entry.verified) verifiedCount += 1;
    if (entry.localExecutable) localExecutableCount += 1;
    if (entry.reuseCount >= FREQUENTLY_USED_THRESHOLD) frequentlyUsedCount += 1;
    if (entry.ownerScope === 'local-user') localUserCount += 1;
    else if (entry.ownerScope === 'remote-user') remoteUserCount += 1;
    else if (entry.ownerScope === 'shared-derived') sharedDerivedCount += 1;
    if (entry.lastUsedAt !== null && (lastSuccessfulReuseAt === null || entry.lastUsedAt > lastSuccessfulReuseAt)) {
      lastSuccessfulReuseAt = entry.lastUsedAt;
    }
  }

  return {
    totalStored: entries.length,
    verifiedCount,
    localExecutableCount,
    frequentlyUsedCount,
    lastSuccessfulReuseAt,
    localUserCount,
    remoteUserCount,
    sharedDerivedCount,
  };
}""")

# PR #1774: single-pass token filter with one hoisted numeric regex.
path = 'src/mobile-workflow-pattern-rules.ts'
replace_once(path, """function extractLearningTerms(visibleText: string): string[] {
  const normalized = normalizeMobileWorkflowText(visibleText);
  if (!normalized) return [];

  const tokens = normalized
    .split(' ')
    .filter((token) => token.length >= 4)
    .filter((token) => !LEARNING_STOP_WORDS.has(token))
    .filter((token) => !/^\\d+$/.test(token));""", """const NUMERIC_ONLY = /^\\d+$/;

function extractLearningTerms(visibleText: string): string[] {
  const normalized = normalizeMobileWorkflowText(visibleText);
  if (!normalized) return [];

  const rawTokens = normalized.split(' ');
  const tokens: string[] = [];
  for (const token of rawTokens) {
    if (token.length >= 4 && !LEARNING_STOP_WORDS.has(token) && !NUMERIC_ONLY.test(token)) {
      tokens.push(token);
    }
  }""")

# PR #1785: single-pass active pattern counters and focused regression.
Path('src/features/product/runtime/patternMemoryContainerRuntime.ts').write_text("""import {
  buildSolutionPatternRuntimeSummary,
  validateSolutionPatternStore,
  type SolutionPatternStore,
} from './solutionPatternMemory';

export interface PatternMemoryContainerState {
  valid: boolean;
  activePatterns: number;
  rejectedItems: number;
  completedPatterns: number;
  reportedPatterns: number;
  totalHits: number;
  summary: string;
}

export function derivePatternMemoryContainerState(store: SolutionPatternStore): PatternMemoryContainerState {
  const validation = validateSolutionPatternStore(store);
  let activePatterns = 0;
  let completedPatterns = 0;
  let reportedPatterns = 0;
  let totalHits = 0;

  for (const pattern of store.patterns) {
    if (pattern.status !== 'active') continue;
    activePatterns += 1;
    if (pattern.confidence === 'completed') completedPatterns += 1;
    else if (pattern.confidence === 'reported') reportedPatterns += 1;
    totalHits += pattern.hits;
  }

  return {
    valid: validation.valid,
    activePatterns,
    rejectedItems: store.rejections.length,
    completedPatterns,
    reportedPatterns,
    totalHits,
    summary: validation.valid ? buildSolutionPatternRuntimeSummary(store) : validation.summary,
  };
}

export function canClearPatternMemory(store: SolutionPatternStore): boolean {
  return store.patterns.length > 0 || store.rejections.length > 0;
}
""", 'utf-8')
Path('src/features/product/runtime/patternMemoryContainerRuntime.test.ts').write_text("""import { describe, expect, it } from 'vitest';
import { canClearPatternMemory, derivePatternMemoryContainerState } from './patternMemoryContainerRuntime';
import type { SolutionPattern, SolutionPatternStore } from './solutionPatternMemory';

function pattern(id: string, status: SolutionPattern['status'], confidence: SolutionPattern['confidence'], hits: number): SolutionPattern {
  return {
    id,
    status,
    problemSignature: `sig-${id}`,
    contextFingerprint: `ctx-${id}`,
    fixFingerprint: `fix-${id}`,
    category: 'logic',
    filePathHint: `src/${id}.ts`,
    fileExtension: '.ts',
    problemSummary: `Problem ${id}`,
    beforeFingerprint: `before-${id}`,
    solutionSummary: `Solution ${id}`,
    afterFingerprint: `after-${id}`,
    conditions: ['condition'],
    recommendedSteps: ['step'],
    evidence: `proof-${id}`,
    intakeNode: 'action-builder',
    processingNode: 'learning-memory',
    outputNodes: ['action-builder'],
    confidence,
    tags: [id],
    hits,
    successfulUses: 0,
    rejectedUses: 0,
    createdAt: 1000,
    updatedAt: 1000,
  };
}

describe('patternMemoryContainerRuntime', () => {
  it('derives active counters and hits without counting rejected patterns', () => {
    const store: SolutionPatternStore = {
      version: 1,
      updatedAt: 1000,
      patterns: [
        pattern('p1', 'active', 'completed', 5),
        pattern('p2', 'active', 'reported', 3),
        pattern('p3', 'rejected', 'completed', 10),
        pattern('p4', 'active', 'manual', 2),
      ],
      rejections: [{ id: 'r1', reason: 'rejected', errors: [], warnings: [], at: 1000 }],
    };
    const derived = derivePatternMemoryContainerState(store);
    expect(derived.activePatterns).toBe(3);
    expect(derived.completedPatterns).toBe(1);
    expect(derived.reportedPatterns).toBe(1);
    expect(derived.totalHits).toBe(10);
    expect(derived.rejectedItems).toBe(1);
    expect(canClearPatternMemory(store)).toBe(true);
  });

  it('handles an empty store', () => {
    const store: SolutionPatternStore = { version: 1, patterns: [], rejections: [], updatedAt: 0 };
    expect(derivePatternMemoryContainerState(store)).toMatchObject({
      activePatterns: 0,
      completedPatterns: 0,
      reportedPatterns: 0,
      totalHits: 0,
      rejectedItems: 0,
    });
    expect(canClearPatternMemory(store)).toBe(false);
  });
});
""", 'utf-8')

# PR #1811: single-pass category/summary accumulation and native deterministic sorting.
path = 'src/features/product/runtime/brownfieldExplorer.ts'
replace_once(path, """function scoreFor(findings: BrownfieldFinding[], category: BrownfieldCategory, maxWeight: number): number {
  const weight = findings
    .filter((finding) => finding.category === category)
    .reduce((total, finding) => total + severityWeight(finding.severity), 0);
  return Math.min(100, Math.round((weight / maxWeight) * 100));
}

function categoryScore(findings: BrownfieldFinding[]): BrownfieldScore {
  const naming = scoreFor(findings, 'naming', 24);
  const testCoverage = scoreFor(findings, 'test-coverage', 20);
  const patternHealth = scoreFor(findings, 'pattern-inconsistency', 16);
  const dependency = scoreFor(findings, 'dependency', 12);
  const size = scoreFor(findings, 'size', 30);
  const treeIntegrity = scoreFor(findings, 'tree-integrity', 20);""", """function categoryScore(findings: BrownfieldFinding[]): BrownfieldScore {
  const weights: Record<BrownfieldCategory, number> = {
    naming: 0,
    'test-coverage': 0,
    'pattern-inconsistency': 0,
    dependency: 0,
    size: 0,
    'tree-integrity': 0,
  };
  for (const finding of findings) weights[finding.category] += severityWeight(finding.severity);
  const naming = Math.min(100, Math.round((weights.naming / 24) * 100));
  const testCoverage = Math.min(100, Math.round((weights['test-coverage'] / 20) * 100));
  const patternHealth = Math.min(100, Math.round((weights['pattern-inconsistency'] / 16) * 100));
  const dependency = Math.min(100, Math.round((weights.dependency / 12) * 100));
  const size = Math.min(100, Math.round((weights.size / 30) * 100));
  const treeIntegrity = Math.min(100, Math.round((weights['tree-integrity'] / 20) * 100));""")
replace_once(path, ".sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))", ".sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))")
replace_once(path, """function buildBrownfieldSummary(score: BrownfieldScore, findings: BrownfieldFinding[]): string {
  const critical = findings.filter((finding) => finding.severity === 'critical').length;
  const warnings = findings.filter((finding) => finding.severity === 'warn').length;""", """function buildBrownfieldSummary(score: BrownfieldScore, findings: BrownfieldFinding[]): string {
  let critical = 0;
  let warnings = 0;
  for (const finding of findings) {
    if (finding.severity === 'critical') critical += 1;
    else if (finding.severity === 'warn') warnings += 1;
  }""")
replace_once(path, "return bySeverity || a.id.localeCompare(b.id);", "return bySeverity || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);")

# PR #1830: one state pass for latest-by-stage and one summary counter pass.
path = 'src/features/product/runtime/sovereignTelemetry.ts'
replace_once(path, """  const ids = new Set<string>();
  for (const event of state.events) {
    if (ids.has(event.id)) warnings.push(`Duplicate telemetry event id: ${event.id}`);
    ids.add(event.id);
    const report = validateTelemetryEvent(event);
    errors.push(...report.errors.map((error) => `${event.label || event.id}: ${error}`));
    warnings.push(...report.warnings.map((warning) => `${event.label || event.id}: ${warning}`));
  }

  for (const [stage, event] of Object.entries(state.latestByStage)) {
    if (!TELEMETRY_STAGES.includes(stage as SovereignTelemetryStage)) errors.push(`Unknown latest telemetry stage: ${stage}`);
    const latest = state.events.filter((item) => item.stage === stage).slice(-1)[0];""", """  const ids = new Set<string>();
  const actualLatestByStage: Partial<Record<SovereignTelemetryStage, SovereignTelemetryEvent>> = {};
  for (const event of state.events) {
    if (ids.has(event.id)) warnings.push(`Duplicate telemetry event id: ${event.id}`);
    ids.add(event.id);
    const report = validateTelemetryEvent(event);
    errors.push(...report.errors.map((error) => `${event.label || event.id}: ${error}`));
    warnings.push(...report.warnings.map((warning) => `${event.label || event.id}: ${warning}`));
    actualLatestByStage[event.stage] = event;
  }

  for (const [stage, event] of Object.entries(state.latestByStage)) {
    if (!TELEMETRY_STAGES.includes(stage as SovereignTelemetryStage)) errors.push(`Unknown latest telemetry stage: ${stage}`);
    const latest = actualLatestByStage[stage as SovereignTelemetryStage];""")
replace_once(path, """  const errorCount = state.events.filter((event) => event.level === 'error').length;
  const warningCount = state.events.filter((event) => event.level === 'warning').length;""", """  let errorCount = 0;
  let warningCount = 0;
  for (const event of state.events) {
    if (event.level === 'error') errorCount += 1;
    else if (event.level === 'warning') warningCount += 1;
  }""")
