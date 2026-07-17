/**
 * GitHub Write Proxy Contract
 *
 * Frontend code may prepare a publish payload, but it must not own the GitHub write token.
 * Draft PR write operations belong behind a backend proxy route that keeps credentials in
 * server-side environment storage.
 */

export type GitHubWriteProxyOperation = 'create_blob' | 'create_tree' | 'create_commit' | 'create_ref' | 'update_ref' | 'create_draft_pr';

export interface GitHubWriteProxyConfig {
  readonly endpointUrl: string;
  readonly requiresServerToken: true;
  readonly allowedOperations: readonly GitHubWriteProxyOperation[];
  readonly maxFilesPerRequest: number;
  readonly maxFileBytes: number;
}

export interface GitHubWriteProxyPayloadFile {
  readonly path: string;
  readonly content: string;
}

export interface GitHubWriteProxyPayload {
  readonly repoUrl: string;
  readonly baseBranch?: string;
  readonly title: string;
  readonly body: string;
  readonly files: readonly GitHubWriteProxyPayloadFile[];
  readonly operation: GitHubWriteProxyOperation;
}

export interface GitHubWriteProxyValidationReport {
  readonly valid: boolean;
  readonly errors: readonly string[];
}

export const DEFAULT_GITHUB_WRITE_PROXY_CONFIG: GitHubWriteProxyConfig = {
  endpointUrl: '/api/toolchain/create-draft-pr',
  requiresServerToken: true,
  allowedOperations: ['create_blob', 'create_tree', 'create_commit', 'create_ref', 'update_ref', 'create_draft_pr'],
  maxFilesPerRequest: 30,
  maxFileBytes: 200_000,
};

const FORBIDDEN_PATHS = ['.env', '.env.local', '.env.production'];
const FORBIDDEN_PREFIXES = ['.git/', 'node_modules/', 'dist/', 'build/'];

function looksLikeSecret(value: string): boolean {
  const lower = value.toLowerCase();
  return lower.includes('authorization: bearer') || lower.includes('x-oauth-basic') || lower.includes('private_key') || lower.includes('access_token=');
}

export function validateGitHubWriteProxyConfig(config: GitHubWriteProxyConfig = DEFAULT_GITHUB_WRITE_PROXY_CONFIG): GitHubWriteProxyValidationReport {
  const errors: string[] = [];

  if (!config.requiresServerToken) errors.push('GitHub write proxy must require a server-side token.');
  if (!config.endpointUrl.trim()) errors.push('GitHub write proxy endpoint is required.');
  if (!config.endpointUrl.startsWith('/api/') && !config.endpointUrl.startsWith('https://')) errors.push('GitHub write proxy endpoint must be /api/* or HTTPS.');
  if (config.allowedOperations.length === 0) errors.push('GitHub write proxy must allow at least one explicit operation.');
  if (!config.allowedOperations.includes('create_draft_pr')) errors.push('GitHub write proxy must support create_draft_pr for the release path.');
  if (config.maxFilesPerRequest < 1 || config.maxFilesPerRequest > 100) errors.push('GitHub write proxy file limit must be between 1 and 100.');
  if (config.maxFileBytes < 1 || config.maxFileBytes > 1_000_000) errors.push('GitHub write proxy file size limit is outside the safe range.');

  return { valid: errors.length === 0, errors };
}

export function validateGitHubWriteProxyPayload(
  payload: GitHubWriteProxyPayload,
  config: GitHubWriteProxyConfig = DEFAULT_GITHUB_WRITE_PROXY_CONFIG,
): GitHubWriteProxyValidationReport {
  const errors: string[] = [];
  const configReport = validateGitHubWriteProxyConfig(config);
  errors.push(...configReport.errors);

  if (!/^https:\/\/github\.com\/[^/\s]+\/[^/\s]+/i.test(payload.repoUrl.trim())) errors.push('repoUrl must be a GitHub HTTPS repository URL.');
  if (!payload.title.trim()) errors.push('title is required.');
  if (!payload.body.trim()) errors.push('body is required.');
  if (!config.allowedOperations.includes(payload.operation)) errors.push(`Operation is not allowed: ${payload.operation}`);
  if (payload.files.length === 0) errors.push('At least one file is required.');
  if (payload.files.length > config.maxFilesPerRequest) errors.push(`Too many files: ${payload.files.length}`);

  const seen = new Set<string>();
  for (const file of payload.files) {
    const path = file.path.trim().replace(/^\/+/, '');
    const lower = path.toLowerCase();
    if (!path || path.includes('..')) errors.push(`Invalid file path: ${file.path}`);
    if (FORBIDDEN_PATHS.includes(lower) || FORBIDDEN_PREFIXES.some((prefix) => lower.startsWith(prefix))) errors.push(`Forbidden file path: ${path}`);
    if (seen.has(path)) errors.push(`Duplicate file path: ${path}`);
    if (!file.content.trim()) errors.push(`Empty file content: ${path}`);
    if (file.content.length > config.maxFileBytes) errors.push(`File too large: ${path}`);
    if (looksLikeSecret(file.content)) errors.push(`Secret-like content found in file content: ${path}`);
    seen.add(path);
  }

  return { valid: errors.length === 0, errors };
}

export function assertGitHubWriteProxyPayloadSafe(payload: GitHubWriteProxyPayload, config: GitHubWriteProxyConfig = DEFAULT_GITHUB_WRITE_PROXY_CONFIG): void {
  const report = validateGitHubWriteProxyPayload(payload, config);
  if (!report.valid) throw new Error(`GitHub write proxy payload rejected: ${report.errors.join(' | ')}`);
}
