/**
 * Sovereign Agent Workspace Runtime
 *
 * Neutral contract for code-capable agents such as OpenHands.
 * The workspace produces runtime evidence; the UI only displays the resulting state.
 *
 * This module intentionally does not start OpenHands, clone repositories, run shell commands,
 * or create folders. It defines and validates the contract that an external executor must obey.
 */

export type AgentWorkspaceExecutor = 'openhands' | 'external-code-agent' | 'local-runner';
export type AgentWorkspaceHost = 'managed-ephemeral' | 'self-hosted-runner' | 'external-agent-runtime';
export type AgentWorkspaceStatus = 'queued' | 'running' | 'completed' | 'failed' | 'blocked' | 'cleaned';
export type AgentWorkspaceEventLevel = 'info' | 'warning' | 'error';
export type AgentWorkspaceIntentKind = 'none' | 'read-only' | 'code-execution';

export interface AgentWorkspaceEvent {
  readonly level: AgentWorkspaceEventLevel;
  readonly message: string;
  readonly at: number;
}

export interface AgentWorkspaceRequest {
  readonly repoUrl: string;
  readonly branch?: string;
  readonly task: string;
  readonly executor: AgentWorkspaceExecutor;
  readonly allowedPaths?: readonly string[];
  readonly forbiddenPaths?: readonly string[];
  readonly memoryHints?: readonly string[];
  readonly draftPrOnly: true;
  readonly workspaceHost?: AgentWorkspaceHost;
  readonly maxRuntimeMs?: number;
  readonly maxWorkspaceBytes?: number;
}

export interface AgentWorkspaceResult {
  readonly workspaceId: string;
  readonly status: AgentWorkspaceStatus;
  readonly events: readonly AgentWorkspaceEvent[];
  readonly changedFiles: readonly string[];
  readonly diffSummary?: string;
  readonly testSummary?: string;
  readonly draftPrUrl?: string;
  readonly blocker?: string;
  readonly workspaceInspectorUrl?: string;
  readonly cleanedAt?: number;
}

export interface AgentWorkspaceValidationResult {
  readonly allowed: boolean;
  readonly blockers: readonly string[];
  readonly warnings: readonly string[];
}

export interface AgentWorkspaceIntentDecision {
  readonly kind: AgentWorkspaceIntentKind;
  readonly allowed: boolean;
  readonly reason: string;
  readonly executor?: AgentWorkspaceExecutor;
}

const GITHUB_REPO_URL = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\.git)?(?:\/.*)?$/i;
const SAFE_BRANCH = /^[\w./-]{1,160}$/;
const SAFE_RELATIVE_PATH = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))(?!.*\0)[\w .@/+~=-]+$/;
const SECRET_PATTERNS: readonly RegExp[] = [
  /ghp_[A-Za-z0-9_]{20,}/g,
  /github_pat_[A-Za-z0-9_]{20,}/g,
  /sk-[A-Za-z0-9_-]{20,}/g,
  /sk-proj-[A-Za-z0-9_-]{20,}/g,
  /(Authorization:\s*)(Bearer\s+)?[^\s\n]+/gi,
  /((?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s\n]+/gi,
];

const CODE_EXECUTION_SIGNALS = [
  'implement', 'implementation', 'fix', 'repair', 'refactor', 'patch', 'change file', 'modify file',
  'create draft pr', 'draft pr', 'pull request', 'commit', 'run tests', 'add test', 'update code',
  'baue', 'bauen', 'implementiere', 'umsetzen', 'ändere', 'aendere', 'fixe', 'repariere',
  'erstelle draft pr', 'pull request erstellen', 'datei ändern', 'datei aendern', 'tests ausführen',
  'tests ausfuehren', 'code ändern', 'code aendern',
];

const READ_ONLY_SIGNALS = [
  'explain', 'summarize', 'status', 'what happened', 'why', 'read', 'inspect', 'analyse', 'analyze',
  'erklär', 'erklaer', 'zusammenfassen', 'was ist', 'warum', 'prüfe', 'pruefe', 'lies', 'ansehen',
];

function unique(values: readonly string[]): string[] {
  return [...new Set(values)];
}

function trimTo(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

export function sanitizeWorkspaceText(value: string): string {
  return SECRET_PATTERNS.reduce((current, pattern) => current.replace(pattern, (_match, prefix = '') => `${prefix}[redacted]`), value);
}

export function sanitizeWorkspaceEvent(event: AgentWorkspaceEvent): AgentWorkspaceEvent {
  return {
    level: normalizeEventLevel(event.level),
    message: trimTo(sanitizeWorkspaceText(event.message), 1200),
    at: Number.isFinite(event.at) && event.at > 0 ? event.at : Date.now(),
  };
}

export function isSupportedWorkspaceExecutor(value: unknown): value is AgentWorkspaceExecutor {
  return value === 'openhands' || value === 'external-code-agent' || value === 'local-runner';
}

export function isSupportedWorkspaceHost(value: unknown): value is AgentWorkspaceHost {
  return value === 'managed-ephemeral' || value === 'self-hosted-runner' || value === 'external-agent-runtime';
}

export function isTerminalWorkspaceStatus(status: AgentWorkspaceStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'blocked' || status === 'cleaned';
}

export function shouldCleanupWorkspace(status: AgentWorkspaceStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'blocked';
}

export function normalizeWorkspacePath(path: string): string | null {
  const clean = path.trim().replace(/\\+/g, '/').replace(/^\.\//, '');
  if (!clean || !SAFE_RELATIVE_PATH.test(clean)) return null;
  return clean;
}

export function classifyWorkspaceIntent(message: string): AgentWorkspaceIntentKind {
  const normalized = message.toLowerCase().trim();
  if (!normalized) return 'none';

  const codeSignalCount = CODE_EXECUTION_SIGNALS.filter((signal) => normalized.includes(signal)).length;
  const hasFileContext = /\b(src|tests?|android|scripts|\.tsx?|\.jsx?|\.mjs|\.json|\.ya?ml|README\.md)\b/i.test(message);
  const hasDraftPrSignal = /draft\s*pr|pull request|pr erstellen|create pr/i.test(message);

  if (hasDraftPrSignal || codeSignalCount >= 2 || (codeSignalCount >= 1 && hasFileContext)) {
    return 'code-execution';
  }

  if (READ_ONLY_SIGNALS.some((signal) => normalized.includes(signal))) {
    return 'read-only';
  }

  return 'none';
}

export function decideAgentWorkspaceIntent(input: {
  readonly message: string;
  readonly repoReady: boolean;
  readonly executorReady: boolean;
  readonly activeWorkspaceStatus?: AgentWorkspaceStatus | 'idle';
  readonly executor?: AgentWorkspaceExecutor;
}): AgentWorkspaceIntentDecision {
  const kind = classifyWorkspaceIntent(input.message);
  if (kind !== 'code-execution') {
    return {
      kind,
      allowed: false,
      reason: kind === 'read-only'
        ? 'Read-only chat can use repo snapshot, Worker chat, logs or memory without a write workspace.'
        : 'No code-execution intent detected.',
    };
  }

  if (!input.repoReady) {
    return { kind, allowed: false, reason: 'Workspace requires a loaded repository snapshot.' };
  }

  if (!input.executorReady) {
    return { kind, allowed: false, reason: 'Workspace executor is not ready.' };
  }

  if (input.activeWorkspaceStatus && input.activeWorkspaceStatus !== 'idle' && !isTerminalWorkspaceStatus(input.activeWorkspaceStatus)) {
    return { kind, allowed: false, reason: `Workspace already ${input.activeWorkspaceStatus}.` };
  }

  return {
    kind,
    allowed: true,
    reason: 'Code-execution intent may start an isolated workspace job.',
    executor: input.executor || 'openhands',
  };
}

export function validateAgentWorkspaceRequest(request: AgentWorkspaceRequest): AgentWorkspaceValidationResult {
  const blockers: string[] = [];
  const warnings: string[] = [];
  const repoUrl = request.repoUrl.trim();
  const branch = request.branch?.trim() || 'main';
  const task = request.task.trim();

  if (!GITHUB_REPO_URL.test(repoUrl)) blockers.push('Workspace requires a valid HTTPS GitHub repository URL.');
  if (!SAFE_BRANCH.test(branch)) blockers.push('Workspace branch contains unsafe characters.');
  if (!task) blockers.push('Workspace task is required.');
  if (task.length > 8000) blockers.push('Workspace task is too large for a single executor request.');
  if (!isSupportedWorkspaceExecutor(request.executor)) blockers.push('Workspace executor is not supported.');
  if (request.draftPrOnly !== true) blockers.push('Workspace may only run in Draft-PR-only mode.');

  if (request.workspaceHost && !isSupportedWorkspaceHost(request.workspaceHost)) {
    blockers.push('Workspace host is not supported.');
  }

  if (request.workspaceHost === 'self-hosted-runner') {
    warnings.push('Self-hosted runner must enforce its own quota, timeout and cleanup policy.');
  }

  const allowedPaths = request.allowedPaths?.map(normalizeWorkspacePath) ?? [];
  const forbiddenPaths = request.forbiddenPaths?.map(normalizeWorkspacePath) ?? [];
  if (allowedPaths.some((path) => !path)) blockers.push('Workspace allowedPaths contains an unsafe path.');
  if (forbiddenPaths.some((path) => !path)) blockers.push('Workspace forbiddenPaths contains an unsafe path.');

  if (request.maxRuntimeMs !== undefined && (!Number.isFinite(request.maxRuntimeMs) || request.maxRuntimeMs < 30_000)) {
    blockers.push('Workspace maxRuntimeMs must be at least 30000 when provided.');
  }

  if (request.maxWorkspaceBytes !== undefined && (!Number.isFinite(request.maxWorkspaceBytes) || request.maxWorkspaceBytes < 50_000_000)) {
    blockers.push('Workspace maxWorkspaceBytes must be at least 50000000 when provided.');
  }

  const combinedText = [task, ...(request.memoryHints ?? [])].join('\n');
  if (combinedText !== sanitizeWorkspaceText(combinedText)) {
    blockers.push('Workspace request contains a secret-like value and must be sanitized before dispatch.');
  }

  return { allowed: blockers.length === 0, blockers: unique(blockers), warnings: unique(warnings) };
}

export function buildAgentWorkspaceRequest(input: {
  readonly repoUrl: string;
  readonly branch?: string;
  readonly task: string;
  readonly executor?: AgentWorkspaceExecutor;
  readonly allowedPaths?: readonly string[];
  readonly forbiddenPaths?: readonly string[];
  readonly memoryHints?: readonly string[];
  readonly workspaceHost?: AgentWorkspaceHost;
}): AgentWorkspaceRequest {
  return {
    repoUrl: input.repoUrl.trim(),
    branch: input.branch?.trim() || 'main',
    task: input.task.trim(),
    executor: input.executor || 'openhands',
    allowedPaths: input.allowedPaths?.map((path) => path.trim()).filter(Boolean),
    forbiddenPaths: input.forbiddenPaths?.map((path) => path.trim()).filter(Boolean),
    memoryHints: input.memoryHints?.map((hint) => trimTo(sanitizeWorkspaceText(hint.trim()), 1000)).filter(Boolean),
    draftPrOnly: true,
    workspaceHost: input.workspaceHost || 'external-agent-runtime',
  };
}

export function normalizeAgentWorkspaceResult(value: Partial<AgentWorkspaceResult> & { workspaceId: string; status: AgentWorkspaceStatus }): AgentWorkspaceResult {
  const changedFiles = unique((value.changedFiles ?? [])
    .map((path) => normalizeWorkspacePath(path))
    .filter((path): path is string => Boolean(path)));

  return {
    workspaceId: sanitizeWorkspaceId(value.workspaceId),
    status: normalizeWorkspaceStatus(value.status),
    events: (value.events ?? []).map(sanitizeWorkspaceEvent).slice(-200),
    changedFiles,
    diffSummary: value.diffSummary ? trimTo(sanitizeWorkspaceText(value.diffSummary.trim()), 2000) : undefined,
    testSummary: value.testSummary ? trimTo(sanitizeWorkspaceText(value.testSummary.trim()), 2000) : undefined,
    draftPrUrl: value.draftPrUrl && /^https:\/\/github\.com\//i.test(value.draftPrUrl.trim()) ? value.draftPrUrl.trim() : undefined,
    blocker: value.blocker ? trimTo(sanitizeWorkspaceText(value.blocker.trim()), 1200) : undefined,
    workspaceInspectorUrl: value.workspaceInspectorUrl && /^https?:\/\//i.test(value.workspaceInspectorUrl.trim())
      ? sanitizeWorkspaceText(value.workspaceInspectorUrl.trim())
      : undefined,
    cleanedAt: Number.isFinite(value.cleanedAt) && value.cleanedAt && value.cleanedAt > 0 ? value.cleanedAt : undefined,
  };
}

function normalizeWorkspaceStatus(status: AgentWorkspaceStatus): AgentWorkspaceStatus {
  if (status === 'queued' || status === 'running' || status === 'completed' || status === 'failed' || status === 'blocked' || status === 'cleaned') {
    return status;
  }
  return 'blocked';
}

function normalizeEventLevel(level: AgentWorkspaceEventLevel): AgentWorkspaceEventLevel {
  if (level === 'info' || level === 'warning' || level === 'error') return level;
  return 'warning';
}

function sanitizeWorkspaceId(value: string): string {
  const clean = value.trim().replace(/[^\w.-]/g, '-').slice(0, 96);
  return clean || 'workspace-unknown';
}
