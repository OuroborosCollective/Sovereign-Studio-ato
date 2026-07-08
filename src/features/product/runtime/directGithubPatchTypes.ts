/**
 * Direct GitHub Patch Runtime Types
 * 
 * Defines types for the Direct GitHub Patch route - a lightweight alternative
 * to OpenHands for small README/docs changes.
 * 
 * Security rules:
 * - Token is ephemeral in memory only (component ref), never persisted.
 * - Token is never logged, written to chat history, or stored in state.
 * - Token is cleared on validation failure, repo change, or reset.
 * - Only fetcher with auth headers used for API calls.
 * - Patch must be validated against content before any GitHub write.
 * - Only safe paths allowed (README.md, docs/*.md, etc.)
 * - File content must be loaded before patching.
 */

// ─────────────────────────────────────────────────────────────
// Repo Context
// ─────────────────────────────────────────────────────────────

export interface DirectPatchRepoContext {
  readonly owner: string;
  readonly name: string;
  readonly branch: string;
  readonly filePaths: readonly string[]; // Available file paths in repo
}

// ─────────────────────────────────────────────────────────────
// Capability Check
// ─────────────────────────────────────────────────────────────

export type DirectPatchBlocker =
  | 'repo_missing'           // No repo loaded
  | 'github_access_missing'  // GitHub token not validated
  | 'unsupported_intent'     // Not a simple README/docs intent
  | 'target_not_in_repo'     // Target file not found in repo snapshot
  | 'unsafe_target'          // Target path not in allowed list
  | 'content_load_failed';   // Could not load file content

export interface DirectGitHubPatchCapability {
  readonly available: boolean;
  readonly reason: string;
  readonly blocker?: DirectPatchBlocker;
}

// ─────────────────────────────────────────────────────────────
// Request
// ─────────────────────────────────────────────────────────────

export interface DirectGitHubPatchRequest {
  readonly repo: DirectPatchRepoContext;
  readonly targetPath: string;
  readonly instruction: string;
  readonly baseContent: string;
}

// ─────────────────────────────────────────────────────────────
// Result
// ─────────────────────────────────────────────────────────────

export type DirectPatchNextAction = 'preview_diff' | 'create_draft_pr';

export interface DirectGitHubPatchSuccess {
  readonly ok: true;
  readonly targetPath: string;
  readonly patchSummary: string;
  readonly nextAction: DirectPatchNextAction;
  readonly proposedContent: string;
  readonly baseContent: string;
  readonly instruction: string;
}

export interface DirectGitHubPatchFailure {
  readonly ok: false;
  readonly reason: string;
  readonly blocker: DirectPatchBlocker;
}

export type DirectGitHubPatchResult = DirectGitHubPatchSuccess | DirectGitHubPatchFailure;

// ─────────────────────────────────────────────────────────────
// Allowed Target Patterns (v1)
// ─────────────────────────────────────────────────────────────

// Supported file patterns for Direct GitHub Patch v1
const DIRECT_PATCH_ALLOWED_PATTERNS: readonly RegExp[] = [
  /^README\.md$/i,
  /^README\.[a-z]{2,3}\.md$/i, // README.de.md, README.en.md, etc.
  /^docs\/.+\.md$/i,
  /^doc\/.+\.md$/i,
  /^documentation\/.+\.md$/i,
];

// Forbidden file patterns - must go through Workspace/Executor
const DIRECT_PATCH_FORBIDDEN_PATTERNS: readonly RegExp[] = [
  /^src\//,
  /^android\//,
  /^ios\//,
  /^scripts\//,
  /^\.github\//,
  /^workflows?\//,
  /^\.github\//,
  /package\.json$/,
  /package-lock\.json$/,
  /\.lock$/,
  /\.ts$/,
  /\.tsx$/,
  /\.js$/,
  /\.jsx$/,
  /\.py$/,
  /\.java$/,
  /\.go$/,
  /\.rs$/,
  /\.toml$/,
  /\.yaml$/,
  /\.yml$/,
  /\.sh$/,
];

/**
 * Check if a file path is allowed for Direct GitHub Patch v1.
 * Only README and docs/*.md files are allowed.
 */
export function isDirectPatchAllowedPath(path: string): boolean {
  return DIRECT_PATCH_ALLOWED_PATTERNS.some((pattern) => pattern.test(path));
}

/**
 * Check if a file path is explicitly forbidden for Direct GitHub Patch.
 * These paths must go through Workspace/Executor.
 */
export function isDirectPatchForbiddenPath(path: string): boolean {
  return DIRECT_PATCH_FORBIDDEN_PATTERNS.some((pattern) => pattern.test(path));
}

/**
 * Get the type of blocker for a given path check.
 */
export function getDirectPatchPathBlocker(path: string): DirectPatchBlocker | null {
  if (isDirectPatchForbiddenPath(path)) {
    return 'unsafe_target';
  }
  if (!isDirectPatchAllowedPath(path)) {
    return 'unsupported_intent';
  }
  return null;
}
