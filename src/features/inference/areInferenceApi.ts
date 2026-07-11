const API_BASE = (
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim()
  || 'https://sovereign-backend.arelorian.de'
).replace(/\/$/, '');

export type AreInferenceDecision = 'local' | 'online_required' | 'blocked';

export interface AreRepositoryFile {
  readonly path: string;
  readonly objectId: string;
}

export interface AreRepositoryState {
  readonly owner: string;
  readonly repo: string;
  readonly branch: string;
  readonly repositoryRevision: string;
  readonly files: readonly AreRepositoryFile[];
  readonly evidenceComplete: boolean;
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
    readonly repository?: string | null;
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
  const files = [...(repository?.files ?? [])]
    .map((entry) => ({
      path: entry.path.trim(),
      objectId: entry.objectId.trim().toLowerCase(),
    }))
    .filter((entry) => entry.path.length > 0)
    .sort((left, right) => left.path.localeCompare(right.path) || left.objectId.localeCompare(right.objectId));
  const repositoryRevision = repository?.repositoryRevision?.trim().toLowerCase() ?? '';
  const evidenceComplete = Boolean(
    repository?.evidenceComplete
    && repositoryRevision
    && files.every((entry) => entry.objectId.length > 0),
  );

  return {
    owner: repository?.owner?.trim() ?? '',
    repo: repository?.repo?.trim() ?? '',
    branch: repository?.branch?.trim() ?? '',
    repositoryRevision,
    files,
    evidenceComplete,
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
  readonly selected: number;
  readonly repaired: number;
  readonly remaining: number;
  readonly remainingForUser: number;
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

export interface AreQuarantineResult {
  readonly candidate: {
    readonly id: string;
    readonly status: string;
    readonly contentSha256: string;
  };
  readonly quarantined: boolean;
  readonly duplicate: boolean;
  readonly learningState: 'pending_evidence' | 'already_resolved';
  readonly promoted: boolean;
}

export async function quarantineAreResponse(input: QuarantineAreResponseInput): Promise<AreQuarantineResult> {
  const response = await fetch(`${API_BASE}/api/inference/are/quarantine`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  const payload = await readJson<AreQuarantineResult>(response);
  if (!response.ok) {
    throw new Error(payload.error || `ARE-Quarantäne HTTP ${response.status}`);
  }
  return payload as AreQuarantineResult;
}

export function buildAreRepositoryState(input: {
  readonly owner?: string;
  readonly repo?: string;
  readonly branch?: string;
  readonly repositoryRevision?: string;
  readonly files?: readonly { readonly path: string; readonly type?: string; readonly sha?: string }[];
}): AreRepositoryState {
  const files = (input.files ?? [])
    .filter((entry) => entry.type === undefined || entry.type === 'blob')
    .map((entry) => ({ path: entry.path, objectId: entry.sha ?? '' }));
  return normalizeRepository({
    owner: input.owner ?? '',
    repo: input.repo ?? '',
    branch: input.branch ?? '',
    repositoryRevision: input.repositoryRevision ?? '',
    files,
    evidenceComplete: Boolean(input.repositoryRevision && files.every((entry) => entry.objectId)),
  });
}
