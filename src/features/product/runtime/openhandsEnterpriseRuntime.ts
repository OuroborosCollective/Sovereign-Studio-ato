export type OpenHandsDeploymentMode = 'disabled' | 'sovereign-agent-backend' | 'external-agent-runtime';
export type OpenHandsJobStatus = 'idle' | 'queued' | 'provisioning' | 'running' | 'waiting-for-user' | 'validating' | 'blocked' | 'failed' | 'completed' | 'cleaned';
export type OpenHandsEventLevel = 'info' | 'warning' | 'error' | 'success';

/** OpenHands health status */
export type OpenHandsHealthStatus = 'healthy' | 'degraded' | 'unknown' | 'unavailable';

/** OpenHands runtime health report */
export interface OpenHandsHealthReport {
  status: OpenHandsHealthStatus;
  latencyMs: number | null;
  lastCheck: number | null;
  consecutiveFailures: number;
  lastError?: string;
  agentApiUrl: string;
  adminConsoleUrl: string;
}

/** Create initial OpenHands health report */
export function createOpenHandsHealthReport(config: OpenHandsEnterpriseConfig): OpenHandsHealthReport {
  return {
    status: config.ready ? 'unknown' : 'unavailable',
    latencyMs: null,
    lastCheck: null,
    consecutiveFailures: 0,
    agentApiUrl: config.agentApiUrl,
    adminConsoleUrl: config.adminConsoleUrl,
  };
}

export interface OpenHandsEnterpriseConfigInput {
  enabled?: boolean;
  agentApiUrl?: string;
  adminConsoleUrl?: string;
  deploymentMode?: OpenHandsDeploymentMode;
}

export interface OpenHandsEnterpriseConfig {
  enabled: boolean;
  deploymentMode: OpenHandsDeploymentMode;
  agentApiUrl: string;
  adminConsoleUrl: string;
  ready: boolean;
  reason: string;
}

export interface OpenHandsJobRequest {
  repoUrl: string;
  branch: string;
  mission: string;
  draftPrOnly: true;
  allowAutoMerge: false;
  runtimeTruthRequired: true;
  source: 'sovereign-studio';
  executor?: 'sovereign-local-runner';
  provisionWorkspace?: boolean;
  cloneRepo?: boolean;
}

export interface OpenHandsRuntimeEvent {
  at: number;
  level: OpenHandsEventLevel;
  stage: string;
  message: string;
}

export interface OpenHandsJobSnapshot {
  jobId?: string;
  openHandsId?: string;
  status: OpenHandsJobStatus;
  repoUrl?: string;
  branch?: string;
  draftPrUrl?: string;
  changedFiles: string[];
  events: OpenHandsRuntimeEvent[];
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

export function resolveOpenHandsEnterpriseConfig(input: OpenHandsEnterpriseConfigInput = {}): OpenHandsEnterpriseConfig {
  const sovereignAgentApiUrl = normalizeUrl(
    readWindowOverride('__SOVEREIGN_AGENT_API_URL__')
      || readBuildEnv('VITE_SOVEREIGN_AGENT_API_URL')
      || readBuildEnv('VITE_SOVEREIGN_BACKEND_URL')
      || '',
  );
  const legacyOpenHandsApiUrl = normalizeUrl(
    readWindowOverride('__SOVEREIGN_OPENHANDS_AGENT_API_URL__')
      || readBuildEnv('VITE_OPENHANDS_AGENT_API_URL')
      || '',
  );
  const agentApiUrl = normalizeUrl(
    input.agentApiUrl
      || sovereignAgentApiUrl
      || legacyOpenHandsApiUrl
      || '',
  );
  const adminConsoleUrl = normalizeUrl(
    input.adminConsoleUrl
      || readWindowOverride('__SOVEREIGN_OPENHANDS_ADMIN_CONSOLE_URL__')
      || readBuildEnv('VITE_OPENHANDS_ADMIN_CONSOLE_URL')
      || '',
  );
  const enabledEnv = readWindowOverride('__SOVEREIGN_OPENHANDS_ENABLED__') || readBuildEnv('VITE_OPENHANDS_ENABLED');
  const legacyEnabled = typeof input.enabled === 'boolean'
    ? input.enabled
    : enabledEnv === 'true';
  const deploymentMode: OpenHandsDeploymentMode = input.deploymentMode
    || (sovereignAgentApiUrl ? 'sovereign-agent-backend' : legacyEnabled ? 'external-agent-runtime' : 'disabled');
  const enabled = deploymentMode === 'sovereign-agent-backend' || legacyEnabled;
  const urlSafe = !agentApiUrl || isHttpsUrl(agentApiUrl) || isLocalUrl(agentApiUrl);
  const ready = enabled && deploymentMode !== 'disabled' && Boolean(agentApiUrl) && urlSafe;

  return {
    enabled,
    deploymentMode,
    agentApiUrl,
    adminConsoleUrl,
    ready,
    reason: ready
      ? deploymentMode === 'sovereign-agent-backend'
        ? 'Sovereign Agent Backend is configured as the primary internal runtime.'
        : 'OpenHands Enterprise agent runtime is configured as an external worker backend.'
      : enabled
        ? 'OpenHands Enterprise is enabled but the agent API URL is missing or unsafe. Use HTTPS outside localhost.'
        : 'OpenHands Enterprise is disabled. Sovereign will not call an agent backend.',
  };
}

export function buildOpenHandsJobRequest(input: { repoUrl: string; branch?: string; mission: string; deploymentMode?: OpenHandsDeploymentMode }): OpenHandsJobRequest {
  const repoUrl = input.repoUrl.trim();
  const mission = input.mission.trim();
  const branch = input.branch?.trim() || 'main';
  const deploymentMode = input.deploymentMode || resolveOpenHandsEnterpriseConfig().deploymentMode;

  if (!repoUrl) throw new Error('OpenHands job requires a repository URL.');
  if (!mission) throw new Error('OpenHands job requires a mission.');

  const base: OpenHandsJobRequest = {
    repoUrl,
    branch,
    mission,
    draftPrOnly: true,
    allowAutoMerge: false,
    runtimeTruthRequired: true,
    source: 'sovereign-studio',
  };

  if (deploymentMode === 'sovereign-agent-backend') {
    return {
      ...base,
      executor: 'sovereign-local-runner',
      provisionWorkspace: true,
      cloneRepo: true,
    };
  }

  return base;
}

export function createOpenHandsIdleSnapshot(): OpenHandsJobSnapshot {
  return {
    status: 'idle',
    changedFiles: [],
    events: [],
  };
}

export function summarizeOpenHandsJob(snapshot: OpenHandsJobSnapshot): string {
  if (snapshot.status === 'idle') return 'OpenHands wartet auf einen echten Agentenauftrag.';
  if (snapshot.status === 'queued') return 'OpenHands Auftrag ist in der Warteschlange.';
  if (snapshot.status === 'running') return `OpenHands arbeitet${snapshot.openHandsId ? ` mit echter Runtime-ID ${snapshot.openHandsId}` : ''}: ${snapshot.changedFiles.length} Datei(en) gemeldet.`;
  if (snapshot.status === 'waiting-for-user') return 'OpenHands wartet auf eine Nutzerentscheidung.';
  if (snapshot.status === 'blocked') return snapshot.lastError || 'OpenHands ist durch ein Gate blockiert.';
  if (snapshot.status === 'failed') return snapshot.lastError || 'OpenHands Auftrag ist fehlgeschlagen.';
  return snapshot.draftPrUrl
    ? `OpenHands hat einen Draft PR erstellt: ${snapshot.draftPrUrl}`
    : 'OpenHands meldet abgeschlossen, aber kein Draft PR ist belegt.';
}

export function isOpenHandsTerminalStatus(status: OpenHandsJobStatus): boolean {
  return status === 'blocked' || status === 'failed' || status === 'completed' || status === 'cleaned';
}

export function maskOpenHandsSensitiveText(value: string): string {
  return value
    .replace(/(licenseID:\s*)[^\s]+/gi, '$1[redacted]')
    .replace(/(Authorization:\s*)[^\n]+/gi, '$1[redacted]')
    .replace(/(registry-password\s+)[^\s]+/gi, '$1[redacted]')
    .replace(/(password[=:]\s*)[^\s]+/gi, '$1[redacted]')
    .replace(/(token[=:]\s*)[^\s]+/gi, '$1[redacted]');
}
