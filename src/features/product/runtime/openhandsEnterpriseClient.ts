import {
  buildOpenHandsJobRequest,
  type OpenHandsEnterpriseConfig,
  type OpenHandsJobRequest,
  type OpenHandsJobSnapshot,
  type OpenHandsRuntimeEvent,
  resolveOpenHandsEnterpriseConfig,
} from './openhandsEnterpriseRuntime';

export interface OpenHandsEnterpriseClientOptions {
  config?: OpenHandsEnterpriseConfig;
  fetcher?: typeof fetch;
  now?: () => number;
}

export interface OpenHandsStartJobInput {
  repoUrl: string;
  branch?: string;
  mission: string;
}

interface RawOpenHandsJobResponse {
  jobId?: unknown;
  id?: unknown;
  openHandsId?: unknown;
  openhandsId?: unknown;
  ohConvId?: unknown;
  conversationId?: unknown;
  sessionId?: unknown;
  status?: unknown;
  repoUrl?: unknown;
  branch?: unknown;
  draftPrUrl?: unknown;
  prUrl?: unknown;
  pr_url?: unknown;
  changedFiles?: unknown;
  changed_files?: unknown;
  events?: unknown;
  lastError?: unknown;
  error?: unknown;
  message?: unknown;
  details?: unknown;
  blocker?: unknown;
  workspaceId?: unknown;
  workspace_id?: unknown;
  externalRef?: unknown;
  external_ref?: unknown;
}

function endpoint(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0).map((item) => item.trim());
}

function eventArray(value: unknown, now: () => number): OpenHandsRuntimeEvent[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isObject).map((item): OpenHandsRuntimeEvent => {
    const level = item.level === 'warning' || item.level === 'error' || item.level === 'success' ? item.level : 'info';
    return {
      at: typeof item.at === 'number' && Number.isFinite(item.at) ? item.at : now(),
      level,
      stage: stringValue(item.stage) || 'openhands',
      message: stringValue(item.message) || 'OpenHands runtime event.',
    };
  });
}

function normalizeStatus(value: unknown): OpenHandsJobSnapshot['status'] {
  if (
    value === 'queued'
    || value === 'provisioning'
    || value === 'running'
    || value === 'waiting-for-user'
    || value === 'validating'
    || value === 'blocked'
    || value === 'failed'
    || value === 'completed'
    || value === 'cleaned'
  ) return value;
  return 'idle';
}

function openHandsRuntimeId(raw: RawOpenHandsJobResponse): string | undefined {
  return stringValue(raw.openHandsId)
    || stringValue(raw.openhandsId)
    || stringValue(raw.ohConvId)
    || stringValue(raw.conversationId)
    || stringValue(raw.sessionId)
    || stringValue(raw.workspaceId)
    || stringValue(raw.workspace_id)
    || stringValue(raw.externalRef)
    || stringValue(raw.external_ref);
}

function backendErrorMessage(raw: RawOpenHandsJobResponse): string | undefined {
  return stringValue(raw.error)
    || stringValue(raw.message)
    || stringValue(raw.details)
    || stringValue(raw.blocker)
    || stringValue(raw.lastError);
}

function unwrapJobPayload(raw: Record<string, unknown>): RawOpenHandsJobResponse {
  const nested = raw.job;
  return isObject(nested) ? nested as RawOpenHandsJobResponse : raw as RawOpenHandsJobResponse;
}

function sanitizeSnapshot(rawInput: RawOpenHandsJobResponse, now: () => number): OpenHandsJobSnapshot {
  const raw = unwrapJobPayload(rawInput as Record<string, unknown>);
  return {
    jobId: stringValue(raw.jobId) || stringValue(raw.id),
    openHandsId: openHandsRuntimeId(raw),
    status: normalizeStatus(raw.status),
    repoUrl: stringValue(raw.repoUrl),
    branch: stringValue(raw.branch),
    draftPrUrl: stringValue(raw.draftPrUrl) || stringValue(raw.prUrl) || stringValue(raw.pr_url),
    changedFiles: stringArray(raw.changedFiles).concat(stringArray(raw.changed_files)),
    events: eventArray(raw.events, now),
    lastError: stringValue(raw.lastError) || backendErrorMessage(raw),
  };
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text.trim()) return {};
  return JSON.parse(text);
}

function assertReady(config: OpenHandsEnterpriseConfig): void {
  if (!config.ready) throw new Error(config.reason);
}

function jobPath(config: OpenHandsEnterpriseConfig, jobId?: string, suffix = ''): string {
  if (config.deploymentMode === 'sovereign-agent-backend') {
    const base = jobId
      ? `/api/user/agent/jobs/${encodeURIComponent(jobId.trim())}`
      : '/api/user/agent/jobs';
    return `${base}${suffix}`;
  }
  const base = jobId ? `/jobs/${encodeURIComponent(jobId.trim())}` : '/jobs';
  return `${base}${suffix}`;
}

function requestCredentials(config: OpenHandsEnterpriseConfig): RequestCredentials | undefined {
  return config.deploymentMode === 'sovereign-agent-backend' ? 'include' : undefined;
}

function headers(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
}

async function requestSnapshot(args: {
  url: string;
  init: RequestInit;
  fetcher: typeof fetch;
  now: () => number;
}): Promise<OpenHandsJobSnapshot> {
  const response = await args.fetcher(args.url, args.init);
  const body = await readJson(response);
  if (!response.ok) {
    const message = isObject(body) ? backendErrorMessage(body) : undefined;
    throw new Error(message || `OpenHands backend returned HTTP ${response.status}.`);
  }
  if (!isObject(body)) throw new Error('OpenHands backend returned a non-object response.');
  return sanitizeSnapshot(body, args.now);
}

export class OpenHandsEnterpriseClient {
  private readonly config: OpenHandsEnterpriseConfig;
  private readonly fetcher: typeof fetch;
  private readonly now: () => number;

  constructor(options: OpenHandsEnterpriseClientOptions = {}) {
    this.config = options.config ?? resolveOpenHandsEnterpriseConfig();
    this.fetcher = options.fetcher ?? fetch;
    this.now = options.now ?? Date.now;
  }

  getConfig(): OpenHandsEnterpriseConfig {
    return this.config;
  }

  buildJobRequest(input: OpenHandsStartJobInput): OpenHandsJobRequest {
    return buildOpenHandsJobRequest(input);
  }

  async startJob(input: OpenHandsStartJobInput): Promise<OpenHandsJobSnapshot> {
    assertReady(this.config);
    const job = this.buildJobRequest(input);
    return requestSnapshot({
      url: endpoint(this.config.agentApiUrl, jobPath(this.config)),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: requestCredentials(this.config),
        body: JSON.stringify(job),
      },
      fetcher: this.fetcher,
      now: this.now,
    });
  }

  async getJob(jobId: string): Promise<OpenHandsJobSnapshot> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('OpenHands job id is required.');
    return requestSnapshot({
      url: endpoint(this.config.agentApiUrl, jobPath(this.config, jobId)),
      init: {
        method: 'GET',
        headers: headers(),
        credentials: requestCredentials(this.config),
      },
      fetcher: this.fetcher,
      now: this.now,
    });
  }

  async cancelJob(jobId: string): Promise<OpenHandsJobSnapshot> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('OpenHands job id is required.');
    return requestSnapshot({
      url: endpoint(this.config.agentApiUrl, jobPath(this.config, jobId, '/cancel')),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: requestCredentials(this.config),
      },
      fetcher: this.fetcher,
      now: this.now,
    });
  }
}

export function createOpenHandsEnterpriseClient(options: OpenHandsEnterpriseClientOptions = {}): OpenHandsEnterpriseClient {
  return new OpenHandsEnterpriseClient(options);
}
