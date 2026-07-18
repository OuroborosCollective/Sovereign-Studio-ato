/**
 * Pattern Memory Proposal Runtime — Issue #447
 *
 * Pure runtime logic for deriving a PatternMemoryIntake from workflow context
 * after the caller has supplied accepted server-side learning evidence, and for
 * building the bounded chat projection of that persisted result.
 *
 * No fake state. No mocks in this path. No side-effects — callers own storage.
 */

import {
  type PatternMemoryIntake,
} from './patternMemoryRuntime';

// ── Internal helpers ────────────────────────────────────────────────────────

/** Maximum characters used from the mission text in the pattern title. */
const MAX_TITLE_CHARS = 80;
/** Maximum characters used in the summary field. */
const MAX_SUMMARY_CHARS = 600;

const SENSITIVE_SCRUB = [
  /ghp_[A-Za-z0-9_]{8,}/g,
  /github_pat_[A-Za-z0-9_]+/g,
  /sk-[A-Za-z0-9_-]{12,}/g,
  /Bearer\s+[A-Za-z0-9._~+/=-]{10,}/gi,
  /password\s*[:=]\s*\S+/gi,
  /token\s*[:=]\s*\S+/gi,
];

function scrub(text: string): string {
  let out = text.trim();
  for (const re of SENSITIVE_SCRUB) {
    re.lastIndex = 0;
    out = out.replace(re, '<redacted>');
  }
  return out;
}

function normalizeTag(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9:_-]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 40);
}

/**
 * Builds a stable, human-readable trace ID for a workflow-derived pattern.
 * Does not contain any sensitive data.
 */
function buildWorkflowTraceId(repoOwner: string, repoName: string, mission: string): string {
  const slug = mission
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 40);
  const safeOwner = repoOwner.replace(/[^a-zA-Z0-9_-]/g, '');
  const safeRepo = repoName.replace(/[^a-zA-Z0-9_-]/g, '');
  return `workflow:${safeOwner}:${safeRepo}:${slug}`;
}

// ── Public API ───────────────────────────────────────────────────────────────

export interface WorkflowProposalContext {
  /** The mission / task text the agent executed. */
  readonly mission: string;
  /** GitHub repo owner (e.g. "OuroborosCollective"). Empty string if unknown. */
  readonly repoOwner: string;
  /** GitHub repo name (e.g. "Sovereign-Studio-ato"). Empty string if unknown. */
  readonly repoName: string;
  /** The Draft PR URL produced by the completed workflow. */
  readonly prUrl: string;
  /** Override for Date.now(). Used in tests. */
  readonly now?: number;
}

/**
 * Derives workflow context for an intake. This function does not prove that a
 * learning candidate or vector was accepted; the caller must bind that evidence.
 */
export function derivePatternIntakeFromWorkflow(
  ctx: WorkflowProposalContext,
): PatternMemoryIntake {
  const { mission, repoOwner, repoName, prUrl } = ctx;

  const safeOwner = scrub(repoOwner) || 'unknown';
  const safeRepo = scrub(repoName) || 'unknown';
  const safeMission = scrub(mission);
  const safePrUrl = scrub(prUrl);

  const title = safeMission.slice(0, MAX_TITLE_CHARS) || `${safeOwner}/${safeRepo} Workflow`;

  const summaryParts: string[] = [
    `PR: ${safePrUrl}`,
    `Repo: ${safeOwner}/${safeRepo}`,
    `Mission: ${safeMission}`,
  ];
  const summary = summaryParts.join(' · ').slice(0, MAX_SUMMARY_CHARS);

  const rawTags = ['draft-pr', 'workflow-complete'];
  if (safeRepo !== 'unknown') rawTags.push(safeRepo);

  return {
    ownerScope: 'local-user',
    sourceTraceId: buildWorkflowTraceId(safeOwner, safeRepo, safeMission),
    title,
    summary,
    tags: rawTags.map(normalizeTag).filter(Boolean),
    vectorRef: null,
    objectRef: safePrUrl || null,
    verified: false,
    localExecutable: false,
    now: ctx.now,
  };
}

/**
 * Builds the assistant projection used only after server evidence confirms that
 * the learning candidate and its vector were stored.
 */
export function buildPatternSavedChatText(
  title: string,
  prUrl: string,
  repoOwner: string,
  repoName: string,
): string {
  const repoLabel =
    repoOwner && repoName ? ` · ${repoOwner}/${repoName}` : '';
  const prLabel = prUrl ? `\nPR: ${prUrl}` : '';
  return (
    `✅ Serverseitig bestätigtes Pattern gespeichert: „${title}"${repoLabel}${prLabel}\n` +
    `Lernkandidat und Vektor-Speicherung wurden durch Runtime-Evidence bestätigt.`
  );
}
