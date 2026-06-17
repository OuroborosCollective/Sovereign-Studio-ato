export interface GitHubAuthSession {
  token: string;
  hasToken: boolean;
  redactedToken: string;
}

export interface GitHubHeadersOptions {
  token?: string;
  json?: boolean;
  extra?: HeadersInit;
}

const GITHUB_ACCEPT = 'application/vnd.github+json';
const GITHUB_API_VERSION = '2022-11-28';

export function normalizeGitHubToken(token?: string | null): string {
  return (token ?? '').trim();
}

export function hasGitHubToken(token?: string | null): boolean {
  return normalizeGitHubToken(token).length > 0;
}

export function redactGitHubToken(token?: string | null): string {
  const normalized = normalizeGitHubToken(token);
  if (!normalized) return '<no-token>';
  if (normalized.length <= 8) return '<redacted-token>';
  return `${normalized.slice(0, 4)}…${normalized.slice(-4)}`;
}

export function createGitHubAuthSession(token?: string | null): GitHubAuthSession {
  const normalized = normalizeGitHubToken(token);
  return {
    token: normalized,
    hasToken: normalized.length > 0,
    redactedToken: redactGitHubToken(normalized),
  };
}

function normalizeExtraHeaders(extra?: HeadersInit): Record<string, string> {
  if (!extra) return {};
  if (extra instanceof Headers) {
    const out: Record<string, string> = {};
    extra.forEach((value, key) => {
      out[key] = value;
    });
    return out;
  }
  if (Array.isArray(extra)) {
    return Object.fromEntries(extra.map(([key, value]) => [key, value]));
  }
  return extra as Record<string, string>;
}

export function buildGitHubHeaders(options: GitHubHeadersOptions = {}): HeadersInit {
  const session = createGitHubAuthSession(options.token);
  return {
    Accept: GITHUB_ACCEPT,
    'X-GitHub-Api-Version': GITHUB_API_VERSION,
    ...(options.json ? { 'Content-Type': 'application/json' } : {}),
    ...(session.hasToken ? { Authorization: `Bearer ${session.token}` } : {}),
    ...normalizeExtraHeaders(options.extra),
  };
}

export function requireGitHubToken(token?: string | null, purpose = 'GitHub write operation'): string {
  const normalized = normalizeGitHubToken(token);
  if (!normalized) throw new Error(`${purpose} requires a GitHub token.`);
  return normalized;
}

export function stripTokenFromText(value: string, token?: string | null): string {
  const normalized = normalizeGitHubToken(token);
  if (!normalized) return value;
  return value.split(normalized).join(redactGitHubToken(normalized));
}
