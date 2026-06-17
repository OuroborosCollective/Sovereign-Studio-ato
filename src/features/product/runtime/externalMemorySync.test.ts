import { describe, expect, it, vi } from 'vitest';
import {
  buildExternalMemoryConsentText,
  buildExternalMemorySyncPayload,
  createExternalMemorySyncConfig,
  syncExternalMemory,
  validateExternalMemorySyncConfig,
  validateExternalMemorySyncPayload,
} from './externalMemorySync';
import { applyScanFindings, collectRepoPathFindings, createScanFindingRegistry } from './scanFindingRegistry';

describe('externalMemorySync', () => {
  it('is disabled by default and requires explicit consent when enabled', () => {
    const config = createExternalMemorySyncConfig();
    expect(config.enabled).toBe(false);
    expect(validateExternalMemorySyncConfig(config).valid).toBe(true);
    expect(buildExternalMemoryConsentText()).toContain('disabled by default');

    const enabled = { ...config, enabled: true, gatewayUrl: 'https://memory.example.test', consentAccepted: false };
    const report = validateExternalMemorySyncConfig(enabled);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('Consent');
  });

  it('rejects direct database-style port usage and non-https remote gateways', () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'http://example.test:19530',
    };
    const report = validateExternalMemorySyncConfig(config);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('Gateway URL must use HTTPS');
    expect(report.errors.join(' ')).toContain('gateway instead');
  });

  it('builds summary-only payloads from active scan findings', () => {
    const findings = collectRepoPathFindings([
      { path: 'node_modules/pkg/index.js', type: 'blob', size: 10 },
      { path: 'README.md', type: 'blob', size: 10 },
    ], 1);
    const registry = applyScanFindings(createScanFindingRegistry(1), 'repo-path-scan', findings, 1, 2);
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'https://memory.example.test',
    };

    const payload = buildExternalMemorySyncPayload({ config, scanRegistry: registry, now: 3 });
    expect(payload.redaction).toBe('summary-only-no-source-files');
    expect(payload.retrievalProfile).toBe('hybrid-dense-sparse-graph');
    expect(payload.items.some((item) => item.kind === 'scan-finding')).toBe(true);
    expect(validateExternalMemorySyncPayload(payload).valid).toBe(true);
  });

  it('soft-fails invalid sync instead of throwing', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: false,
      gatewayUrl: 'https://memory.example.test',
    };
    const payload = buildExternalMemorySyncPayload({ config: { ...config, consentAccepted: true }, now: 1 });

    const result = await syncExternalMemory({ config, payload });
    expect(result.status).toBe('soft-failed');
    expect(result.accepted).toBe(false);
  });

  it('posts to the gateway endpoint when enabled and valid', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'https://memory.example.test/base',
      clientAccessKey: 'session-key',
    };
    const payload = buildExternalMemorySyncPayload({ config, now: 1 });
    const fetcher = vi.fn(async (_url: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => ({ accepted: true, imported: 1, exported: 2, rejected: 0, summary: 'done' }),
    }) as Response);

    const result = await syncExternalMemory({ config, payload, fetcher: fetcher as unknown as typeof fetch });
    expect(result.status).toBe('synced');
    expect(result.response?.imported).toBe(1);
    expect(String(fetcher.mock.calls[0][0])).toBe('https://memory.example.test/api/sovereign-memory/sync');
  });
});
