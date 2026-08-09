import { buildGitHubHeaders } from '../../github/githubAuthSession';
import { fetchWorkflowWatchReport, type WorkflowWatchReport } from './workflowWatch';

export type IdleLiveAwarenessMode = 'off' | 'observe' | 'observe-notify';

export interface IdleLiveAwarenessTarget {
  repoUrl: string;
  prUrl: string;
  token?: string;
}

export interface IdleLiveAwarenessObservation {
  repoUrl: string;
  prUrl: string;
  prNumber: number;
  headSha: string;
  checkedAt: number;
  workflow: WorkflowWatchReport;
  terminalGreen: boolean;
  fingerprint: string;
}

export interface IdleLiveAwarenessTransition {
  changed: boolean;
  shouldNotify: boolean;
  reason: 'initial' | 'unchanged' | 'head-changed' | 'became-green' | 'left-green' | 'workflow-changed';
}

export interface IdleLiveAwarenessEventDetail {
  source: 'idle-live-awareness';
  mode: Exclude<IdleLiveAwarenessMode, 'off'>;
  observation: IdleLiveAwarenessObservation;
  transition: IdleLiveAwarenessTransition;
}

export interface IdleLiveAwarenessController {
  stop: () => void;
  probeNow: () => Promise<IdleLiveAwarenessObservation | null>;
}

export interface ParsedPullRequestUrl {
  owner: string;
  repo: string;
  prNumber: number;
}

interface PullRequestResponse {
  number?: number;
  html_url?: string;
  head?: { sha?: string };
}

const MODE_STORAGE_KEY = 'sovereign_idle_live_awareness_mode';
const TARGET_STORAGE_KEY = 'sovereign_idle_live_awareness_pr_url';
const DEFAULT_POLL_MS_WITH_TOKEN = 60_000;
const DEFAULT_POLL_MS_WITHOUT_TOKEN = 300_000;
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

function stableFingerprint(input: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

export function parseIdleAwarenessPullRequestUrl(value: string): ParsedPullRequestUrl | null {
  const match = value.trim().match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)(?:[/?#].*)?$/i);
  if (!match) return null;
  const prNumber = Number(match[3]);
  if (!Number.isInteger(prNumber) || prNumber <= 0) return null;
  return { owner: match[1], repo: match[2].replace(/\.git$/i, ''), prNumber };
}

export function idleAwarenessTargetFromPullRequestUrl(prUrl: string): IdleLiveAwarenessTarget | null {
  const parsed = parseIdleAwarenessPullRequestUrl(prUrl);
  if (!parsed) return null;
  return {
    repoUrl: `https://github.com/${parsed.owner}/${parsed.repo}`,
    prUrl: `https://github.com/${parsed.owner}/${parsed.repo}/pull/${parsed.prNumber}`,
  };
}

export function normalizeIdleLiveAwarenessMode(value: unknown): IdleLiveAwarenessMode {
  return value === 'observe' || value === 'observe-notify' ? value : 'off';
}

export function readIdleLiveAwarenessMode(storage: Pick<Storage, 'getItem'> | null = typeof window === 'undefined' ? null : window.localStorage): IdleLiveAwarenessMode {
  if (!storage) return 'off';
  try {
    return normalizeIdleLiveAwarenessMode(storage.getItem(MODE_STORAGE_KEY));
  } catch {
    return 'off';
  }
}

export function writeIdleLiveAwarenessMode(mode: IdleLiveAwarenessMode, storage: Pick<Storage, 'setItem'> | null = typeof window === 'undefined' ? null : window.localStorage): void {
  if (!storage) return;
  try {
    storage.setItem(MODE_STORAGE_KEY, normalizeIdleLiveAwarenessMode(mode));
  } catch {
    // Consent state must fail closed when browser storage is unavailable.
  }
}

export function readIdleLiveAwarenessPrUrl(storage: Pick<Storage, 'getItem'> | null = typeof window === 'undefined' ? null : window.localStorage): string {
  if (!storage) return '';
  try {
    const value = storage.getItem(TARGET_STORAGE_KEY)?.trim() ?? '';
    return parseIdleAwarenessPullRequestUrl(value) ? value : '';
  } catch {
    return '';
  }
}

export function writeIdleLiveAwarenessPrUrl(prUrl: string, storage: Pick<Storage, 'setItem'> | null = typeof window === 'undefined' ? null : window.localStorage): boolean {
  if (!storage) return false;
  const target = idleAwarenessTargetFromPullRequestUrl(prUrl);
  if (!target || hasSecret(prUrl)) return false;
  try {
    storage.setItem(TARGET_STORAGE_KEY, target.prUrl);
    return true;
  } catch {
    return false;
  }
}

export function isStrictWorkflowGreen(report: WorkflowWatchReport): boolean {
  if (report.errors.length > 0 || report.warnings.length > 0 || report.checks.length === 0) return false;
  return report.checks.every((check) => {
    if (check.status !== 'green') return false;
    const conclusion = (check.conclusion ?? '').toLowerCase();
    return conclusion !== 'skipped' && conclusion !== 'neutral';
  });
}

export function createIdleAwarenessFingerprint(input: {
  prNumber: number;
  headSha: string;
  workflow: WorkflowWatchReport;
}): string {
  const checks = input.workflow.checks
    .map((check) => `${check.name}:${check.status}:${check.conclusion ?? ''}`)
    .sort()
    .join('|');
  return stableFingerprint(`${input.prNumber}:${input.headSha}:${input.workflow.status}:${checks}`);
}

export function evaluateIdleAwarenessTransition(
  previous: IdleLiveAwarenessObservation | null,
  current: IdleLiveAwarenessObservation,
): IdleLiveAwarenessTransition {
  if (!previous) {
    return { changed: true, shouldNotify: current.terminalGreen, reason: 'initial' };
  }
  if (previous.headSha !== current.headSha) {
    return { changed: true, shouldNotify: current.terminalGreen, reason: 'head-changed' };
  }
  if (previous.fingerprint === current.fingerprint) {
    return { changed: false, shouldNotify: false, reason: 'unchanged' };
  }
  if (!previous.terminalGreen && current.terminalGreen) {
    return { changed: true, shouldNotify: true, reason: 'became-green' };
  }
  if (previous.terminalGreen && !current.terminalGreen) {
    return { changed: true, shouldNotify: true, reason: 'left-green' };
  }
  return { changed: true, shouldNotify: false, reason: 'workflow-changed' };
}

export async function fetchIdleLiveAwarenessObservation(
  target: IdleLiveAwarenessTarget,
  fetcher: typeof fetch = fetch,
): Promise<IdleLiveAwarenessObservation> {
  const parsed = parseIdleAwarenessPullRequestUrl(target.prUrl);
  if (!parsed) throw new Error('Idle Live Awareness requires a canonical GitHub pull-request URL.');
  if (hasSecret(target.repoUrl) || hasSecret(target.prUrl)) {
    throw new Error('Idle Live Awareness target contains secret-like content.');
  }

  const headers = buildGitHubHeaders({ token: target.token });
  const response = await fetcher(`https://api.github.com/repos/${parsed.owner}/${parsed.repo}/pulls/${parsed.prNumber}`, { headers });
  if (!response.ok) throw new Error(`Pull request readback returned ${response.status}.`);
  const payload = await response.json() as PullRequestResponse;
  const headSha = payload.head?.sha?.trim() ?? '';
  if (!/^[0-9a-f]{40}$/i.test(headSha)) throw new Error('Pull request readback did not return a valid head SHA.');

  const workflow = await fetchWorkflowWatchReport({
    repoUrl: target.repoUrl,
    token: target.token,
    commitSha: headSha,
    fetcher,
  });
  const checkedAt = Date.now();
  const terminalGreen = isStrictWorkflowGreen(workflow);
  const fingerprint = createIdleAwarenessFingerprint({ prNumber: parsed.prNumber, headSha, workflow });
  return {
    repoUrl: target.repoUrl,
    prUrl: target.prUrl,
    prNumber: parsed.prNumber,
    headSha,
    checkedAt,
    workflow,
    terminalGreen,
    fingerprint,
  };
}

function publishAwarenessEvent(detail: IdleLiveAwarenessEventDetail): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('sovereign:idle-awareness', { detail }));

  if (detail.mode !== 'observe-notify' || !detail.transition.shouldNotify) return;
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;

  const title = detail.observation.terminalGreen
    ? `PR #${detail.observation.prNumber} vollständig grün`
    : `PR #${detail.observation.prNumber} nicht mehr grün`;
  const body = `Head ${detail.observation.headSha.slice(0, 12)} · ${detail.observation.workflow.checks.length} Checks`;
  new Notification(title, { body });
}

export function startIdleLiveAwareness(input: {
  mode: IdleLiveAwarenessMode;
  target: IdleLiveAwarenessTarget;
  isIdle: () => boolean;
  fetcher?: typeof fetch;
  pollMs?: number;
  onObservation?: (observation: IdleLiveAwarenessObservation, transition: IdleLiveAwarenessTransition) => void;
}): IdleLiveAwarenessController {
  let stopped = false;
  let running = false;
  let previous: IdleLiveAwarenessObservation | null = null;
  const fetcher = input.fetcher ?? fetch;
  const pollMs = Math.max(
    30_000,
    input.pollMs ?? (input.target.token ? DEFAULT_POLL_MS_WITH_TOKEN : DEFAULT_POLL_MS_WITHOUT_TOKEN),
  );

  const probeNow = async (): Promise<IdleLiveAwarenessObservation | null> => {
    if (stopped || running || input.mode === 'off' || !input.isIdle()) return null;
    running = true;
    try {
      const observation = await fetchIdleLiveAwarenessObservation(input.target, fetcher);
      const transition = evaluateIdleAwarenessTransition(previous, observation);
      previous = observation;
      input.onObservation?.(observation, transition);
      if (transition.changed) {
        publishAwarenessEvent({
          source: 'idle-live-awareness',
          mode: input.mode,
          observation,
          transition,
        });
      }
      return observation;
    } finally {
      running = false;
    }
  };

  let timer: ReturnType<typeof setInterval> | null = null;
  if (input.mode !== 'off' && typeof window !== 'undefined') {
    void probeNow();
    timer = window.setInterval(() => { void probeNow(); }, pollMs);
  }

  return {
    probeNow,
    stop: () => {
      stopped = true;
      if (timer !== null && typeof window !== 'undefined') window.clearInterval(timer);
      timer = null;
    },
  };
}

export const IDLE_LIVE_AWARENESS_MODE_STORAGE_KEY = MODE_STORAGE_KEY;
export const IDLE_LIVE_AWARENESS_TARGET_STORAGE_KEY = TARGET_STORAGE_KEY;
