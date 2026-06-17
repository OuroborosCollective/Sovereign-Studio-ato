import {
  validateExternalMemorySyncConfig,
  type ExternalMemorySyncConfig,
  type ExternalMemorySyncStatus,
  type ExternalMemorySyncValidationReport,
} from './externalMemorySync';

export interface ExternalMemoryGatewayStats {
  totalRequests: number;
  blockedRequests: number;
  filteredRequests: number;
  passedRequests: number;
}

export interface ExternalMemoryGatewayMonitoring {
  service: string;
  version: string;
  uptime: number;
  memoryUsage: Record<string, number>;
  inboundStats: ExternalMemoryGatewayStats;
  milvusConnected: boolean;
}

export interface ExternalMemoryMonitoringResult {
  status: ExternalMemorySyncStatus;
  ok: boolean;
  monitoring?: ExternalMemoryGatewayMonitoring;
  validation: ExternalMemorySyncValidationReport;
  summary: string;
}

const SAFE_SERVICE = /^[a-z0-9._:-]{2,100}$/i;

function sanitizeText(value = ''): string {
  return value.trim().slice(0, 500);
}

function safeUrl(value: string): URL | null {
  try {
    return new URL(value.trim());
  } catch {
    return null;
  }
}

function buildGatewayEndpoint(config: ExternalMemorySyncConfig, path: string): string {
  const base = safeUrl(config.gatewayUrl);
  if (!base) throw new Error('Invalid gateway URL.');
  return new URL(path, base).toString();
}

function buildGatewayHeaders(config: ExternalMemorySyncConfig): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    ...(config.clientAccessKey ? { 'X-Sovereign-Gateway-Key': config.clientAccessKey } : {}),
  };
}

function numberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function normalizeStats(value: unknown): ExternalMemoryGatewayStats {
  const input = typeof value === 'object' && value ? value as Record<string, unknown> : {};
  return {
    totalRequests: numberValue(input.totalRequests),
    blockedRequests: numberValue(input.blockedRequests),
    filteredRequests: numberValue(input.filteredRequests),
    passedRequests: numberValue(input.passedRequests),
  };
}

function normalizeMemoryUsage(value: unknown): Record<string, number> {
  const input = typeof value === 'object' && value ? value as Record<string, unknown> : {};
  const output: Record<string, number> = {};
  for (const [key, raw] of Object.entries(input)) {
    if (typeof raw === 'number' && Number.isFinite(raw)) output[key] = raw;
  }
  return output;
}

export function validateExternalMemoryMonitoringPayload(payload: ExternalMemoryGatewayMonitoring): ExternalMemorySyncValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!SAFE_SERVICE.test(payload.service)) errors.push('Monitoring service id is invalid.');
  if (!payload.version.trim()) warnings.push('Monitoring version is empty.');
  if (!Number.isFinite(payload.uptime) || payload.uptime < 0) errors.push('Monitoring uptime must be finite and non-negative.');
  if (payload.inboundStats.totalRequests < 0) errors.push('totalRequests must not be negative.');
  if (payload.inboundStats.blockedRequests < 0) errors.push('blockedRequests must not be negative.');
  if (payload.inboundStats.filteredRequests < 0) errors.push('filteredRequests must not be negative.');
  if (payload.inboundStats.passedRequests < 0) errors.push('passedRequests must not be negative.');
  if (payload.inboundStats.passedRequests > payload.inboundStats.totalRequests) warnings.push('passedRequests is greater than totalRequests.');
  if (Object.keys(payload.memoryUsage).length === 0) warnings.push('Monitoring memoryUsage is empty.');

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in external memory monitoring payload.`,
  };
}

export function normalizeExternalMemoryMonitoringPayload(raw: unknown): ExternalMemoryGatewayMonitoring {
  const input = typeof raw === 'object' && raw ? raw as Record<string, unknown> : {};
  return {
    service: sanitizeText(String(input.service ?? 'unknown-service')),
    version: sanitizeText(String(input.version ?? 'unknown')),
    uptime: numberValue(input.uptime),
    memoryUsage: normalizeMemoryUsage(input.memoryUsage),
    inboundStats: normalizeStats(input.inboundStats),
    milvusConnected: Boolean(input.milvusConnected),
  };
}

export async function fetchExternalMemoryMonitoring(input: {
  config: ExternalMemorySyncConfig;
  fetcher?: typeof fetch;
}): Promise<ExternalMemoryMonitoringResult> {
  const configValidation = validateExternalMemorySyncConfig(input.config);
  if (!input.config.enabled) {
    return { status: 'disabled', ok: false, validation: configValidation, summary: 'External memory sync is disabled.' };
  }
  if (!configValidation.valid) {
    return { status: 'soft-failed', ok: false, validation: configValidation, summary: configValidation.summary };
  }

  try {
    const response = await (input.fetcher ?? fetch)(buildGatewayEndpoint(input.config, '/api/sovereign-memory/monitoring'), {
      headers: buildGatewayHeaders(input.config),
    });
    const body = await response.json().catch(() => ({}));
    const monitoring = normalizeExternalMemoryMonitoringPayload(body);
    const payloadValidation = validateExternalMemoryMonitoringPayload(monitoring);
    if (!response.ok || !payloadValidation.valid) {
      return {
        status: 'soft-failed',
        ok: false,
        monitoring,
        validation: payloadValidation.valid ? configValidation : payloadValidation,
        summary: response.ok ? payloadValidation.summary : `External memory monitoring returned ${response.status}.`,
      };
    }
    return {
      status: 'ready',
      ok: true,
      monitoring,
      validation: payloadValidation,
      summary: `Gateway ${monitoring.service} ${monitoring.version}: ${monitoring.inboundStats.totalRequests} request(s), Milvus ${monitoring.milvusConnected ? 'connected' : 'not connected'}.`,
    };
  } catch (error) {
    return {
      status: 'soft-failed',
      ok: false,
      validation: configValidation,
      summary: error instanceof Error ? sanitizeText(error.message) : 'External memory monitoring request failed.',
    };
  }
}
