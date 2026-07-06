/**
 * Sovereign Workspace Scope Runtime
 *
 * Defines the allowed work area for code-capable executors. This runtime does
 * not start an executor. It produces truth about what an executor may touch.
 */

export type SovereignWorkspaceMaxAction = 'read_only' | 'patch_plan' | 'draft_pr';
export type SovereignWorkspaceScopeStatus = 'ready' | 'blocked';

export interface SovereignWorkspaceScopeInput {
  readonly repoFullName: string;
  readonly repoUrl?: string;
  readonly branch: string;
  readonly allowedPaths?: readonly string[];
  readonly forbiddenPaths?: readonly string[];
  readonly draftPrOnly: true;
  readonly githubWriteValidated: boolean;
  readonly maxAction: SovereignWorkspaceMaxAction;
  readonly maxRuntimeMs?: number;
  readonly maxChangedFiles?: number;
}

export interface SovereignWorkspaceScope {
  readonly repoFullName: string;
  readonly repoUrl: string;
  readonly branch: string;
  readonly allowedPaths: readonly string[];
  readonly forbiddenPaths: readonly string[];
  readonly draftPrOnly: true;
  readonly githubWriteValidated: boolean;
  readonly maxAction: SovereignWorkspaceMaxAction;
  readonly maxRuntimeMs: number;
  readonly maxChangedFiles: number;
}

export interface SovereignWorkspaceScopeValidation {
  readonly status: SovereignWorkspaceScopeStatus;
  readonly allowed: boolean;
  readonly blockers: readonly string[];
  readonly warnings: readonly string[];
}

const SAFE_REPO_FULL_NAME = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const SAFE_BRANCH = /^[\w./-]{1,160}$/;
const SAFE_RELATIVE_PATH = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))(?!.*\0)[\w .@/+~=-]+\/?$/;
const SECRET_PATTERNS: readonly RegExp[] = [
  /ghp_[A-Za-z0-9_]{20,}/,
  /github_pat_[A-Za-z0-9_]{20,}/,
  /sk-[A-Za-z0-9_-]{20,}/,
  /sk-proj-[A-Za-z0-9_-]{20,}/,
  /(?:token|password|secret|api[_-]?key)\s*[=:]/i,
];

const DEFAULT_FORBIDDEN_PATHS = [
  '.env',
  '.env.local',
  '.env.production',
  'node_modules/',
  'dist/',
  'build/',
  'android/app/release/',
  'android/app/build/',
] as const;

function unique(values: readonly string[]): string[] {
  return [...new Set(values)];
}

function hasSecretLikeValue(value: string): boolean {
  return SECRET_PATTERNS.some((pattern) => pattern.test(value));
}

export function normalizeSovereignWorkspacePath(path: string): string | null {
  const clean = path.trim().replace(/\\+/g, '/').replace(/^\.\//, '').replace(/\/+/g, '/');
  if (!clean || !SAFE_RELATIVE_PATH.test(clean)) return null;
  return clean;
}

function normalizePathList(paths: readonly string[] | undefined): { paths: string[]; unsafe: string[] } {
  const normalized: string[] = [];
  const unsafe: string[] = [];

  for (const path of paths ?? []) {
    const clean = normalizeSovereignWorkspacePath(path);
    if (clean) normalized.push(clean);
    else unsafe.push(path);
  }

  return { paths: unique(normalized), unsafe };
}

export function createSovereignWorkspaceScope(input: SovereignWorkspaceScopeInput): SovereignWorkspaceScope {
  const allowed = normalizePathList(input.allowedPaths);
  const forbidden = normalizePathList([...(input.forbiddenPaths ?? []), ...DEFAULT_FORBIDDEN_PATHS]);
  const repoFullName = input.repoFullName.trim();

  return {
    repoFullName,
    repoUrl: input.repoUrl?.trim() || `https://github.com/${repoFullName}`,
    branch: input.branch.trim() || 'main',
    allowedPaths: allowed.paths.length > 0 ? allowed.paths : ['src/', 'tests/', 'scripts/', 'README.md', 'docs/'],
    forbiddenPaths: forbidden.paths,
    draftPrOnly: true,
    githubWriteValidated: input.githubWriteValidated,
    maxAction: input.maxAction,
    maxRuntimeMs: input.maxRuntimeMs ?? 30 * 60 * 1000,
    maxChangedFiles: input.maxChangedFiles ?? 30,
  };
}

export function validateSovereignWorkspaceScope(scope: SovereignWorkspaceScope): SovereignWorkspaceScopeValidation {
  const blockers: string[] = [];
  const warnings: string[] = [];

  if (!SAFE_REPO_FULL_NAME.test(scope.repoFullName)) blockers.push('Workspace scope requires owner/repo repoFullName.');
  if (!scope.repoUrl.startsWith(`https://github.com/${scope.repoFullName}`)) blockers.push('Workspace scope repoUrl must match repoFullName.');
  if (!SAFE_BRANCH.test(scope.branch)) blockers.push('Workspace scope branch contains unsafe characters.');
  if (scope.draftPrOnly !== true) blockers.push('Workspace scope must be Draft-PR-only.');
  if (!scope.githubWriteValidated && scope.maxAction !== 'read_only') blockers.push('Write workspace requires validated GitHub write access.');
  if (scope.maxAction !== 'read_only' && scope.maxAction !== 'patch_plan' && scope.maxAction !== 'draft_pr') blockers.push('Workspace scope maxAction is unsupported.');
  if (!Number.isFinite(scope.maxRuntimeMs) || scope.maxRuntimeMs < 30_000) blockers.push('Workspace scope maxRuntimeMs must be at least 30000.');
  if (!Number.isFinite(scope.maxChangedFiles) || scope.maxChangedFiles < 1) blockers.push('Workspace scope maxChangedFiles must be at least 1.');

  const unsafeAllowed = normalizePathList(scope.allowedPaths).unsafe;
  const unsafeForbidden = normalizePathList(scope.forbiddenPaths).unsafe;
  if (unsafeAllowed.length > 0) blockers.push('Workspace scope allowedPaths contains unsafe paths.');
  if (unsafeForbidden.length > 0) blockers.push('Workspace scope forbiddenPaths contains unsafe paths.');

  const allStrings = [scope.repoFullName, scope.repoUrl, scope.branch, ...scope.allowedPaths, ...scope.forbiddenPaths];
  if (allStrings.some(hasSecretLikeValue)) blockers.push('Workspace scope contains secret-like text.');

  if (scope.maxAction === 'draft_pr' && !scope.githubWriteValidated) {
    blockers.push('Draft PR workspace requires validated GitHub write access.');
  }

  if (scope.allowedPaths.some((allowedPath) => scope.forbiddenPaths.includes(allowedPath))) {
    warnings.push('A path appears in both allowedPaths and forbiddenPaths; forbidden wins.');
  }

  return {
    status: blockers.length === 0 ? 'ready' : 'blocked',
    allowed: blockers.length === 0,
    blockers,
    warnings,
  };
}

function pathMatchesRule(path: string, rule: string): boolean {
  if (rule.endsWith('/')) return path === rule.slice(0, -1) || path.startsWith(rule);
  return path === rule || path.startsWith(`${rule}/`);
}

export function canWorkspaceTouchPath(scope: SovereignWorkspaceScope, candidatePath: string): {
  readonly allowed: boolean;
  readonly reason: string;
} {
  const path = normalizeSovereignWorkspacePath(candidatePath);
  if (!path) return { allowed: false, reason: 'Path is unsafe.' };

  if (scope.forbiddenPaths.some((rule) => pathMatchesRule(path, rule))) {
    return { allowed: false, reason: 'Path is forbidden by workspace scope.' };
  }

  if (scope.allowedPaths.some((rule) => pathMatchesRule(path, rule))) {
    return { allowed: true, reason: 'Path is allowed by workspace scope.' };
  }

  return { allowed: false, reason: 'Path is outside workspace scope.' };
}

export function summarizeSovereignWorkspaceScope(scope: SovereignWorkspaceScope): string {
  return [
    `Repo: ${scope.repoFullName}`,
    `Branch: ${scope.branch}`,
    `Max action: ${scope.maxAction}`,
    `Draft PR only: ${scope.draftPrOnly ? 'yes' : 'no'}`,
    `Allowed paths: ${scope.allowedPaths.join(', ')}`,
    `Forbidden paths: ${scope.forbiddenPaths.join(', ')}`,
  ].join('\n');
}
