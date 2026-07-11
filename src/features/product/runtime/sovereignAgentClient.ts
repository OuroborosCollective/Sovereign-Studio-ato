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

export interface SovereignAgentStartJobInput {
  repoUrl: string;
  branch?: string;
  mission: string;
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
  return stringValue(raw.error) || stringValue(raw.message) || stringValue(raw.details) || stringValue(raw.blocker) || stringValue(raw.lastError);
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
      init: { method: 'POST', headers: headers(), credentials: 'include', body: JSON.stringify(job) },
      fetcher: this.fetcher,
      now: this.now,
    });
    return { ...snapshot, repoUrl: snapshot.repoUrl ?? job.repoUrl, branch: snapshot.branch ?? job.branch };
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
