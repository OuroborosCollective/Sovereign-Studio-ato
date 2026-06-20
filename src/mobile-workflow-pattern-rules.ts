import type {
  MobileWorkbenchLamp,
  MobileWorkbenchMode,
  MobileWorkbenchTarget,
} from './mobile-workflow-orchestrator';

export type MobileWorkflowPatternId =
  | 'active-work'
  | 'result-review'
  | 'repo-setup'
  | 'runtime-healthy'
  | 'real-stopper'
  | 'awaiting-intent';

export interface MobileWorkflowPatternRule {
  id: MobileWorkflowPatternId;
  priority: number;
  lamp: MobileWorkbenchLamp;
  mode: MobileWorkbenchMode;
  targetNav: MobileWorkbenchTarget;
  autoOpenTarget: boolean;
  title: string;
  summary: string;
  positiveSignals: string[];
  negativeSignals?: string[];
  minScore: number;
  lines: string[];
}

export interface MobileWorkflowPatternMatch {
  rule: MobileWorkflowPatternRule;
  score: number;
  matchedSignals: string[];
}

export interface MobileWorkflowPatternValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export interface MobileWorkflowPatternCandidate {
  rule: MobileWorkflowPatternRule;
  score: number;
  matchedSignals: string[];
  blocked: boolean;
  blockedBySignals: string[];
}

export interface MobileWorkflowPatternMatchExplanation {
  sourceHash: string;
  sourceLength: number;
  normalizedSourceLength: number;
  fallbackUsed: boolean;
  selectedRuleId: MobileWorkflowPatternId;
  consideredRules: number;
  rejectedRules: number;
  reason: string;
}

export interface MobileWorkflowPatternDetailedMatch extends MobileWorkflowPatternMatch {
  candidates: MobileWorkflowPatternCandidate[];
  rejectedCandidates: MobileWorkflowPatternCandidate[];
  explanation: MobileWorkflowPatternMatchExplanation;
}

export interface MobileWorkflowPatternRuleOverride {
  id: MobileWorkflowPatternId;
  addPositiveSignals?: string[];
  addNegativeSignals?: string[];
  removePositiveSignals?: string[];
  removeNegativeSignals?: string[];
  priority?: number;
  minScore?: number;
}

export interface MobileWorkflowPatternLearningSignal {
  visibleText: string;
  expectedPatternId?: MobileWorkflowPatternId;
  rejectedPatternId?: MobileWorkflowPatternId;
  operatorAccepted?: boolean;
  timestamp?: number;
  note?: string;
}

export interface MobileWorkflowPatternLearningSuggestion {
  ruleId: MobileWorkflowPatternId;
  addPositiveSignals: string[];
  addNegativeSignals: string[];
  reason: string;
}

export interface MobileWorkflowPatternLearningReport {
  totalSignals: number;
  usableSignals: number;
  acceptedMatches: number;
  rejectedMatches: number;
  mismatches: number;
  suggestions: MobileWorkflowPatternLearningSuggestion[];
  summary: string;
}

export interface MobileWorkflowPatternRulesHealth {
  valid: boolean;
  ruleCount: number;
  fallbackPresent: boolean;
  fallbackPriorityLowest: boolean;
  ids: MobileWorkflowPatternId[];
  report: MobileWorkflowPatternValidationReport;
}

interface PatternCandidateInternal {
  rule: MobileWorkflowPatternRule;
  score: number;
  matchedSignals: string[];
  blocked: boolean;
  blockedBySignals: string[];
}

const VALID_PATTERN_IDS: readonly MobileWorkflowPatternId[] = [
  'active-work',
  'result-review',
  'repo-setup',
  'runtime-healthy',
  'real-stopper',
  'awaiting-intent',
];

const VALID_LAMPS: readonly MobileWorkbenchLamp[] = ['green', 'yellow', 'red'];

const VALID_MODES: readonly MobileWorkbenchMode[] = [
  'nocode-plan',
  'matrix-work',
  'review-log',
  'repair-log',
];

const VALID_TARGETS: readonly MobileWorkbenchTarget[] = [
  'Repo',
  'Builder',
  'Files',
  'Diff',
  'Live Monitor',
  'Repair',
  null,
];

const LEARNING_STOP_WORDS = new Set([
  'der',
  'die',
  'das',
  'und',
  'oder',
  'mit',
  'ist',
  'sind',
  'ein',
  'eine',
  'einen',
  'the',
  'and',
  'for',
  'with',
  'from',
  'this',
  'that',
  'repo',
  'workflow',
  'runtime',
]);

export const MOBILE_WORKFLOW_PATTERN_RULES: MobileWorkflowPatternRule[] = [
  {
    id: 'real-stopper',
    priority: 100,
    lamp: 'red',
    mode: 'repair-log',
    targetNav: 'Live Monitor',
    autoOpenTarget: true,
    title: 'Stopper erkannt',
    summary: 'Ich halte an und zeige dir automatisch die passende Log-Ansicht.',
    positiveSignals: [
      'validation_failed',
      'validation failed',
      'package build failed',
      'draft pr failed',
      'pr failed',
      'pull request failed',
      'build failed',
      'workflow failed',
      'critical blocker',
      'blockierender fehler',
      'fehlgeschlagen',
      'failed with exit code',
      'type-check failed',
      'type check failed',
      'test failed',
      'deploy failed',
      'fatal error',
      'process completed with exit code 1',
      'cannot install with frozen-lockfile',
      'err_pnpm_outdated_lockfile',
      'github api error',
      'api rate limit',
    ],
    negativeSignals: [
      '0 failed',
      '0 failed step',
      '0 failed step(s)',
      'no active step; 0 completed step(s), 0 failed step(s)',
      'repair plan idle',
      'workflow: idle',
      'no failures',
      'all checks passed',
    ],
    minScore: 1,
    lines: [
      'pattern = real-stopper',
      'open = log-view',
      'next = rewrite-or-repair',
    ],
  },
  {
    id: 'active-work',
    priority: 90,
    lamp: 'green',
    mode: 'matrix-work',
    targetNav: 'Live Monitor',
    autoOpenTarget: true,
    title: 'Ich arbeite',
    summary:
      'Ich zeige den aktiven Arbeitsbereich und halte dich im Arbeitsmonitor auf dem Laufenden.',
    positiveSignals: [
      'läuft',
      'laeuft',
      'running',
      'busy',
      'in progress',
      'is building',
      'is watching',
      'package-build',
      'package build',
      'diff-load',
      'diff load',
      'draft-pr-publish',
      'draft pr publish',
      'draft pr läuft',
      'draft pr running',
      'pr-creation',
      'pr erstellt',
      'pr created',
      'pr wird erstellt',
      'workflow-watch',
      'workflow watch',
      'installing',
      'building',
      'checking',
      'loading repo',
      'repo loading',
      'watching workflow',
      'scan running',
      'telemetry running',
      'repair running',
      'monitor running',
    ],
    negativeSignals: [
      'idle',
      'awaiting intent',
      'bereit fuer auftrag',
      'bereit für auftrag',
      'ready for Auftrag',
    ],
    minScore: 1,
    lines: [
      'pattern = active-work',
      'observe = runtime-step',
      'ui = follow-active-window',
    ],
  },
  {
    id: 'result-review',
    priority: 80,
    lamp: 'green',
    mode: 'review-log',
    targetNav: 'Files',
    autoOpenTarget: true,
    title: 'Ergebnis bereit',
    summary:
      'Die erzeugten Dateien sind bereit. Files und Diff sind jetzt die wichtigen Pruefpunkte.',
    positiveSignals: [
      'self review: accepted',
      'generated-output-accepted',
      'generated output accepted',
      'generated package passed self review',
      'generated files review',
      'pre-publish review',
      'generated file',
      'files ready',
      'diff ready',
      'review accepted',
      'package ready',
      'replacement file ready',
      'complete replacement file',
      'vollstaendige ersatzdatei',
      'vollständige ersatzdatei',
    ],
    negativeSignals: [
      'build a sovereign package first',
      'before creating a draft pr',
      'noch kein sovereign paket',
      'noch kein package',
    ],
    minScore: 1,
    lines: [
      'pattern = result-review',
      'files = ready',
      'next = diff-or-draft-decision',
    ],
  },
  {
    id: 'repo-setup',
    priority: 70,
    lamp: 'yellow',
    mode: 'nocode-plan',
    targetNav: 'Repo',
    autoOpenTarget: true,
    title: 'Repo fehlt',
    summary:
      'Ich brauche zuerst die Repository URL. Oeffne das Zahnrad oder Repo und lade das Projekt.',
    positiveSignals: [
      'repo fehlt',
      'repository fehlt',
      'repo snapshot required',
      'repository snapshot is not ready',
      'noch kein echtes repo',
      'automation needs a loaded repository snapshot',
      'load repository',
      'load repo first',
      'repo url required',
      'repository url required',
      'no repo snapshot',
      'repository required',
      'repo setup',
    ],
    minScore: 1,
    lines: [
      'pattern = repo-setup',
      'need = repository-url',
      'next = load-repo',
    ],
  },
  {
    id: 'runtime-healthy',
    priority: 60,
    lamp: 'green',
    mode: 'review-log',
    targetNav: null,
    autoOpenTarget: false,
    title: 'Checks gesund',
    summary:
      'Runtime und Coverage sehen gesund aus. Du kannst weiter planen oder Dateien pruefen.',
    positiveSignals: [
      'runtime validation coverage',
      'healthy',
      'health green',
      'green gate passed',
      'green gate results',
      'all checks passed',
      'type-check passed',
      'type check passed',
      'test passed',
      'build successful',
      'build passed',
      '21/21 runtime validation',
      'working tree clean',
      'tests passed',
    ],
    negativeSignals: [
      'critical blocker',
      'validation_failed',
      'build failed',
      'workflow failed',
      'test failed',
      'type-check failed',
      'type check failed',
    ],
    minScore: 1,
    lines: [
      'pattern = runtime-healthy',
      'state = stable',
      'next = continue-main-flow',
    ],
  },
  {
    id: 'awaiting-intent',
    priority: 1,
    lamp: 'yellow',
    mode: 'nocode-plan',
    targetNav: 'Builder',
    autoOpenTarget: false,
    title: 'Bereit fuer Auftrag',
    summary:
      'Schreib deinen Wunsch in einfachen Worten. Ich plane danach automatisch und zeige die Arbeit live.',
    positiveSignals: [],
    minScore: 0,
    lines: [
      'pattern = awaiting-intent',
      'need = user-goal',
      'guard = draft-only',
    ],
  },
];

function transliterateGerman(value: string): string {
  return value
    .replace(/ä/g, 'ae')
    .replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue')
    .replace(/ß/g, 'ss')
    .replace(/Ä/g, 'Ae')
    .replace(/Ö/g, 'Oe')
    .replace(/Ü/g, 'Ue');
}

export function normalizeMobileWorkflowText(value: string): string {
  return transliterateGerman(value)
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[_-]+/g, ' ')
    .replace(/[^a-z0-9./:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function canonicalSignal(value: string): string {
  return normalizeMobileWorkflowText(value);
}

function stableHash(value: string): string {
  let hash = 2166136261;

  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }

  return `mwf-${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

function uniqueSignals(values: string[] = []): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const value of values) {
    const trimmed = value.trim();
    const key = canonicalSignal(trimmed);

    if (!key || seen.has(key)) continue;

    seen.add(key);
    result.push(trimmed);
  }

  return result;
}

function targetIsValid(target: MobileWorkbenchTarget): boolean {
  return VALID_TARGETS.some((candidate) => candidate === target);
}

function includesSignal(normalizedSource: string, signal: string): boolean {
  const normalizedSignal = canonicalSignal(signal);
  if (!normalizedSignal) return false;

  return normalizedSource.includes(normalizedSignal);
}

function toPublicCandidate(candidate: PatternCandidateInternal): MobileWorkflowPatternCandidate {
  return {
    rule: candidate.rule,
    score: candidate.score,
    matchedSignals: candidate.matchedSignals,
    blocked: candidate.blocked,
    blockedBySignals: candidate.blockedBySignals,
  };
}

function scoreRule(
  normalizedSource: string,
  rule: MobileWorkflowPatternRule,
): PatternCandidateInternal {
  if (rule.id === 'awaiting-intent') {
    return {
      rule,
      score: 0,
      matchedSignals: [],
      blocked: false,
      blockedBySignals: [],
    };
  }

  const negativeSignals = uniqueSignals(rule.negativeSignals ?? []);
  const blockedBySignals = negativeSignals.filter((signal) =>
    includesSignal(normalizedSource, signal),
  );

  const positiveSignals = uniqueSignals(rule.positiveSignals);
  const matchedSignals = positiveSignals.filter((signal) =>
    includesSignal(normalizedSource, signal),
  );

  return {
    rule,
    score: matchedSignals.length,
    matchedSignals,
    blocked: blockedBySignals.length > 0,
    blockedBySignals,
  };
}

function compareCandidates(a: PatternCandidateInternal, b: PatternCandidateInternal): number {
  return (
    b.rule.priority - a.rule.priority ||
    b.score - a.score ||
    a.rule.id.localeCompare(b.rule.id)
  );
}

function createFallbackMatch(
  rules: MobileWorkflowPatternRule[],
  normalizedSource: string,
  sourceLength: number,
  candidates: PatternCandidateInternal[],
): MobileWorkflowPatternDetailedMatch {
  const fallback = rules.find((rule) => rule.id === 'awaiting-intent');

  if (!fallback) {
    throw new Error('No mobile workflow pattern matched and no fallback pattern exists.');
  }

  const rejectedCandidates = candidates.filter(
    (candidate) => candidate.blocked || candidate.score < candidate.rule.minScore,
  );

  return {
    rule: fallback,
    score: 0,
    matchedSignals: [],
    candidates: candidates.map(toPublicCandidate),
    rejectedCandidates: rejectedCandidates.map(toPublicCandidate),
    explanation: {
      sourceHash: stableHash(normalizedSource),
      sourceLength,
      normalizedSourceLength: normalizedSource.length,
      fallbackUsed: true,
      selectedRuleId: fallback.id,
      consideredRules: candidates.length,
      rejectedRules: rejectedCandidates.length,
      reason: normalizedSource
        ? 'No active pattern reached minScore; fallback awaiting-intent selected.'
        : 'Visible text was empty after normalization; fallback awaiting-intent selected.',
    },
  };
}

function cloneRule(rule: MobileWorkflowPatternRule): MobileWorkflowPatternRule {
  return {
    ...rule,
    positiveSignals: [...rule.positiveSignals],
    negativeSignals: rule.negativeSignals ? [...rule.negativeSignals] : undefined,
    lines: [...rule.lines],
  };
}

function removeSignals(source: string[], removals: string[] = []): string[] {
  const removalKeys = new Set(removals.map(canonicalSignal).filter(Boolean));

  if (removalKeys.size === 0) return [...source];

  return source.filter((signal) => !removalKeys.has(canonicalSignal(signal)));
}

function addSignals(source: string[], additions: string[] = []): string[] {
  return uniqueSignals([...source, ...additions]);
}

function extractLearningTerms(visibleText: string): string[] {
  const normalized = normalizeMobileWorkflowText(visibleText);
  if (!normalized) return [];

  const tokens = normalized
    .split(' ')
    .filter((token) => token.length >= 4)
    .filter((token) => !LEARNING_STOP_WORDS.has(token))
    .filter((token) => !/^\d+$/.test(token));

  const phrases: string[] = [];

  for (let index = 0; index < tokens.length; index += 1) {
    phrases.push(tokens[index]);

    if (tokens[index + 1]) {
      phrases.push(`${tokens[index]} ${tokens[index + 1]}`);
    }
  }

  return uniqueSignals(phrases).slice(0, 10);
}

function createValidationReport(
  errors: string[],
  warnings: string[] = [],
): MobileWorkflowPatternValidationReport {
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} pattern validation error(s), ${warnings.length} warning(s).`,
  };
}

export function validateMobileWorkflowPatternRule(
  rule: MobileWorkflowPatternRule,
): MobileWorkflowPatternValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!rule.id) {
    errors.push('Pattern id is required.');
  } else if (!VALID_PATTERN_IDS.includes(rule.id)) {
    errors.push(`Pattern ${rule.id} has unknown id.`);
  }

  if (!Number.isFinite(rule.priority)) {
    errors.push(`Pattern ${rule.id} priority must be finite.`);
  }

  if (rule.priority < 0) {
    errors.push(`Pattern ${rule.id} priority must be non-negative.`);
  }

  if (!VALID_LAMPS.includes(rule.lamp)) {
    errors.push(`Pattern ${rule.id} has unknown lamp.`);
  }

  if (!VALID_MODES.includes(rule.mode)) {
    errors.push(`Pattern ${rule.id} has unknown mode.`);
  }

  if (!targetIsValid(rule.targetNav)) {
    errors.push(`Pattern ${rule.id} has unknown target.`);
  }

  if (rule.autoOpenTarget && !rule.targetNav) {
    errors.push(`Pattern ${rule.id} auto-open requires target.`);
  }

  if (typeof rule.title !== 'string' || !rule.title.trim()) {
    errors.push(`Pattern ${rule.id} title is required.`);
  }

  if (typeof rule.summary !== 'string' || !rule.summary.trim()) {
    errors.push(`Pattern ${rule.id} summary is required.`);
  }

  if (!Array.isArray(rule.positiveSignals)) {
    errors.push(`Pattern ${rule.id} needs positive signals.`);
  } else if (rule.id !== 'awaiting-intent' && rule.positiveSignals.length === 0) {
    errors.push(`Pattern ${rule.id} needs positive signals.`);
  } else if (
    rule.id !== 'awaiting-intent' &&
    rule.positiveSignals.some((signal) => !signal.trim())
  ) {
    errors.push(`Pattern ${rule.id} has empty positive signal.`);
  } else if (
    rule.id === 'awaiting-intent' &&
    rule.positiveSignals.some((signal) => signal.trim())
  ) {
    errors.push('Fallback pattern awaiting-intent must not use positive signals.');
  }

  if (uniqueSignals(rule.positiveSignals).length !== rule.positiveSignals.length) {
    warnings.push(`Pattern ${rule.id} has duplicate positive signals.`);
  }

  if (rule.negativeSignals?.some((signal) => !signal.trim())) {
    errors.push(`Pattern ${rule.id} has empty negative signal.`);
  }

  if (
    rule.negativeSignals &&
    uniqueSignals(rule.negativeSignals).length !== rule.negativeSignals.length
  ) {
    warnings.push(`Pattern ${rule.id} has duplicate negative signals.`);
  }

  if (!Number.isFinite(rule.minScore) || rule.minScore < 0) {
    errors.push(`Pattern ${rule.id} minScore must be non-negative.`);
  }

  if (rule.id === 'awaiting-intent' && rule.minScore !== 0) {
    errors.push('Fallback pattern awaiting-intent minScore must be 0.');
  }

  if (rule.id !== 'awaiting-intent' && rule.minScore < 1) {
    errors.push(`Pattern ${rule.id} minScore must be at least 1.`);
  }

  if (!Array.isArray(rule.lines) || rule.lines.length === 0) {
    errors.push(`Pattern ${rule.id} needs workbench lines.`);
  } else if (rule.lines.some((line) => !line.trim())) {
    errors.push(`Pattern ${rule.id} has empty workbench line.`);
  }

  return createValidationReport(errors, warnings);
}

export function validateMobileWorkflowPatternRules(
  rules = MOBILE_WORKFLOW_PATTERN_RULES,
): MobileWorkflowPatternValidationReport {
  const errors = rules.flatMap((rule) => validateMobileWorkflowPatternRule(rule).errors);
  const warnings = rules.flatMap((rule) => validateMobileWorkflowPatternRule(rule).warnings);
  const ids = new Set<string>();

  if (!Array.isArray(rules) || rules.length === 0) {
    errors.push('Mobile workflow pattern rules must not be empty.');
  }

  for (const rule of rules) {
    if (ids.has(rule.id)) {
      errors.push(`Duplicate pattern id: ${rule.id}`);
    }

    ids.add(rule.id);
  }

  if (!rules.some((rule) => rule.id === 'awaiting-intent')) {
    errors.push('Fallback pattern awaiting-intent is required.');
  }

  const fallbackCount = rules.filter((rule) => rule.id === 'awaiting-intent').length;

  if (fallbackCount > 1) {
    errors.push('Only one fallback pattern awaiting-intent is allowed.');
  }

  const fallback = rules.find((rule) => rule.id === 'awaiting-intent');
  const nonFallbackRules = rules.filter((rule) => rule.id !== 'awaiting-intent');

  if (fallback && nonFallbackRules.some((rule) => fallback.priority >= rule.priority)) {
    errors.push('Fallback pattern awaiting-intent must have lower priority than all active patterns.');
  }

  for (const rule of rules) {
    const positive = uniqueSignals(rule.positiveSignals);
    const negative = uniqueSignals(rule.negativeSignals ?? []);
    const overlap = positive.filter((signal) =>
      negative.some(
        (negativeSignal) => canonicalSignal(negativeSignal) === canonicalSignal(signal),
      ),
    );

    if (overlap.length > 0) {
      errors.push(
        `Pattern ${rule.id} has overlapping positive and negative signals: ${overlap.join(', ')}`,
      );
    }
  }

  return createValidationReport(errors, warnings);
}

export function assertMobileWorkflowPatternRulesValid(
  rules = MOBILE_WORKFLOW_PATTERN_RULES,
): void {
  const report = validateMobileWorkflowPatternRules(rules);

  if (!report.valid) {
    throw new Error(`Mobile workflow pattern rules invalid: ${report.errors.join(' | ')}`);
  }
}

export function getMobileWorkflowPatternRulesHealth(
  rules = MOBILE_WORKFLOW_PATTERN_RULES,
): MobileWorkflowPatternRulesHealth {
  const report = validateMobileWorkflowPatternRules(rules);
  const fallback = rules.find((rule) => rule.id === 'awaiting-intent');
  const nonFallbackRules = rules.filter((rule) => rule.id !== 'awaiting-intent');

  return {
    valid: report.valid,
    ruleCount: rules.length,
    fallbackPresent: Boolean(fallback),
    fallbackPriorityLowest: Boolean(
      fallback && nonFallbackRules.every((rule) => fallback.priority < rule.priority),
    ),
    ids: rules.map((rule) => rule.id),
    report,
  };
}

export function matchMobileWorkflowPatternDetailed(
  visibleText: string,
  rules = MOBILE_WORKFLOW_PATTERN_RULES,
): MobileWorkflowPatternDetailedMatch {
  assertMobileWorkflowPatternRulesValid(rules);

  const normalizedSource = normalizeMobileWorkflowText(visibleText);
  const candidates = rules.map((rule) => scoreRule(normalizedSource, rule));

  if (!normalizedSource) {
    return createFallbackMatch(rules, normalizedSource, visibleText.length, candidates);
  }

  const eligible = candidates
    .filter((candidate) => candidate.rule.id !== 'awaiting-intent')
    .filter((candidate) => !candidate.blocked)
    .filter((candidate) => candidate.score >= candidate.rule.minScore)
    .sort(compareCandidates);

  if (eligible.length === 0) {
    return createFallbackMatch(rules, normalizedSource, visibleText.length, candidates);
  }

  const selected = eligible[0];
  const rejectedCandidates = candidates.filter(
    (candidate) =>
      candidate.rule.id !== selected.rule.id &&
      (candidate.blocked || candidate.score < candidate.rule.minScore),
  );

  return {
    rule: selected.rule,
    score: selected.score,
    matchedSignals: selected.matchedSignals,
    candidates: candidates.map(toPublicCandidate),
    rejectedCandidates: rejectedCandidates.map(toPublicCandidate),
    explanation: {
      sourceHash: stableHash(normalizedSource),
      sourceLength: visibleText.length,
      normalizedSourceLength: normalizedSource.length,
      fallbackUsed: false,
      selectedRuleId: selected.rule.id,
      consideredRules: candidates.length,
      rejectedRules: rejectedCandidates.length,
      reason: `Selected ${selected.rule.id} by priority ${selected.rule.priority} with score ${selected.score}.`,
    },
  };
}

export function matchMobileWorkflowPattern(
  visibleText: string,
  rules = MOBILE_WORKFLOW_PATTERN_RULES,
): MobileWorkflowPatternMatch {
  const detailed = matchMobileWorkflowPatternDetailed(visibleText, rules);

  return {
    rule: detailed.rule,
    score: detailed.score,
    matchedSignals: detailed.matchedSignals,
  };
}

export function createMobileWorkflowPatternRulesWithOverrides(
  rules: MobileWorkflowPatternRule[] = MOBILE_WORKFLOW_PATTERN_RULES,
  overrides: MobileWorkflowPatternRuleOverride[] = [],
): MobileWorkflowPatternRule[] {
  const overrideById = new Map(overrides.map((override) => [override.id, override]));

  const nextRules = rules.map((rule) => {
    const override = overrideById.get(rule.id);
    if (!override) return cloneRule(rule);

    const next: MobileWorkflowPatternRule = {
      ...cloneRule(rule),
      priority: override.priority ?? rule.priority,
      minScore: override.minScore ?? rule.minScore,
    };

    next.positiveSignals = addSignals(
      removeSignals(next.positiveSignals, override.removePositiveSignals),
      override.addPositiveSignals,
    );

    next.negativeSignals = addSignals(
      removeSignals(next.negativeSignals ?? [], override.removeNegativeSignals),
      override.addNegativeSignals,
    );

    return next;
  });

  assertMobileWorkflowPatternRulesValid(nextRules);

  return nextRules;
}

export function createMobileWorkflowPatternLearningReport(
  signals: MobileWorkflowPatternLearningSignal[],
  rules = MOBILE_WORKFLOW_PATTERN_RULES,
): MobileWorkflowPatternLearningReport {
  assertMobileWorkflowPatternRulesValid(rules);

  let usableSignals = 0;
  let acceptedMatches = 0;
  let rejectedMatches = 0;
  let mismatches = 0;

  const suggestionMap = new Map<MobileWorkflowPatternId, MobileWorkflowPatternLearningSuggestion>();

  function suggestionFor(ruleId: MobileWorkflowPatternId): MobileWorkflowPatternLearningSuggestion {
    const existing = suggestionMap.get(ruleId);
    if (existing) return existing;

    const created: MobileWorkflowPatternLearningSuggestion = {
      ruleId,
      addPositiveSignals: [],
      addNegativeSignals: [],
      reason: 'Derived from explicit operator learning signals.',
    };

    suggestionMap.set(ruleId, created);
    return created;
  }

  for (const signal of signals) {
    const visibleText = signal.visibleText.trim();
    if (!visibleText) continue;

    usableSignals += 1;

    const match = matchMobileWorkflowPattern(visibleText, rules);
    const expectedPatternId = signal.expectedPatternId;
    const rejectedPatternId = signal.rejectedPatternId;

    if (signal.operatorAccepted === true) {
      acceptedMatches += 1;
    }

    if (signal.operatorAccepted === false || rejectedPatternId) {
      rejectedMatches += 1;
    }

    if (expectedPatternId && expectedPatternId !== match.rule.id) {
      mismatches += 1;

      const suggestion = suggestionFor(expectedPatternId);
      suggestion.addPositiveSignals = addSignals(
        suggestion.addPositiveSignals,
        extractLearningTerms(visibleText),
      );
    }

    if (rejectedPatternId) {
      const suggestion = suggestionFor(rejectedPatternId);
      suggestion.addNegativeSignals = addSignals(
        suggestion.addNegativeSignals,
        extractLearningTerms(visibleText),
      );
    }
  }

  const suggestions = Array.from(suggestionMap.values()).map((suggestion) => ({
    ...suggestion,
    addPositiveSignals: uniqueSignals(suggestion.addPositiveSignals),
    addNegativeSignals: uniqueSignals(suggestion.addNegativeSignals),
  }));

  return {
    totalSignals: signals.length,
    usableSignals,
    acceptedMatches,
    rejectedMatches,
    mismatches,
    suggestions,
    summary: `${usableSignals} usable learning signal(s), ${mismatches} mismatch(es), ${suggestions.length} suggestion(s).`,
  };
                        }
