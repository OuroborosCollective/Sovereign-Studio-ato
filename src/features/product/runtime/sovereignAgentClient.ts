import {
  buildSovereignAgentJobRequest,
  type SovereignAgentConfig,
  type SovereignAgentJobRequest,
  type SovereignAgentJobSnapshot,
  type SovereignAgentRuntimeEvent,
  resolveSovereignAgentConfig,
} from './sovereignAgentRuntime';

export interface SovereignAgentClientOptions {
  config?: SovereignAgentConfig;
  fetcher?: typeof fetch;
  now?: () => number;
}

export interface SovereignPatternLearningEvidence {
  candidateId?: string;
  candidateCreated: boolean;
  allowed: boolean;
  decision: string;
  vectorStored: boolean;
  vectorStorage?: string;
  vectorReason?: string;
}

export interface SovereignStagedFile {
  path: string;
  content: string;
  baseContent?: string;
}

export interface SovereignAgentStartJobInput {
  repoUrl: string;
  branch?: string;
  mission: string;
  provisionWorkspace?: boolean;
  cloneRepo?: boolean;
  stagedFiles?: SovereignStagedFile[];
  testCommand?: string;
  githubAccessToken?: string;
}

export interface SovereignToolchainStartJobInput extends SovereignAgentStartJobInput {
  evidenceText?: string;
}

export interface SovereignToolchainFailureFamily {
  code: string;
  title: string;
  severity: string;
  score: number;
  checks: string[];
}

export interface SovereignToolchainFollowup {
  fromFamily: string;
  prediction: string;
  checkNext: string;
}

export interface SovereignToolchainDiagnosis {
  evidenceHash?: string;
  failureFamilies: SovereignToolchainFailureFamily[];
  nextLogicalFailures: SovereignToolchainFollowup[];
}

export interface SovereignDraftPrPreparationResponse {
  ok: boolean;
  jobId: string;
  draftPrPreparation: {
    allowed: boolean;
    decision: string;
    summary?: string;
    headBranch?: string;
    baseBranch?: string;
    nextAction?: string;
    canCreateDraftPr?: boolean;
    blockers: string[];
  };
}

export interface SovereignDraftPrCreateResponse {
  ok: boolean;
  jobId: string;
  draftPrCreate: {
    allowed: boolean;
    status: string;
    prUrl?: string;
    blocker?: string;
    summary?: string;
  };
}

export interface SovereignDraftPrPreparationResponse {
  learningEvidence?: SovereignPatternLearningEvidence;
}

export interface SovereignToolchainStartJobInput extends SovereignAgentStartJobInput {
  evidenceText?: string;
  provisionWorkspace?: boolean;
  cloneRepo?: boolean;
}

export interface SovereignToolchainFailureFamily {
  code: string;
  title: string;
  severity: string;
  score: number;
  checks: string[];
}

export interface SovereignToolchainFollowup {
  fromFamily: string;
  prediction: string;
  checkNext: string;
}

export interface SovereignToolchainDiagnosis {
  evidenceHash?: string;
  failureFamilies: SovereignToolchainFailureFamily[];
  nextLogicalFailures: SovereignToolchainFollowup[];
}

export interface SovereignDraftPrPreparationResponse {
  ok: boolean;
  jobId: string;
  draftPrPreparation: {
    allowed: boolean;
    decision: string;
    summary?: string;
    headBranch?: string;
    baseBranch?: string;
    nextAction?: string;
    canCreateDraftPr?: boolean;
    blockers: string[];
  };
}

export interface SovereignDraftPrCreateResponse {
  ok: boolean;
  jobId: string;
  draftPrCreate: {
    allowed: boolean;
    status: string;
    prUrl?: string;
    blocker?: string;
    summary?: string;
  };
}

export interface SovereignJanitorFinding {
  id: string;
  ruleId: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | string;
  path: string;
  line: number;
  message: string;
  evidence: string;
  contentSha256: string;
  fixAvailable: boolean;
  suggestedSearchText?: string | null;
  suggestedReplacementText?: string | null;
}

export interface SovereignJanitorScanInput {
  mode?: 'scan';
  family?: string;
  paths?: string[];
  maxFindings?: number;
  maxFiles?: number;
  includeDocs?: boolean;
  explainWithLocalModel?: boolean;
}

export interface SovereignJanitorApplyInput {
  mode: 'apply';
  path: string;
  searchText: string;
  replacementText: string;
  expectedSha256: string;
  confirm: true;
}

export type SovereignJanitorInput = SovereignJanitorScanInput | SovereignJanitorApplyInput;

export interface SovereignJanitorToolResponse {
  ok: boolean;
  jobId: string;
  tool: {
    status: string;
    output?: string;
    blocker?: string;
    changedFiles: string[];
    diffSummary?: string;
    testSummary?: string;
    metadata: Record<string, unknown>;
    evidenceGate?: unknown;
  };
}

interface RawSovereignAgentJobResponse {
  jobId?: unknown;
  id?: unknown;
  runtimeId?: unknown;
  workspaceId?: unknown;
  status?: unknown;
  repoUrl?: unknown;
  branch?: unknown;
  draftPrUrl?: unknown;
  changedFiles?: unknown;
  events?: unknown;
  lastError?: unknown;
  error?: unknown;
  message?: unknown;
  details?: unknown;
  blocker?: unknown;
}

function endpoint(baseUrl: string, route: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/${route.replace(/^\/+/, '')}`;
}
function isObject(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null; }
function stringValue(value: unknown): string | undefined { return typeof value === 'string' && value.trim() ? value.trim() : undefined; }
function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0).map((item) => item.trim());
}
function eventArray(value: unknown, now: () => number): SovereignAgentRuntimeEvent[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isObject).map((item): SovereignAgentRuntimeEvent => ({
    at: typeof item.at === 'number' && Number.isFinite(item.at) ? item.at : now(),
    level: item.level === 'warning' || item.level === 'error' || item.level === 'success' ? item.level : 'info',
    stage: stringValue(item.stage) || 'sovereign-agent',
    message: stringValue(item.message) || 'Sovereign Agent runtime event.',
  }));
}
function normalizeStatus(value: unknown): SovereignAgentJobSnapshot['status'] {
  if (value === 'queued' || value === 'provisioning' || value === 'running' || value === 'waiting-for-user' || value === 'validating' || value === 'blocked' || value === 'failed' || value === 'completed' || value === 'cleaned') return value;
  return 'idle';
}
function backendErrorMessage(raw: RawSovereignAgentJobResponse): string | undefined {
  const value = raw as RawSovereignAgentJobResponse & Record<string, unknown>;
  const preparation = isObject(value.draftPrPreparation) ? value.draftPrPreparation : undefined;
  const creation = isObject(value.draftPrCreate) ? value.draftPrCreate : undefined;
  const preparationBlockers = preparation ? stringArray(preparation.blockers) : [];
  return stringValue(raw.error)
    || stringValue(raw.message)
    || stringValue(raw.details)
    || stringValue(raw.blocker)
    || stringValue(raw.lastError)
    || (preparationBlockers.length ? preparationBlockers.join('; ') : undefined)
    || (creation ? stringValue(creation.blocker) || stringValue(creation.summary) : undefined)
    || (preparation ? stringValue(preparation.summary) : undefined);
}
function unwrapJobPayload(raw: Record<string, unknown>): RawSovereignAgentJobResponse {
  return isObject(raw.job) ? raw.job as RawSovereignAgentJobResponse : raw as RawSovereignAgentJobResponse;
}
function sanitizeSnapshot(rawInput: RawSovereignAgentJobResponse, now: () => number): SovereignAgentJobSnapshot {
  const raw = unwrapJobPayload(rawInput as Record<string, unknown>);
  const workspaceId = stringValue(raw.workspaceId);
  return {
    jobId: stringValue(raw.jobId) || stringValue(raw.id),
    runtimeId: stringValue(raw.runtimeId) || workspaceId,
    workspaceId,
    status: normalizeStatus(raw.status),
    repoUrl: stringValue(raw.repoUrl),
    branch: stringValue(raw.branch),
    draftPrUrl: stringValue(raw.draftPrUrl),
    changedFiles: stringArray(raw.changedFiles),
    events: eventArray(raw.events, now),
    lastError: stringValue(raw.lastError) || backendErrorMessage(raw),
  };
}
async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text.trim()) return {};
  return JSON.parse(text);
}
function assertReady(config: SovereignAgentConfig): void { if (!config.ready) throw new Error(config.reason); }
function jobPath(jobId?: string, suffix = ''): string {
  const base = jobId ? `/api/user/agent/jobs/${encodeURIComponent(jobId.trim())}` : '/api/user/agent/jobs';
  return `${base}${suffix}`;
}
function headers(): HeadersInit { return { 'Content-Type': 'application/json', Accept: 'application/json' }; }
async function requestSnapshot(args: { url: string; init: RequestInit; fetcher: typeof fetch; now: () => number }): Promise<SovereignAgentJobSnapshot> {
  const response = await args.fetcher(args.url, args.init);
  const body = await readJson(response);
  if (!response.ok) {
    const message = isObject(body) ? backendErrorMessage(body) : undefined;
    throw new Error(message || `Sovereign Agent backend returned HTTP ${response.status}.`);
  }
  if (!isObject(body)) throw new Error('Sovereign Agent backend returned a non-object response.');
  return sanitizeSnapshot(body, args.now);
}

async function requestObject(args: { url: string; init: RequestInit; fetcher: typeof fetch; fallback: string }): Promise<Record<string, unknown>> {
  const response = await args.fetcher(args.url, args.init);
  const body = await readJson(response);
  if (!response.ok) {
    const message = isObject(body) ? backendErrorMessage(body) : undefined;
    throw new Error(message || `${args.fallback} returned HTTP ${response.status}.`);
  }
  if (!isObject(body)) throw new Error(`${args.fallback} returned a non-object response.`);
  return body;
}

function patternLearningEvidence(body: Record<string, unknown>): SovereignPatternLearningEvidence | undefined {
  const pattern = isObject(body.patternLearning) ? body.patternLearning : undefined;
  const vector = isObject(body.vectorMemory) ? body.vectorMemory : undefined;
  const candidateId = stringValue(body.candidateId);
  if (!pattern && !vector && !candidateId) return undefined;
  return {
    candidateId,
    candidateCreated: body.candidateCreated === true,
    allowed: pattern?.allowed === true,
    decision: stringValue(pattern?.decision) || 'blocked',
    vectorStored: vector?.stored === true,
    vectorStorage: stringValue(vector?.storage),
    vectorReason: stringValue(vector?.reason),
  };
}

function diagnosisValue(value: unknown): SovereignToolchainDiagnosis {
  const raw = isObject(value) ? value : {};
  const families = Array.isArray(raw.failureFamilies)
    ? raw.failureFamilies.filter(isObject).map((item): SovereignToolchainFailureFamily => ({
        code: stringValue(item.code) || 'unknown',
        title: stringValue(item.title) || 'Unknown failure family',
        severity: stringValue(item.severity) || 'unknown',
        score: typeof item.score === 'number' && Number.isFinite(item.score) ? item.score : 0,
        checks: stringArray(item.checks),
      }))
    : [];
  const followups = Array.isArray(raw.nextLogicalFailures)
    ? raw.nextLogicalFailures.filter(isObject).map((item): SovereignToolchainFollowup => ({
        fromFamily: stringValue(item.fromFamily) || 'runtime_state_neighbour',
        prediction: stringValue(item.prediction) || 'Unknown neighbouring runtime risk.',
        checkNext: stringValue(item.checkNext) || 'verify runtime evidence',
      }))
    : [];
  return {
    evidenceHash: stringValue(raw.evidenceHash),
    failureFamilies: families,
    nextLogicalFailures: followups,
  };
}

function toolchainEvents(diagnosis: SovereignToolchainDiagnosis, now: () => number): SovereignAgentRuntimeEvent[] {
  const familySummary = diagnosis.failureFamilies.length
    ? diagnosis.failureFamilies.map((item) => item.code).join(', ')
    : 'no known family matched';
  return [
    {
      at: now(),
      level: 'success',
      stage: 'toolchain_diagnosis_completed',
      message: `Universal Toolchain diagnosis: ${familySummary}.`,
    },
    ...diagnosis.nextLogicalFailures.slice(0, 4).map((item, index): SovereignAgentRuntimeEvent => ({
      at: now(),
      level: 'info',
      stage: 'toolchain_predictive_handoff',
      message: `${index + 1}. ${item.prediction} Next check: ${item.checkNext}`,
    })),
  ];
}

async function requestJanitorTool(args: { url: string; init: RequestInit; fetcher: typeof fetch }): Promise<SovereignJanitorToolResponse> {
  const response = await args.fetcher(args.url, args.init);
  const body = await readJson(response);
  if (!response.ok) {
    const message = isObject(body) ? backendErrorMessage(body) : undefined;
    throw new Error(message || `Sovereign Janitor returned HTTP ${response.status}.`);
  }
  if (!isObject(body) || !isObject(body.tool)) throw new Error('Sovereign Janitor returned an invalid response.');
  const tool = body.tool;
  return {
    ok: body.ok === true,
    jobId: stringValue(body.jobId) || '',
    tool: {
      status: stringValue(tool.status) || 'error',
      output: stringValue(tool.stdout) || stringValue(tool.output),
      blocker: stringValue(tool.blocker),
      changedFiles: stringArray(tool.changedFiles),
      diffSummary: stringValue(tool.diffSummary),
      testSummary: stringValue(tool.testSummary),
      metadata: isObject(tool.metadata) ? tool.metadata : {},
      evidenceGate: tool.evidenceGate,
    },
  };
}

export class SovereignAgentClient {
  private readonly config: SovereignAgentConfig;
  private readonly fetcher: typeof fetch;
  private readonly now: () => number;
  constructor(options: SovereignAgentClientOptions = {}) {
    this.config = options.config ?? resolveSovereignAgentConfig();
    this.fetcher = options.fetcher ?? fetch;
    this.now = options.now ?? Date.now;
  }
  getConfig(): SovereignAgentConfig { return this.config; }
  buildJobRequest(input: SovereignAgentStartJobInput): SovereignAgentJobRequest { return buildSovereignAgentJobRequest(input); }
  async startJob(input: SovereignAgentStartJobInput): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    const job = this.buildJobRequest(input);
    const snapshot = await requestSnapshot({
      url: endpoint(this.config.agentApiUrl, jobPath()),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify({
          ...job,
          provisionWorkspace: input.provisionWorkspace ?? true,
          cloneRepo: input.cloneRepo ?? true,
          ...(input.stagedFiles?.length ? { stagedFiles: input.stagedFiles } : {}),
          ...(input.testCommand?.trim() ? { testCommand: input.testCommand.trim() } : {}),
          ...(input.githubAccessToken?.trim() ? { githubAccessToken: input.githubAccessToken.trim() } : {}),
        }),
      },
      fetcher: this.fetcher,
      now: this.now,
    });
    return { ...snapshot, repoUrl: snapshot.repoUrl ?? job.repoUrl, branch: snapshot.branch ?? job.branch };
  }
  async startToolchainJob(input: SovereignToolchainStartJobInput): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    const job = this.buildJobRequest(input);
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, '/api/user/agent/toolchain/handoff'),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify({
          ...job,
          evidenceText: input.evidenceText || '',
          provisionWorkspace: input.provisionWorkspace ?? true,
          cloneRepo: input.cloneRepo ?? false,
          ...(input.stagedFiles?.length ? { stagedFiles: input.stagedFiles } : {}),
          ...(input.testCommand?.trim() ? { testCommand: input.testCommand.trim() } : {}),
          ...(input.githubAccessToken?.trim() ? { githubAccessToken: input.githubAccessToken.trim() } : {}),
        }),
      },
      fetcher: this.fetcher,
      fallback: 'Sovereign Universal Toolchain handoff',
    });
    const snapshot = sanitizeSnapshot(isObject(body.job) ? body.job : body, this.now);
    const diagnosis = diagnosisValue(body.toolchain);
    return {
      ...snapshot,
      repoUrl: snapshot.repoUrl ?? job.repoUrl,
      branch: snapshot.branch ?? job.branch,
      events: [...toolchainEvents(diagnosis, this.now), ...snapshot.events],
    };
  }
  async getJob(jobId: string): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    return requestSnapshot({ url: endpoint(this.config.agentApiUrl, jobPath(jobId)), init: { method: 'GET', headers: headers(), credentials: 'include' }, fetcher: this.fetcher, now: this.now });
  }
  async cancelJob(jobId: string): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    return requestSnapshot({ url: endpoint(this.config.agentApiUrl, jobPath(jobId, '/cancel')), init: { method: 'POST', headers: headers(), credentials: 'include' }, fetcher: this.fetcher, now: this.now });
  }
  async prepareDraftPr(jobId: string, headBranch?: string): Promise<SovereignDraftPrPreparationResponse> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, jobPath(jobId, '/draft-pr/prepare')),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify(headBranch ? { headBranch } : {}),
      },
      fetcher: this.fetcher,
      fallback: 'Sovereign Draft PR preparation',
    });
    const signal = isObject(body.draftPrPreparation) ? body.draftPrPreparation : {};
    return {
      ok: body.ok === true,
      jobId: stringValue(body.jobId) || jobId,
      draftPrPreparation: {
        allowed: signal.allowed === true,
        decision: stringValue(signal.decision) || 'blocked',
        summary: stringValue(signal.summary),
        headBranch: stringValue(signal.headBranch),
        baseBranch: stringValue(signal.baseBranch),
        nextAction: stringValue(signal.nextAction),
        canCreateDraftPr: signal.canCreateDraftPr === true,
        blockers: stringArray(signal.blockers),
      },
      learningEvidence: patternLearningEvidence(body),
    };
  }
  async createDraftPr(jobId: string, githubAccessToken?: string): Promise<SovereignDraftPrCreateResponse> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    const token = githubAccessToken?.trim();
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, jobPath(jobId, '/draft-pr/create')),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify(token ? { githubAccessToken: token } : {}),
      },
      fetcher: this.fetcher,
      fallback: 'Sovereign Draft PR create',
    });
    const signal = isObject(body.draftPrCreate) ? body.draftPrCreate : {};
    return {
      ok: body.ok === true,
      jobId: stringValue(body.jobId) || jobId,
      draftPrCreate: {
        allowed: signal.allowed === true,
        status: stringValue(signal.status) || 'blocked',
        prUrl: stringValue(signal.prUrl),
        blocker: stringValue(signal.blocker),
        summary: stringValue(signal.summary),
      },
    };
  }
  async runJanitor(jobId: string, input: SovereignJanitorInput = {}): Promise<SovereignJanitorToolResponse> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    return requestJanitorTool({
      url: endpoint(this.config.agentApiUrl, jobPath(jobId, '/tools/janitor')),
      init: { method: 'POST', headers: headers(), credentials: 'include', body: JSON.stringify(input) },
      fetcher: this.fetcher,
    });
  }
}
export function createSovereignAgentClient(options: SovereignAgentClientOptions = {}): SovereignAgentClient { return new SovereignAgentClient(options); }
