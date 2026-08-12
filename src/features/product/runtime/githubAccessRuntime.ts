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
  readonly jobId: string;
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
 * Validate GitHub PAT format as a cheap preflight only.
 * Runtime truth still comes from the real GitHub API validation below.
 */
export function validateGitHubTokenFormat(token: string): GitHubAccessValidationResult {
  const trimmed = token.trim();
  
  if (!trimmed) {
    return { isValid: false, maskedToken: '', error: 'Token ist leer.' };
  }

  const isFineGrainedPat = /^github_pat_[A-Za-z0-9_]{20,}$/.test(trimmed);
  const isPrefixedGitHubToken = /^gh[pousr]_[A-Za-z0-9_]{20,}$/.test(trimmed);
  const isLegacyClassicPat = /^[a-zA-Z0-9]{40,}$/.test(trimmed);
  
  if (!isFineGrainedPat && !isPrefixedGitHubToken && !isLegacyClassicPat) {
    return {
      isValid: false,
      maskedToken: maskGitHubToken(trimmed),
      error: 'Ungültiges Token-Format. Unterstützt werden github_pat_ Fine-Grained PATs, ghp_ Classic PATs sowie GitHub OAuth/App-Tokenformate.',
    };
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
 * Validate one ephemeral GitHub credential through the authenticated Sovereign
 * backend. This intentionally does not call api.github.com from the browser:
 * validation and the later clone/push/PR operation must share one runtime
 * boundary and one token-normalization contract.
 */
export async function validateGitHubTokenForRepo(
  token: string,
  target: GitHubAccessRepositoryTarget,
  fetcher: typeof fetch = fetch,
  backendBaseUrl = '',
): Promise<GitHubAccessApiValidationResult> {
  const format = validateGitHubTokenFormat(token);
  if (!format.isValid) return { ok: false, error: format.error };
  const jobId = target.jobId.trim();
  if (!jobId) return { ok: false, canWrite: false, error: 'Serverbestätigter Agent-Job fehlt für GitHub-Zugangsprüfung.' };

  const base = backendBaseUrl.replace(/\/+$/, '');
  try {
    const response = await fetcher(`${base}/api/user/agent/github-access/validate`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        jobId,
        githubAccessToken: token.trim(),
      }),
    });
    const payload = await safeReadJson(response);
    if (!response.ok) {
      return {
        ok: false,
        canWrite: false,
        error: response.status === 401
          ? 'Sovereign-Session ist nicht mehr bestätigt. Bitte erneut anmelden.'
          : `Sovereign GitHub-Zugangsprüfung fehlgeschlagen: HTTP ${response.status}`,
      };
    }
    if (!isObject(payload)) {
      return { ok: false, canWrite: false, error: 'Sovereign GitHub-Zugangsprüfung lieferte keine gültige Antwort.' };
    }
    return {
      ok: payload.ok === true && payload.canWrite === true,
      canWrite: payload.canWrite === true,
      error: typeof payload.error === 'string' && payload.error.trim() ? payload.error.trim() : undefined,
    };
  } catch {
    return { ok: false, canWrite: false, error: 'Sovereign GitHub-Zugangsprüfung ist momentan nicht erreichbar.' };
  }
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
