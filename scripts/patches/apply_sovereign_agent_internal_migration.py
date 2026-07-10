#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def path(name: str) -> Path:
    return ROOT / name


def read(name: str) -> str:
    return path(name).read_text(encoding="utf-8")


def write(name: str, content: str) -> None:
    target = path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


def remove(name: str) -> None:
    target = path(name)
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def move(old: str, new: str) -> None:
    source = path(old)
    target = path(new)
    if not source.exists():
        return
    if target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)


def replace_exact(name: str, old: str, new: str, *, required: bool = True) -> None:
    content = read(name)
    count = content.count(old)
    if required and count != 1:
        raise RuntimeError(f"{name}: expected one exact anchor, found {count}: {old[:80]!r}")
    if count:
        write(name, content.replace(old, new, 1))


RUNTIME = r'''export type SovereignAgentDeploymentMode = 'disabled' | 'sovereign-agent-backend';
export type SovereignAgentJobStatus = 'idle' | 'queued' | 'provisioning' | 'running' | 'waiting-for-user' | 'validating' | 'blocked' | 'failed' | 'completed' | 'cleaned';
export type SovereignAgentEventLevel = 'info' | 'warning' | 'error' | 'success';
export type SovereignAgentHealthStatus = 'healthy' | 'degraded' | 'unknown' | 'unavailable';

export interface SovereignAgentHealthReport {
  status: SovereignAgentHealthStatus;
  latencyMs: number | null;
  lastCheck: number | null;
  consecutiveFailures: number;
  lastError?: string;
  agentApiUrl: string;
}

export interface SovereignAgentConfigInput {
  enabled?: boolean;
  agentApiUrl?: string;
  deploymentMode?: SovereignAgentDeploymentMode;
}

export interface SovereignAgentConfig {
  enabled: boolean;
  deploymentMode: SovereignAgentDeploymentMode;
  agentApiUrl: string;
  ready: boolean;
  reason: string;
}

export interface SovereignAgentJobRequest {
  repoUrl: string;
  branch: string;
  mission: string;
  draftPrOnly: true;
  allowAutoMerge: false;
  runtimeTruthRequired: true;
  source: 'sovereign-studio';
  executor: 'sovereign-local-runner';
  provisionWorkspace: true;
  cloneRepo: true;
}

export interface SovereignAgentRuntimeEvent {
  at: number;
  level: SovereignAgentEventLevel;
  stage: string;
  message: string;
}

export interface SovereignAgentJobSnapshot {
  jobId?: string;
  runtimeId?: string;
  workspaceId?: string;
  status: SovereignAgentJobStatus;
  repoUrl?: string;
  branch?: string;
  draftPrUrl?: string;
  changedFiles: string[];
  events: SovereignAgentRuntimeEvent[];
  lastError?: string;
}

type ImportMetaWithEnv = ImportMeta & { env?: Record<string, string | undefined> };

function readBuildEnv(name: string): string | undefined {
  try {
    const value = (import.meta as ImportMetaWithEnv).env?.[name]?.trim();
    return value && !value.startsWith('REPLACE_WITH_') ? value : undefined;
  } catch {
    return undefined;
  }
}

function readWindowOverride(name: string): string | undefined {
  if (typeof window === 'undefined') return undefined;
  const value = (window as unknown as Record<string, unknown>)[name];
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function normalizeUrl(value: string): string {
  return value.trim().replace(/\/+$/, '');
}

function isLocalUrl(value: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?($|\/)/i.test(value);
}

function isHttpsUrl(value: string): boolean {
  return /^https:\/\//i.test(value);
}

export function createSovereignAgentHealthReport(config: SovereignAgentConfig): SovereignAgentHealthReport {
  return {
    status: config.ready ? 'unknown' : 'unavailable',
    latencyMs: null,
    lastCheck: null,
    consecutiveFailures: 0,
    agentApiUrl: config.agentApiUrl,
  };
}

export function resolveSovereignAgentConfig(input: SovereignAgentConfigInput = {}): SovereignAgentConfig {
  const agentApiUrl = normalizeUrl(
    input.agentApiUrl
      || readWindowOverride('__SOVEREIGN_AGENT_API_URL__')
      || readBuildEnv('VITE_SOVEREIGN_AGENT_API_URL')
      || readBuildEnv('VITE_SOVEREIGN_BACKEND_URL')
      || '',
  );
  const enabled = typeof input.enabled === 'boolean' ? input.enabled : Boolean(agentApiUrl);
  const deploymentMode: SovereignAgentDeploymentMode = input.deploymentMode
    || (enabled && agentApiUrl ? 'sovereign-agent-backend' : 'disabled');
  const urlSafe = !agentApiUrl || isHttpsUrl(agentApiUrl) || isLocalUrl(agentApiUrl);
  const ready = enabled
    && deploymentMode === 'sovereign-agent-backend'
    && Boolean(agentApiUrl)
    && urlSafe;

  return {
    enabled,
    deploymentMode,
    agentApiUrl,
    ready,
    reason: ready
      ? 'Sovereign Agent Backend is configured as the internal runtime.'
      : enabled
        ? 'Sovereign Agent Backend is enabled but the API URL is missing or unsafe. Use HTTPS outside localhost.'
        : 'Sovereign Agent Backend is disabled.',
  };
}

export function buildSovereignAgentJobRequest(input: { repoUrl: string; branch?: string; mission: string }): SovereignAgentJobRequest {
  const repoUrl = input.repoUrl.trim();
  const mission = input.mission.trim();
  const branch = input.branch?.trim() || 'main';
  if (!repoUrl) throw new Error('Sovereign Agent job requires a repository URL.');
  if (!mission) throw new Error('Sovereign Agent job requires a mission.');
  return {
    repoUrl,
    branch,
    mission,
    draftPrOnly: true,
    allowAutoMerge: false,
    runtimeTruthRequired: true,
    source: 'sovereign-studio',
    executor: 'sovereign-local-runner',
    provisionWorkspace: true,
    cloneRepo: true,
  };
}

export function createSovereignAgentIdleSnapshot(): SovereignAgentJobSnapshot {
  return { status: 'idle', changedFiles: [], events: [] };
}

export function summarizeSovereignAgentJob(snapshot: SovereignAgentJobSnapshot): string {
  if (snapshot.status === 'idle') return 'Sovereign Agent wartet auf einen echten Agentenauftrag.';
  if (snapshot.status === 'queued') return 'Sovereign Agent Auftrag ist in der Warteschlange.';
  if (snapshot.status === 'provisioning') return 'Sovereign Agent provisioniert den Workspace.';
  if (snapshot.status === 'running') return `Sovereign Agent arbeitet${snapshot.runtimeId ? ` mit Runtime-ID ${snapshot.runtimeId}` : ''}: ${snapshot.changedFiles.length} Datei(en) gemeldet.`;
  if (snapshot.status === 'waiting-for-user') return 'Sovereign Agent wartet auf eine Nutzerentscheidung.';
  if (snapshot.status === 'validating') return 'Sovereign Agent validiert Ergebnis-Evidence.';
  if (snapshot.status === 'blocked') return snapshot.lastError || 'Sovereign Agent ist durch ein Gate blockiert.';
  if (snapshot.status === 'failed') return snapshot.lastError || 'Sovereign Agent Auftrag ist fehlgeschlagen.';
  if (snapshot.status === 'cleaned') return 'Sovereign Agent Workspace wurde bereinigt.';
  return snapshot.draftPrUrl
    ? `Sovereign Agent hat einen Draft PR erstellt: ${snapshot.draftPrUrl}`
    : 'Sovereign Agent meldet abgeschlossen, aber kein Draft PR ist belegt.';
}

export function isSovereignAgentTerminalStatus(status: SovereignAgentJobStatus): boolean {
  return status === 'blocked' || status === 'failed' || status === 'completed' || status === 'cleaned';
}

export function maskSovereignAgentSensitiveText(value: string): string {
  return value
    .replace(/(Authorization:\s*)[^\n]+/gi, '$1[redacted]')
    .replace(/(registry-password\s+)[^\s]+/gi, '$1[redacted]')
    .replace(/(password[=:]\s*)[^\s]+/gi, '$1[redacted]')
    .replace(/(token[=:]\s*)[^\s]+/gi, '$1[redacted]');
}
'''

CLIENT = r'''import {
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
}
export function createSovereignAgentClient(options: SovereignAgentClientOptions = {}): SovereignAgentClient { return new SovereignAgentClient(options); }
'''

RUNTIME_TEST = r'''import { describe, expect, it } from 'vitest';
import {
  buildSovereignAgentJobRequest,
  createSovereignAgentIdleSnapshot,
  isSovereignAgentTerminalStatus,
  resolveSovereignAgentConfig,
  summarizeSovereignAgentJob,
} from './sovereignAgentRuntime';

describe('sovereignAgentRuntime', () => {
  it('uses only the internal backend mode', () => {
    expect(resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'https://agent.example.test' })).toMatchObject({ ready: true, deploymentMode: 'sovereign-agent-backend' });
  });
  it('rejects unsafe non-local HTTP URLs', () => {
    expect(resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'http://agent.example.test' }).ready).toBe(false);
  });
  it('builds a sovereign-local-runner request', () => {
    expect(buildSovereignAgentJobRequest({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })).toMatchObject({ executor: 'sovereign-local-runner', draftPrOnly: true, allowAutoMerge: false, cloneRepo: true });
  });
  it('keeps completion without a Draft PR visibly unproven', () => {
    expect(summarizeSovereignAgentJob({ ...createSovereignAgentIdleSnapshot(), status: 'completed' })).toContain('kein Draft PR');
  });
  it('recognizes terminal states', () => {
    expect(isSovereignAgentTerminalStatus('completed')).toBe(true);
    expect(isSovereignAgentTerminalStatus('running')).toBe(false);
  });
});
'''

CLIENT_TEST = r'''import { describe, expect, it, vi } from 'vitest';
import { SovereignAgentClient } from './sovereignAgentClient';
import { resolveSovereignAgentConfig } from './sovereignAgentRuntime';

const config = resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'https://agent.example.test' });

describe('SovereignAgentClient', () => {
  it('starts jobs only through /api/user/agent/jobs', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ job: { id: 'job-1', workspaceId: 'ws-1', status: 'queued', changedFiles: [], events: [] } }), { status: 201 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch, now: () => 10 });
    const snapshot = await client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' });
    expect(fetcher).toHaveBeenCalledWith('https://agent.example.test/api/user/agent/jobs', expect.objectContaining({ method: 'POST', credentials: 'include' }));
    expect(snapshot).toMatchObject({ jobId: 'job-1', runtimeId: 'ws-1', workspaceId: 'ws-1' });
  });
  it('polls and cancels through the same internal route family', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ id: 'job-1', status: 'running', changedFiles: [], events: [] }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });
    await client.getJob('job-1');
    await client.cancelJob('job-1');
    expect(fetcher.mock.calls[0][0]).toBe('https://agent.example.test/api/user/agent/jobs/job-1');
    expect(fetcher.mock.calls[1][0]).toBe('https://agent.example.test/api/user/agent/jobs/job-1/cancel');
  });
  it('surfaces backend blockers without compatibility aliases', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ blocker: 'workspace unavailable' }), { status: 409 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });
    await expect(client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })).rejects.toThrow('workspace unavailable');
  });
});
'''

CONTRACT_TEST = r'''#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve(import.meta.dirname, '..');
const retired = ['open', 'hands'].join('');
const forbidden = new RegExp(`${retired}|VITE_${retired.toUpperCase()}|${retired.toUpperCase()}_API_URL|external-agent-runtime`, 'i');
const liveRoots = ['src', 'backend/agent_runtime', 'scripts/sovereign-backend/agent_runtime'];
function walk(entry) {
  const target = path.join(root, entry);
  if (!fs.existsSync(target)) return [];
  if (fs.statSync(target).isFile()) return [target];
  return fs.readdirSync(target, { withFileTypes: true }).flatMap((item) => walk(path.join(entry, item.name)));
}
function read(name) { return fs.readFileSync(path.join(root, name), 'utf8'); }

test('live product source contains no retired executor imports, env or routes', () => {
  const offenders = liveRoots.flatMap(walk)
    .filter((file) => /\.(?:ts|tsx|js|jsx|mjs|py)$/.test(file))
    .filter((file) => !file.endsWith('sovereign-agent-internal-live-path.test.mjs'))
    .filter((file) => forbidden.test(fs.readFileSync(file, 'utf8')));
  assert.deepEqual(offenders.map((file) => path.relative(root, file)), []);
});

test('frontend client is internal-route-only', () => {
  const client = read('src/features/product/runtime/sovereignAgentClient.ts');
  const runtime = read('src/features/product/runtime/sovereignAgentRuntime.ts');
  assert.match(client, /\/api\/user\/agent\/jobs/);
  assert.doesNotMatch(client, /['"`]\/jobs/);
  assert.match(runtime, /executor: 'sovereign-local-runner'/);
  assert.doesNotMatch(runtime, /external-agent-runtime/);
});

test('database and deploy path enforce the internal executor', () => {
  const migration = read('scripts/sovereign-backend/migrations/007_sovereign_agent_internal_executor_only.sql');
  assert.match(migration, /CHECK \(executor = 'sovereign-local-runner'\)/);
  const dockerfile = read('scripts/sovereign-backend/Dockerfile');
  assert.match(dockerfile, /COPY migrations/);
  const migrate = read('scripts/sovereign-backend/auto-migrate.sh');
  assert.match(migrate, /ON_ERROR_STOP=1/);
});

test('deployed runtime mirrors the canonical backend runtime', () => {
  const files = (base) => walk(base).filter((file) => file.endsWith('.py')).map((file) => path.relative(path.join(root, base), file)).sort();
  const canonical = files('backend/agent_runtime');
  const deployed = files('scripts/sovereign-backend/agent_runtime');
  assert.deepEqual(deployed, canonical);
  for (const relative of canonical) assert.equal(read(path.join('scripts/sovereign-backend/agent_runtime', relative)), read(path.join('backend/agent_runtime', relative)), relative);
});
'''

MAPPINGS = [
    ('createOpenHandsEnterpriseClient', 'createSovereignAgentClient'),
    ('OpenHandsEnterpriseClientOptions', 'SovereignAgentClientOptions'),
    ('OpenHandsEnterpriseClient', 'SovereignAgentClient'),
    ('OpenHandsEnterpriseConfigInput', 'SovereignAgentConfigInput'),
    ('OpenHandsEnterpriseConfig', 'SovereignAgentConfig'),
    ('resolveOpenHandsEnterpriseConfig', 'resolveSovereignAgentConfig'),
    ('createOpenHandsHealthReport', 'createSovereignAgentHealthReport'),
    ('OpenHandsHealthReport', 'SovereignAgentHealthReport'),
    ('OpenHandsHealthStatus', 'SovereignAgentHealthStatus'),
    ('OpenHandsDeploymentMode', 'SovereignAgentDeploymentMode'),
    ('OpenHandsStartJobInput', 'SovereignAgentStartJobInput'),
    ('OpenHandsJobRequest', 'SovereignAgentJobRequest'),
    ('OpenHandsJobSnapshot', 'SovereignAgentJobSnapshot'),
    ('OpenHandsJobStatus', 'SovereignAgentJobStatus'),
    ('OpenHandsRuntimeEvent', 'SovereignAgentRuntimeEvent'),
    ('OpenHandsEventLevel', 'SovereignAgentEventLevel'),
    ('buildOpenHandsJobRequest', 'buildSovereignAgentJobRequest'),
    ('createOpenHandsIdleSnapshot', 'createSovereignAgentIdleSnapshot'),
    ('summarizeOpenHandsJob', 'summarizeSovereignAgentJob'),
    ('isOpenHandsTerminalStatus', 'isSovereignAgentTerminalStatus'),
    ('maskOpenHandsSensitiveText', 'maskSovereignAgentSensitiveText'),
    ('FilteredOpenHandsEvent', 'FilteredSovereignAgentEvent'),
    ('OpenHandsPatternIntakeInput', 'SovereignAgentPatternIntakeInput'),
    ('OpenHandsResultGate', 'SovereignAgentResultGate'),
    ('OpenHandsResultType', 'SovereignAgentResultType'),
    ('buildOpenHandsJobScopeKey', 'buildSovereignAgentJobScopeKey'),
    ('buildPatternIntakeFromOpenHands', 'buildPatternIntakeFromSovereignAgent'),
    ('classifyOpenHandsResult', 'classifySovereignAgentResult'),
    ('filterOpenHandsEventsForUI', 'filterSovereignAgentEventsForUI'),
    ('gateOpenHandsResult', 'gateSovereignAgentResult'),
    ('isOpenHandsJobScopedToRepo', 'isSovereignAgentJobScopedToRepo'),
    ('selectRepoScopedOpenHandsJob', 'selectRepoScopedAgentJob'),
    ('shouldLearnFromOpenHands', 'shouldLearnFromSovereignAgent'),
    ('summarizeOpenHandsChatStatus', 'summarizeSovereignAgentChatStatus'),
    ('hasExplicitOpenHandsIntent', 'hasExplicitAgentIntent'),
    ('isDelegatedOpenHandsExecutionIntent', 'isDelegatedSovereignAgentExecutionIntent'),
    ('isOpenHandsExecutionIntent', 'isSovereignAgentExecutionIntent'),
    ('OPENHANDS_EXECUTION_TOKENS', 'SOVEREIGN_AGENT_EXECUTION_TOKENS'),
    ('OPENHANDS_TOKENS', 'SOVEREIGN_AGENT_TOKENS'),
    ('OpenHandsJobTruthCard', 'SovereignAgentJobTruthCard'),
    ('openHandsId', 'runtimeId'),
    ('openhandsId', 'runtimeId'),
    ('setOpenHandsJob', 'setAgentJob'),
    ('setOpenhandsJob', 'setAgentJob'),
    ('onStartOpenHands', 'onStartAgent'),
    ('onCancelOpenHands', 'onCancelAgent'),
    ('openhandsJobStatus', 'agentJobStatus'),
    ('openhandsIsRunning', 'agentIsRunning'),
    ('openhandsReady', 'agentReady'),
    ('openhandsConfig', 'agentConfig'),
    ('openhandsJob', 'agentJob'),
    ('openHandsStatus', 'agentStatus'),
    ('openhandsStatus', 'agentStatus'),
    ('openhandsRunning', 'agentRunning'),
    ('openhandsEnterpriseRuntime', 'sovereignAgentRuntime'),
    ('openhandsEnterpriseClient', 'sovereignAgentClient'),
    ('openhandsPatternGatewayBridge', 'sovereignAgentPatternGatewayBridge'),
    ('direct_patch_or_openhands', 'direct_patch_or_agent'),
    ('openhands_or_plan', 'agent_or_plan'),
    ('openhands_bridge', 'agent_runtime'),
    ('openhands_unavailable', 'agent_unavailable'),
    ('start_openhands', 'start_agent'),
]


def migrate_typescript() -> None:
    move('src/features/product/runtime/openhandsEnterpriseRuntime.test.ts', 'src/features/product/runtime/sovereignAgentRuntime.test.ts')
    move('src/features/product/runtime/openhandsEnterpriseClient.test.ts', 'src/features/product/runtime/sovereignAgentClient.test.ts')
    move('src/features/product/runtime/openhandsPatternGatewayBridge.ts', 'src/features/product/runtime/sovereignAgentPatternGatewayBridge.ts')
    move('src/features/product/runtime/openhandsPatternGatewayBridge.test.ts', 'src/features/product/runtime/sovereignAgentPatternGatewayBridge.test.ts')
    move('src/features/product/components/OpenHandsJobTruthCard.tsx', 'src/features/product/components/SovereignAgentJobTruthCard.tsx')
    move('src/features/product/components/OpenHandsJobTruthCard.test.tsx', 'src/features/product/components/SovereignAgentJobTruthCard.test.tsx')

    for source in path('src').rglob('*'):
        if not source.is_file() or source.suffix not in {'.ts', '.tsx', '.js', '.jsx', '.mjs'}:
            continue
        content = source.read_text(encoding='utf-8')
        for old, new in MAPPINGS:
            content = content.replace(old, new)
        content = re.sub(r'\bOpenHands(?=[A-Za-z0-9_])', 'SovereignAgent', content)
        content = re.sub(r'\bopenHands(?=[A-Z0-9_])', 'agent', content)
        content = re.sub(r'\bopenhands(?=[A-Z0-9_])', 'agent', content)
        content = re.sub(r'\bOPENHANDS(?=[A-Z0-9_])', 'SOVEREIGN_AGENT', content)
        content = content.replace('OpenHands', 'Sovereign Agent')
        content = content.replace('OPENHANDS', 'SOVEREIGN_AGENT')
        content = content.replace('openhands', 'sovereign-agent')
        for old, new in [
            ('capabilities.sovereign-agent', 'capabilities.agent'),
            ('registry.sovereign-agent', 'registry.agent'),
            ('input.capabilities.sovereign-agent', 'input.capabilities.agent'),
            ('readonly sovereign-agent:', 'readonly agent:'),
            ('const sovereign-agent =', 'const agent ='),
            ('if (sovereign-agent.canStart)', 'if (agent.canStart)'),
            ('sovereign-agent.canStart', 'agent.canStart'),
            ('    sovereign-agent,', '    agent,'),
            ('  sovereign-agent:', '  agent:'),
        ]:
            content = content.replace(old, new)
        source.write_text(content, encoding='utf-8')

    builder = read('src/features/product/containers/BuilderContainer.tsx')
    builder = re.sub(r'^import \{ SovereignAgentOperatorBriefingPanel \} from .*?;\n', '', builder, flags=re.M)
    builder = re.sub(r'\n\s*<SovereignAgentOperatorBriefingPanel\b[\s\S]*?\/>\n', '\n', builder)
    write('src/features/product/containers/BuilderContainer.tsx', builder)

    registry = read('src/features/launcher/launcherRegistry.ts')
    registry = '\n'.join(line for line in registry.splitlines() if 'sovereign-agentToolEntry' not in line and "./tools/sovereign-agent" not in line) + '\n'
    write('src/features/launcher/launcherRegistry.ts', registry)

    detector = read('src/features/product/runtime/workerIntentDetector.ts')
    detector = detector.replace("'sovereign-agent', 'draft pr'", "'sovereign agent', 'sovereign-agent', 'draft pr'")
    detector = detector.replace("'nicht sovereign-agent',\n  'ohne sovereign-agent',", "'nicht sovereign agent',\n  'nicht sovereign-agent',\n  'ohne sovereign agent',\n  'ohne sovereign-agent',")
    detector = detector.replace("export function isSovereignAgentExecutionIntent(text: string): boolean {\n  const lower = text.toLowerCase();\n  return SOVEREIGN_AGENT_EXECUTION_TOKENS.some((token) => lower.includes(token));\n}", "export function isSovereignAgentExecutionIntent(text: string): boolean {\n  const lower = text.toLowerCase();\n  if (ALTERNATIVE_WRITE_ROUTE_TOKENS.some((token) => lower.includes(token))) return false;\n  return SOVEREIGN_AGENT_EXECUTION_TOKENS.some((token) => lower.includes(token));\n}")
    write('src/features/product/runtime/workerIntentDetector.ts', detector)

    write('src/features/product/runtime/sovereignAgentRuntime.ts', RUNTIME)
    write('src/features/product/runtime/sovereignAgentClient.ts', CLIENT)
    write('src/features/product/runtime/sovereignAgentRuntime.test.ts', RUNTIME_TEST)
    write('src/features/product/runtime/sovereignAgentClient.test.ts', CLIENT_TEST)

    for old in [
        'src/features/product/runtime/openhandsEnterpriseRuntime.ts',
        'src/features/product/runtime/openhandsEnterpriseClient.ts',
        'src/features/product/runtime/openhandsWorkspaceAdapter.ts',
        'src/features/product/runtime/openhandsWorkspaceAdapter.test.ts',
        'src/features/product/runtime/openHandsOperatorBriefing.ts',
        'src/features/product/runtime/openHandsOperatorBriefing.test.ts',
        'src/features/product/components/OpenHandsOperatorBriefingPanel.tsx',
        'src/features/product/components/OpenHandsOperatorBriefingPanel.test.tsx',
        'src/features/launcher/tools/openhands',
    ]:
        remove(old)

    card_test = path('src/features/product/components/SovereignAgentJobTruthCard.test.tsx')
    if card_test.exists():
        content = card_test.read_text(encoding='utf-8').replace("    expect(screen.getByText('Sovereign Agent Job')).toBeDefined();\n    expect(screen.queryByText('Sovereign Agent Job')).toBeNull();\n", "    expect(screen.getByText('Sovereign Agent Job')).toBeDefined();\n")
        card_test.write_text(content, encoding='utf-8')


def remove_python_nodes(filename: str) -> None:
    source = read(filename)
    tree = ast.parse(source)
    spans: list[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorated = ' '.join(ast.get_source_segment(source, dec) or '' for dec in node.decorator_list)
            if 'openhands' in node.name.lower() or 'openhands' in decorated.lower():
                spans.append((min([node.lineno] + [d.lineno for d in node.decorator_list]), node.end_lineno or node.lineno))
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            segment = ast.get_source_segment(source, node) or ''
            if 'OPENHANDS_API_URL' in segment:
                spans.append((node.lineno, node.end_lineno or node.lineno))
    lines = source.splitlines()
    blocked = {line for start, end in spans for line in range(start, end + 1)}
    write(filename, '\n'.join(line for index, line in enumerate(lines, 1) if index not in blocked))


def migrate_backend() -> None:
    for filename in ['backend/app.py', 'scripts/sovereign-backend/app.py']:
        remove_python_nodes(filename)
        content = read(filename)
        content = content.replace('Serves OpenHands proxy routes + Admin API routes.', 'Serves the internal Sovereign Agent API and Admin API routes.')
        content = content.replace('# For non-OpenHands tools without URL, mark as unknown', '# Tools without a configured URL remain unknown')
        write(filename, content)

    for root in ['backend/agent_runtime', 'scripts/sovereign-backend/agent_runtime']:
        contracts = read(f'{root}/contracts.py')
        contracts = re.sub(r'AgentExecutor = Literal\[[\s\S]*?\]\n', 'AgentExecutor = Literal["sovereign-local-runner"]\n', contracts, count=1)
        contracts = re.sub(r'AGENT_EXECUTORS: tuple\[AgentExecutor, \.\.\.\] = \([\s\S]*?\)\n', 'AGENT_EXECUTORS: tuple[AgentExecutor, ...] = ("sovereign-local-runner",)\n', contracts, count=1)
        contracts = re.sub(r'\n\s*if request\.executor == ["\']openhands-compat-adapter["\']:[\s\S]*?\n(?=\s*return )', '\n', contracts)
        contracts = contracts.replace('OpenHands is allowed to be an executor adapter, but it is not the truth source.', 'The internal sovereign-local-runner is the only live executor and truth producer.')
        write(f'{root}/contracts.py', contracts)

        lifecycle = read(f'{root}/job_lifecycle.py')
        lifecycle = re.sub(r'return request\.executor if request\.executor in \([\s\S]*?\) else "sovereign-local-runner"', 'return "sovereign-local-runner"', lifecycle)
        write(f'{root}/job_lifecycle.py', lifecycle)

        init = read(f'{root}/__init__.py').replace('OpenHands may be one executor adapter, but the runtime truth is produced here.', 'The internal sovereign-local-runner produces runtime truth here.')
        write(f'{root}/__init__.py', init)

    creator = read('backend/agent_runtime/agent_tool_creator.py')
    creator = creator.replace("            return {\n                \"role\": \"assistant\",\n                \"content\": \"I will use the available tools to complete this task.\",\n                \"tool_calls\": [],\n            }", "            raise RuntimeError('Sovereign Agent LLM client is not configured.')")
    creator = creator.replace("            messages=state.messages,", "            messages=list(state.messages),")
    write('backend/agent_runtime/agent_tool_creator.py', creator)

    shutil.copytree(path('backend/agent_runtime'), path('scripts/sovereign-backend/agent_runtime'), dirs_exist_ok=True)

    migration003 = read('scripts/sovereign-backend/migrations/003_sovereign_agent_jobs.sql')
    migration003 = re.sub(r"executor IN \([\s\S]*?'external-code-agent'\s*\)", "executor = 'sovereign-local-runner'", migration003)
    write('scripts/sovereign-backend/migrations/003_sovereign_agent_jobs.sql', migration003)
    write('scripts/sovereign-backend/migrations/007_sovereign_agent_internal_executor_only.sql', """-- Sovereign Agent Runtime: retire all legacy/external executor identities.
BEGIN;
UPDATE sovereign_agent_jobs
SET status = CASE WHEN status IN ('completed','failed','blocked','cleaned') THEN status ELSE 'blocked' END,
    blocker = CASE WHEN status IN ('completed','failed','blocked','cleaned') THEN blocker ELSE COALESCE(blocker, 'Legacy executor retired; resubmit through sovereign-local-runner.') END,
    executor = 'sovereign-local-runner',
    updated_at = NOW()
WHERE executor <> 'sovereign-local-runner';
ALTER TABLE sovereign_agent_jobs DROP CONSTRAINT IF EXISTS sovereign_agent_jobs_executor_check;
ALTER TABLE sovereign_agent_jobs ADD CONSTRAINT sovereign_agent_jobs_executor_check CHECK (executor = 'sovereign-local-runner');
COMMIT;
""")

    dockerfile = read('scripts/sovereign-backend/Dockerfile')
    if 'COPY migrations' not in dockerfile:
        anchor = 'COPY agent_runtime ./agent_runtime\n'
        if anchor not in dockerfile:
            raise RuntimeError('Dockerfile agent_runtime anchor missing')
        dockerfile = dockerfile.replace(anchor, anchor + 'COPY migrations ./migrations\n')
    write('scripts/sovereign-backend/Dockerfile', dockerfile)

    write('scripts/sovereign-backend/auto-migrate.sh', """#!/usr/bin/env bash
set -euo pipefail
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
for migration in /app/migrations/*.sql; do
  [ -f "$migration" ] || continue
  echo "Applying migration: $(basename "$migration")"
  psql -v ON_ERROR_STOP=1 \
    -h "${POSTGRES_HOST:-db}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER:-postgres}" \
    -d "${POSTGRES_DB:-postgres}" \
    -f "$migration"
done
""")

    workflow = read('.github/workflows/sovereign-agent-backend.yml')
    workflow = workflow.replace("          tar -czf sovereign-backend.tar.gz \\\n            scripts/sovereign-backend/agent_runtime \\\n            scripts/sovereign-backend/app.py", "          tar -czf sovereign-backend.tar.gz scripts/sovereign-backend")
    workflow = workflow.replace("            docker cp /tmp/scripts/sovereign-backend/agent_runtime sovereign-backend:/app/\n            docker cp /tmp/scripts/sovereign-backend/app.py sovereign-backend:/app/\n            docker start sovereign-backend", "            cd /tmp/scripts/sovereign-backend\n            docker build -t sovereign-backend:latest .\n            docker rm sovereign-backend 2>/dev/null || true\n            docker run -d --name sovereign-backend --restart unless-stopped --env-file /opt/sovereign-backend/.env -p 127.0.0.1:8788:8788 sovereign-backend:latest")
    write('.github/workflows/sovereign-agent-backend.yml', workflow)


def migrate_docs() -> None:
    for filename in [
        '.agents/memory/sovereign-execution-routing.md',
        '.agents/memory/sovereign-workbench-status.md',
        '.agents/skills/sovereign-studio-agent/SKILL.md',
        'docs/SOVEREIGN_RUNTIME.md',
        'docs/SOVEREIGN_CAPABILITY_ROUTING.md',
        'docs/SOVEREIGN_PRODUCT_TRUTH.md',
    ]:
        target = path(filename)
        if not target.exists():
            continue
        content = target.read_text(encoding='utf-8')
        content = content.replace('OpenHands', 'Sovereign Agent').replace('openhands', 'sovereign-agent').replace('OPENHANDS', 'SOVEREIGN_AGENT')
        content = content.replace('external-agent-runtime', 'sovereign-agent-backend')
        target.write_text(content, encoding='utf-8')


def main() -> None:
    migrate_typescript()
    migrate_backend()
    migrate_docs()
    write('scripts/sovereign-agent-internal-live-path.test.mjs', CONTRACT_TEST)
    print('SOVEREIGN_AGENT_INTERNAL_MIGRATION=APPLIED')


if __name__ == '__main__':
    main()
