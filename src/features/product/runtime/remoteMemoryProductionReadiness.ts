import { validateExternalMemorySyncConfig, type ExternalMemorySyncConfig } from './externalMemorySync';

export interface RemoteMemoryProductionInput {
  config: ExternalMemorySyncConfig;
  allowedOrigins?: string[];
  rateLimitPerMinute?: number;
  maxBodyBytes?: number;
  maxResponseBytes?: number;
  gatewayHealthPath?: string;
}

export interface RemoteMemoryProductionReadinessReport {
  ready: boolean;
  blockers: string[];
  warnings: string[];
  summary: string;
}

const DEFAULT_MAX_BODY_BYTES = 256_000;
const DEFAULT_MAX_RESPONSE_BYTES = 512_000;
const SAFE_ORIGIN = /^https:\/\/[a-z0-9.-]+(?::\d+)?$/i;

function parseUrl(value: string): URL | null {
  try {
    return new URL(value.trim());
  } catch {
    return null;
  }
}

function isPrivateHost(hostname: string): boolean {
  return hostname === 'localhost'
    || hostname === '127.0.0.1'
    || hostname.startsWith('10.')
    || hostname.startsWith('192.168.')
    || /^172\.(1[6-9]|2\d|3[0-1])\./.test(hostname);
}

function hasDefaultIdentity(config: ExternalMemorySyncConfig): boolean {
  return config.contributorId === 'local-contributor'
    || config.contributorId === 'sovereign-local-install'
    || config.workspaceId === 'local-workspace';
}

export function validateRemoteMemoryProductionReadiness(input: RemoteMemoryProductionInput): RemoteMemoryProductionReadinessReport {
  const blockers: string[] = [];
  const warnings: string[] = [];
  const configReport = validateExternalMemorySyncConfig(input.config);
  const gatewayUrl = parseUrl(input.config.gatewayUrl);

  if (!input.config.enabled) blockers.push('Remote Memory must be enabled for production verification.');
  if (!input.config.consentAccepted) blockers.push('Consent must be accepted before production sync is enabled.');
  if (!configReport.valid) blockers.push(...configReport.errors);
  warnings.push(...configReport.warnings);

  if (!gatewayUrl) {
    blockers.push('Gateway URL must be a valid URL.');
  } else {
    if (gatewayUrl.protocol !== 'https:') blockers.push('Production gateway URL must use HTTPS.');
    if (isPrivateHost(gatewayUrl.hostname)) blockers.push('Production gateway URL must not point to localhost or a private LAN host.');
    if (gatewayUrl.port === '19530') blockers.push('Browser clients must not target the vector database port directly.');
  }

  const origins = input.allowedOrigins ?? [];
  if (!origins.length) blockers.push('At least one explicit HTTPS allowed origin is required.');
  for (const origin of origins) {
    if (!SAFE_ORIGIN.test(origin.trim())) blockers.push(`Allowed origin must be HTTPS and explicit: ${origin}`);
    if (origin.includes('*')) blockers.push(`Wildcard origins are not allowed: ${origin}`);
  }

  const rateLimit = input.rateLimitPerMinute ?? 0;
  if (!Number.isFinite(rateLimit) || rateLimit <= 0) blockers.push('A positive per-minute gateway rate limit is required.');
  if (rateLimit > 120) warnings.push('Rate limit is high for production client sync traffic.');

  const maxBodyBytes = input.maxBodyBytes ?? 0;
  if (!Number.isFinite(maxBodyBytes) || maxBodyBytes <= 0) blockers.push('A positive request body limit is required.');
  if (maxBodyBytes > DEFAULT_MAX_BODY_BYTES) warnings.push('Request body limit is higher than the recommended production default.');

  const maxResponseBytes = input.maxResponseBytes ?? 0;
  if (!Number.isFinite(maxResponseBytes) || maxResponseBytes <= 0) blockers.push('A positive response size limit is required.');
  if (maxResponseBytes > DEFAULT_MAX_RESPONSE_BYTES) warnings.push('Response size limit is higher than the recommended production default.');

  if (!input.gatewayHealthPath?.trim()) warnings.push('Gateway health path is not documented in the production checklist input.');
  if (hasDefaultIdentity(input.config)) warnings.push('Default workspace or contributor identity should be replaced before production sync.');

  return {
    ready: blockers.length === 0,
    blockers,
    warnings,
    summary: `${blockers.length} production blocker(s), ${warnings.length} warning(s).`,
  };
}

export function formatRemoteMemoryProductionChecklist(report: RemoteMemoryProductionReadinessReport): string {
  const lines = [report.summary];
  if (report.blockers.length) lines.push('Blockers:', ...report.blockers.map((item) => `- ${item}`));
  if (report.warnings.length) lines.push('Warnings:', ...report.warnings.map((item) => `- ${item}`));
  if (!report.blockers.length && !report.warnings.length) lines.push('Remote Memory production readiness passed.');
  return lines.join('\n');
}
