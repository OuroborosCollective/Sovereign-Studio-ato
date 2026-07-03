/**
 * GitHub Access State Runtime
 * 
 * Manages GitHub PAT (Personal Access Token) state for draft PR operations.
 * States: missing | requested | validating | ready | invalid
 * 
 * Security rules (STRICT):
 * - Token NEVER stored in any state. Only maskedToken allowed.
 * - Token never in chat history, logs, telemetry, or repo
 * - Push/Draft PR blocked until ready state after REAL API validation
 * - Validating state means actual GitHub API call in progress
 */

export type GitHubAccessState = 'missing' | 'requested' | 'validating' | 'ready' | 'invalid';

export interface GitHubAccessSnapshot {
  state: GitHubAccessState;
  /** Masked token for display only. NEVER contains real token. */
  maskedToken: string | null;
  validatedAt: number | null;
  errorMessage: string | null;
}

export interface GitHubAccessRepositoryTarget {
  readonly owner: string;
  readonly repo: string;
}

export interface GitHubAccessApiValidationResult {
  readonly ok: boolean;
  readonly error?: string;
  readonly canWrite?: boolean;
}

/**
 * Mask a GitHub token for display (show first 4 and last 4 characters)
 * Input token is discarded immediately after masking.
 */
export function maskGitHubToken(token: string): string {
  if (token.length <= 8) return '****';
  const first = token.slice(0, 4);
  const last = token.slice(-4);
  return `${first}****${last}`;
}

/**
 * Validate GitHub PAT format (basic format check only).
 * Real validation requires actual GitHub API call.
 */
export function validateGitHubTokenFormat(token: string): GitHubAccessValidationResult {
  const trimmed = token.trim();
  
  if (!trimmed) {
    return { isValid: false, maskedToken: '', error: 'Token ist leer.' };
  }
  
  // GitHub PATs are typically 40+ characters (classic) or start with ghp_, gho_, ghu_, ghs_, ghr_
  const isClassicPat = /^[a-zA-Z0-9]{40,}$/.test(trimmed);
  const isFineGrained = /^gh[pousr]_[a-zA-Z0-9_]{36,}$/.test(trimmed);
  
  if (!isClassicPat && !isFineGrained) {
    return { isValid: false, maskedToken: maskGitHubToken(trimmed), error: 'Ungültiges Token-Format. GitHub PATs beginnen mit ghp_, gho_, ghu_, ghs_ oder ghr_.' };
  }
  
  return { isValid: true, maskedToken: maskGitHubToken(trimmed) };
}

export interface GitHubAccessValidationResult {
  isValid: boolean;
  maskedToken: string;
  error?: string;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function hasWritePermission(payload: unknown): boolean {
  if (!isObject(payload)) return false;
  const permissions = payload.permissions;
  if (!isObject(permissions)) return false;
  return permissions.push === true || permissions.admin === true || permissions.maintain === true;
}

async function safeReadJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * Validate a GitHub token against the real GitHub API without storing it.
 * The caller must pass the raw token only for this one-shot check and discard it immediately.
 */
export async function validateGitHubTokenForRepo(
  token: string,
  target: GitHubAccessRepositoryTarget,
  fetcher: typeof fetch = fetch,
): Promise<GitHubAccessApiValidationResult> {
  const format = validateGitHubTokenFormat(token);
  if (!format.isValid) return { ok: false, error: format.error };
  const owner = target.owner.trim();
  const repo = target.repo.trim();
  if (!owner || !repo) return { ok: false, error: 'Repo-Ziel fehlt für GitHub-Zugangsprüfung.' };

  const authHeaders: HeadersInit = {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${token.trim()}`,
    'X-GitHub-Api-Version': '2022-11-28',
  };

  const userResponse = await fetcher('https://api.github.com/user', { headers: authHeaders });
  if (!userResponse.ok) {
    return {
      ok: false,
      error: userResponse.status === 401
        ? 'GitHub-Token wurde abgelehnt.'
        : `GitHub-User-Prüfung fehlgeschlagen: HTTP ${userResponse.status}`,
    };
  }

  const repoResponse = await fetcher(
    `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`,
    { headers: authHeaders },
  );
  const repoPayload = await safeReadJson(repoResponse);
  if (!repoResponse.ok) {
    return {
      ok: false,
      error: repoResponse.status === 404
        ? 'GitHub-Token hat keinen Zugriff auf dieses Repository.'
        : `GitHub-Repo-Prüfung fehlgeschlagen: HTTP ${repoResponse.status}`,
    };
  }

  const canWrite = hasWritePermission(repoPayload);
  if (!canWrite) {
    return {
      ok: false,
      canWrite: false,
      error: 'GitHub-Token ist gültig, hat aber keinen Schreibzugriff auf dieses Repository.',
    };
  }

  return { ok: true, canWrite: true };
}

/**
 * Create initial GitHub access snapshot
 */
export function createGitHubAccessSnapshot(): GitHubAccessSnapshot {
  return {
    state: 'missing',
    maskedToken: null,
    validatedAt: null,
    errorMessage: null,
  };
}

/**
 * Transition to requested state
 */
export function requestGitHubAccess(maskedToken: string): GitHubAccessSnapshot {
  return {
    state: 'requested',
    maskedToken,
    validatedAt: null,
    errorMessage: null,
  };
}

/**
 * Transition to validating state.
 * Takes already-masked token - real token must not enter this runtime.
 */
export function startGitHubAccessValidation(maskedToken: string): GitHubAccessSnapshot {
  return {
    state: 'validating',
    maskedToken,
    validatedAt: null,
    errorMessage: null,
  };
}

/**
 * Transition to ready state after successful REAL GitHub API validation.
 * Takes already-masked token.
 */
export function completeGitHubAccessValidation(maskedToken: string): GitHubAccessSnapshot {
  return {
    state: 'ready',
    maskedToken,
    validatedAt: Date.now(),
    errorMessage: null,
  };
}

/**
 * Transition to invalid state after failed REAL GitHub API validation.
 * Takes already-masked token.
 */
export function failGitHubAccessValidation(maskedToken: string, error: string): GitHubAccessSnapshot {
  return {
    state: 'invalid',
    maskedToken,
    validatedAt: Date.now(),
    errorMessage: error,
  };
}

/**
 * Reset to missing state
 */
export function resetGitHubAccess(): GitHubAccessSnapshot {
  return createGitHubAccessSnapshot();
}

/**
 * Check if GitHub write actions are allowed
 */
export function canPerformGitHubWrite(snapshot: GitHubAccessSnapshot): boolean {
  return snapshot.state === 'ready';
}

/**
 * Check if GitHub access is in a terminal state that requires user action
 */
export function requiresUserAction(snapshot: GitHubAccessSnapshot): boolean {
  return snapshot.state === 'missing' || snapshot.state === 'invalid';
}

/**
 * Get human-readable status label
 */
export function getGitHubAccessLabel(snapshot: GitHubAccessSnapshot): string {
  switch (snapshot.state) {
    case 'missing': return 'GitHub-Zugang fehlt';
    case 'requested': return 'GitHub-Zugang wird angefordert';
    case 'validating': return 'GitHub-Zugang wird geprüft';
    case 'ready': return 'GitHub-Zugang bereit';
    case 'invalid': return 'GitHub-Zugang ungültig';
  }
}

/**
 * Get instruction text for missing/invalid state
 */
export function getGitHubAccessInstruction(snapshot: GitHubAccessSnapshot): string {
  if (snapshot.state === 'invalid') {
    return snapshot.errorMessage || 'Der eingegebene GitHub-Zugang ist ungültig.';
  }
  if (snapshot.state === 'requested') {
    return 'Format akzeptiert. Echte GitHub-API-Prüfung steht noch aus.';
  }
  return 'GitHub-Zugang benötigt für Draft PR. Bitte Zugang eingeben.';
}
