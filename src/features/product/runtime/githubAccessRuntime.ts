/**
 * GitHub Access State Runtime
 * 
 * Manages GitHub PAT (Personal Access Token) state for draft PR operations.
 * States: missing | requested | validating | ready | invalid
 * 
 * Security rules:
 * - Token never stored in chat history, logs, telemetry, or repo
 * - Only masked display
 * - Push/Draft PR blocked until ready state
 */

export type GitHubAccessState = 'missing' | 'requested' | 'validating' | 'ready' | 'invalid';

export interface GitHubAccessSnapshot {
  state: GitHubAccessState;
  maskedToken: string | null;
  validatedAt: number | null;
  errorMessage: string | null;
  lastValidatedToken: string | null;
}

export interface GitHubAccessValidationInput {
  token: string;
  repoUrl?: string;
}

export interface GitHubAccessValidationResult {
  isValid: boolean;
  maskedToken: string;
  error?: string;
}

/**
 * Mask a GitHub token for display (show first 4 and last 4 characters)
 */
export function maskGitHubToken(token: string): string {
  if (token.length <= 8) return '****';
  const first = token.slice(0, 4);
  const last = token.slice(-4);
  return `${first}****${last}`;
}

/**
 * Validate GitHub PAT format (basic validation)
 * Real validation happens on API call
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

/**
 * Create initial GitHub access snapshot
 */
export function createGitHubAccessSnapshot(): GitHubAccessSnapshot {
  return {
    state: 'missing',
    maskedToken: null,
    validatedAt: null,
    errorMessage: null,
    lastValidatedToken: null,
  };
}

/**
 * Transition to requested state
 */
export function requestGitHubAccess(): GitHubAccessSnapshot {
  return {
    state: 'requested',
    maskedToken: null,
    validatedAt: null,
    errorMessage: null,
    lastValidatedToken: null,
  };
}

/**
 * Transition to validating state
 */
export function startGitHubAccessValidation(token: string): GitHubAccessSnapshot {
  return {
    state: 'validating',
    maskedToken: maskGitHubToken(token),
    validatedAt: null,
    errorMessage: null,
    lastValidatedToken: token,
  };
}

/**
 * Transition to ready state after successful validation
 */
export function completeGitHubAccessValidation(token: string): GitHubAccessSnapshot {
  return {
    state: 'ready',
    maskedToken: maskGitHubToken(token),
    validatedAt: Date.now(),
    errorMessage: null,
    lastValidatedToken: token,
  };
}

/**
 * Transition to invalid state after failed validation
 */
export function failGitHubAccessValidation(token: string, error: string): GitHubAccessSnapshot {
  return {
    state: 'invalid',
    maskedToken: maskGitHubToken(token),
    validatedAt: Date.now(),
    errorMessage: error,
    lastValidatedToken: token,
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
  return 'GitHub-Zugang benötigt für Draft PR. Bitte TOKEN eingeben.';
}
