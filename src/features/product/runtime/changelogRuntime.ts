import { resolvePrimaryBridgeConfig } from '../llm/primaryBridgeConfig';

export interface ChangelogGenerationResult {
  readonly ok: boolean;
  readonly status: 'ready' | 'deterministic_fallback' | 'blocked_unavailable';
  readonly markdown: string;
  readonly commitCount: number;
  readonly source: string;
  readonly modelUsed?: string;
  readonly resolvedTransport?: string;
  readonly fallbackUsed?: boolean;
  readonly attemptedRouteCount?: number;
  readonly error?: string;
}

export async function fetchCommitsSince(jobId: string, maxCount = 30): Promise<ChangelogGenerationResult> {
  const base = resolvePrimaryBridgeConfig().backendBaseUrl;
  const response = await fetch(`${base}/api/user/agent/jobs/${encodeURIComponent(jobId)}/changelog`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ maxCount }),
  });
  const payload = await response.json() as Partial<ChangelogGenerationResult> & { error?: string };
  const status = payload.status === 'ready' || payload.status === 'deterministic_fallback'
    ? payload.status
    : 'blocked_unavailable';
  return {
    ok: response.ok && typeof payload.markdown === 'string' && payload.markdown.length > 0,
    status,
    markdown: typeof payload.markdown === 'string' ? payload.markdown : '',
    commitCount: typeof payload.commitCount === 'number' && Number.isFinite(payload.commitCount) ? payload.commitCount : 0,
    source: typeof payload.source === 'string' ? payload.source : 'none',
    modelUsed: payload.modelUsed,
    resolvedTransport: payload.resolvedTransport,
    fallbackUsed: payload.fallbackUsed,
    attemptedRouteCount: payload.attemptedRouteCount,
    error: payload.error || (response.ok ? undefined : `Changelog HTTP ${response.status}`),
  };
}

export const generateChangelog = fetchCommitsSince;
