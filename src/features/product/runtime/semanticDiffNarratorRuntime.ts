import { resolvePrimaryBridgeConfig } from '../llm/primaryBridgeConfig';

export interface SemanticDiffNarrative {
  readonly path: string;
  readonly narration: string;
}

export interface SemanticDiffNarrationResult {
  readonly ok: boolean;
  readonly status: 'ready' | 'blocked_unavailable';
  readonly diffText: string;
  readonly narratives: readonly SemanticDiffNarrative[];
  readonly modelUsed?: string;
  readonly resolvedTransport?: string;
  readonly fallbackUsed?: boolean;
  readonly attemptedRouteCount?: number;
  readonly error?: string;
}

export async function requestSemanticDiffNarration(jobId: string): Promise<SemanticDiffNarrationResult> {
  const base = resolvePrimaryBridgeConfig().backendBaseUrl;
  const response = await fetch(`${base}/api/user/agent/jobs/${encodeURIComponent(jobId)}/diff-narration`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  const payload = await response.json() as Partial<SemanticDiffNarrationResult> & { error?: string };
  return {
    ok: response.ok && payload.status === 'ready',
    status: payload.status === 'ready' ? 'ready' : 'blocked_unavailable',
    diffText: typeof payload.diffText === 'string' ? payload.diffText : '',
    narratives: Array.isArray(payload.narratives)
      ? payload.narratives.filter((item): item is SemanticDiffNarrative => Boolean(item && typeof item.path === 'string' && typeof item.narration === 'string'))
      : [],
    modelUsed: payload.modelUsed,
    resolvedTransport: payload.resolvedTransport,
    fallbackUsed: payload.fallbackUsed,
    attemptedRouteCount: payload.attemptedRouteCount,
    error: payload.error || (response.ok ? undefined : `Diff narration HTTP ${response.status}`),
  };
}

export function narrativeMap(result: SemanticDiffNarrationResult | null): Readonly<Record<string, string>> {
  return Object.fromEntries((result?.narratives ?? []).map((item) => [item.path, item.narration]));
}
