export type SovereignAgentDeploymentMode = 'disabled' | 'sovereign-agent-backend';
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
