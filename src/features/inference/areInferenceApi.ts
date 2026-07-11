const API_BASE = (
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim()
  || 'https://sovereign-backend.arelorian.de'
).replace(/\/$/, '');

export type AreInferenceDecision = 'local' | 'online_required' | 'blocked';

export interface AreChangedFile {
  readonly path: string;
  readonly sha256: string;
}

export interface AreRepositoryState {
  readonly owner: string;
  readonly repo: string;
  readonly branch: string;
  readonly repositoryHash: string;
  readonly changedFiles: readonly AreChangedFile[];
}

export interface AreStateEnvelope {
  readonly schemaVersion: number;
  readonly promptSha256: string;
  readonly repository: AreRepositoryState;
  readonly knowledgeRevision: string;
  readonly experienceRevision: string;
  readonly embeddingModelHash: string;
  readonly activeCapabilities: readonly string[];
  readonly onlineAvailable: boolean;
}

export interface AreKnowledgeResult {
  readonly blockId: string;
  readonly contentSha256?: string;
  readonly sourceId?: string;
  readonly sourceType?: string;
  readonly sourceTitle?: string;
  readonly sectionTitle?: string;
  readonly content?: string;
  readonly similarity: number;
}

export interface AreExperienceResult {
  readonly candidateId: string;
  readonly patternText?: string;
  readonly summary?: string;
  readonly similarity: number;
}

export interface AreInferenceResult {
  readonly ok: boolean;
  readonly schemaVersion: number;
  readonly stateHash: string;
  readonly state: AreStateEnvelope;
  readonly decision: AreInferenceDecision;
  readonly adapter: string;
  readonly confidence: number;
  readonly knowledgeConfidence: number;
  readonly experienceConfidence: number;
  readonly selectedKnowledgeIds: readonly string[];
  readonly selectedPatternIds: readonly string[];
  readonly knowledgeContext: string;
  readonly experienceContext: string;
  readonly knowledgeResults: readonly AreKnowledgeResult[];
  readonly experienceResults: readonly AreExperienceResult[];
  readonly reasons: readonly string[];
  readonly blockers: {
    readonly knowledge?: string | null;
    readonly experience?: string | null;
  };
  readonly deterministic: true;
}

export interface EvaluateAreInferenceInput {
  readonly prompt: string;
  readonly repository?: Partial<AreRepositoryState>;
  readonly activeCapabilities?: readonly string[];
  readonly onlineAvailable: boolean;
  readonly limit?: number;
}

export interface QuarantineAreResponseInput {
  readonly prompt: string;
  readonly response: string;
  readonly stateHash: string;
  readonly adapter: string;
  readonly modelId: string;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

function normalizeRepository(repository?: Partial<AreRepositoryState>): AreRepositoryState {
  const changedFiles = [...(repository?.changedFiles ?? [])]
    .map((entry) => ({
      path: entry.path.trim(),
      sha256: entry.sha256.trim().toLowerCase(),
    }))
    .filter((entry) => entry.path.length > 0)
    .sort((left, right) => left.path.localeCompare(right.path) || left.sha256.localeCompare(right.sha256));

  return {
    owner: repository?.owner?.trim() ?? '',
    repo: repository?.repo?.trim() ?? '',
    branch: repository?.branch?.trim() ?? '',
    repositoryHash: repository?.repositoryHash?.trim().toLowerCase() ?? '',
    changedFiles,
  };
}

export function normalizeAreInferenceInput(input: EvaluateAreInferenceInput): EvaluateAreInferenceInput & {
  readonly repository: AreRepositoryState;
  readonly activeCapabilities: readonly string[];
  readonly limit: number;
} {
  return {
    prompt: input.prompt.trim(),
    repository: normalizeRepository(input.repository),
    activeCapabilities: [...new Set(input.activeCapabilities ?? [])]
      .map((value) => value.trim())
      .filter(Boolean)
      .sort(),
    onlineAvailable: input.onlineAvailable,
    limit: Math.max(1, Math.min(Math.trunc(input.limit ?? 5), 8)),
  };
}

async function readJson<T>(response: Response): Promise<T & { error?: string; blocker?: string }> {
  return response.json().catch(() => ({})) as Promise<T & { error?: string; blocker?: string }>;
}

export async function evaluateAreInference(input: EvaluateAreInferenceInput): Promise<AreInferenceResult> {
  const normalized = normalizeAreInferenceInput(input);
  if (!normalized.prompt) throw new Error('ARE-Inferenz benötigt einen Auftrag.');

  const response = await fetch(`${API_BASE}/api/inference/are/evaluate`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(normalized),
  });
  const payload = await readJson<AreInferenceResult>(response);

  if (payload.decision === 'blocked' && payload.stateHash) {
    return payload as AreInferenceResult;
  }
  if (!response.ok) {
    throw new Error(payload.error || payload.blocker || `ARE-Inferenz HTTP ${response.status}`);
  }
  return payload as AreInferenceResult;
}

export interface AreKnowledgeRepairResult {
  readonly action: 'recompute_missing_knowledge_embeddings';
  readonly repaired: number;
  readonly remaining: number;
  readonly embeddingModel?: string;
  readonly provider?: string;
  readonly blockIds?: readonly string[];
}

export async function repairMissingKnowledgeEmbeddings(limit = 25): Promise<AreKnowledgeRepairResult> {
  const response = await fetch(`${API_BASE}/api/inference/are/repair`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'recompute_missing_knowledge_embeddings',
      limit: Math.max(1, Math.min(Math.trunc(limit), 25)),
    }),
  });
  const payload = await readJson<AreKnowledgeRepairResult>(response);
  if (!response.ok) {
    throw new Error(payload.error || payload.blocker || `ARE-Reparatur HTTP ${response.status}`);
  }
  return payload as AreKnowledgeRepairResult;
}

export async function quarantineAreResponse(input: QuarantineAreResponseInput): Promise<void> {
  const response = await fetch(`${API_BASE}/api/inference/are/quarantine`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const payload = await readJson<Record<string, never>>(response);
    throw new Error(payload.error || `ARE-Quarantäne HTTP ${response.status}`);
  }
}

export function buildAreRepositoryState(input: {
  readonly owner?: string;
  readonly repo?: string;
  readonly branch?: string;
  readonly repositoryHash?: string;
  readonly filePaths?: readonly string[];
}): AreRepositoryState {
  return normalizeRepository({
    owner: input.owner ?? '',
    repo: input.repo ?? '',
    branch: input.branch ?? '',
    repositoryHash: input.repositoryHash ?? '',
    changedFiles: (input.filePaths ?? []).map((path) => ({ path, sha256: '' })),
  });
}
