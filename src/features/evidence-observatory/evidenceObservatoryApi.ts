import type { ArenaLeaderboardEntry, AtlasResponse, SourceDependencyAnalysis } from './evidenceObservatoryModel';

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof payload?.error === 'string' ? payload.error : `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return payload as T;
}

export async function loadAtlas(filters: { asOf?: string; projectId?: string } = {}): Promise<AtlasResponse> {
  const params = new URLSearchParams();
  if (filters.asOf) params.set('asOf', filters.asOf);
  if (filters.projectId) params.set('projectId', filters.projectId);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return jsonFetch<AtlasResponse>(`/api/evidence-observatory/v1/atlas${suffix}`);
}

export async function submitCommunityEvidence(input: {
  projectId?: string;
  title?: string;
  claim: string;
  sourceUrl: string;
  note?: string;
}) {
  return jsonFetch<{ ok: boolean; candidate: { id: string; workflow_state: string }; truthPromotion: boolean }>(
    '/api/evidence-observatory/v1/submissions',
    { method: 'POST', body: JSON.stringify(input) },
  );
}

export async function analyzeSourceDependency(caseId: string, sourceId: string) {
  const params = new URLSearchParams({ sourceId });
  return jsonFetch<{ ok: boolean; analysis: SourceDependencyAnalysis }>(
    `/api/evidence-observatory/v1/cases/${encodeURIComponent(caseId)}/source-dependency?${params.toString()}`,
  );
}

export async function loadArenaRequest(caseId: string) {
  return jsonFetch<{
    ok: boolean;
    caseId: string;
    messages: Array<{ role: 'system' | 'user'; content: string }>;
    temperature: number;
    executionEndpoint: string;
  }>(`/api/evidence-observatory/v1/arena/cases/${encodeURIComponent(caseId)}/request`);
}

export async function loadLlmRoutes() {
  return jsonFetch<{ routes?: Array<Record<string, unknown>>; data?: Array<Record<string, unknown>> }>(
    '/api/llm/routes',
  );
}

export async function executeArenaRoute(input: {
  routeId: string;
  modelId: string;
  messages: Array<{ role: string; content: string }>;
}) {
  return jsonFetch<Record<string, unknown>>('/api/llm/chat', {
    method: 'POST',
    body: JSON.stringify({
      routeId: input.routeId,
      model: input.modelId,
      messages: input.messages,
      temperature: 0,
      stream: false,
    }),
  });
}

export function extractArenaExecution(response: Record<string, unknown>): {
  modelResponse: unknown;
  llmRequestId: string;
} {
  const choices = Array.isArray(response.choices) ? response.choices : [];
  const first = choices[0] as Record<string, unknown> | undefined;
  const message = first?.message as Record<string, unknown> | undefined;
  const modelResponse = message?.content;
  const billing = response.sovereignBilling as Record<string, unknown> | undefined;
  const llmRequestId = String(billing?.requestId || billing?.request_id || response.requestId || '');
  if (!modelResponse || !llmRequestId) throw new Error('arena_execution_evidence_missing');
  return { modelResponse, llmRequestId };
}

export async function scoreArenaRun(input: {
  caseId: string;
  routeId: string;
  modelId: string;
  modelResponse: unknown;
  llmRequestId: string;
}) {
  return jsonFetch<{ ok: boolean; runId: string; runSha256: string; metrics: Record<string, unknown> }>(
    '/api/evidence-observatory/v1/arena/score',
    { method: 'POST', body: JSON.stringify(input) },
  );
}

export async function loadArenaLeaderboard() {
  return jsonFetch<{ ok: boolean; entries: ArenaLeaderboardEntry[]; truthfulnessRanked: boolean }>(
    '/api/evidence-observatory/v1/arena/leaderboard',
  );
}
