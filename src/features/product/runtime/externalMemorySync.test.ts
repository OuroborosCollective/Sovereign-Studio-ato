import { describe, expect, it, vi } from 'vitest';
import {
  EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT,
  buildExternalMemoryConsentText,
  buildExternalMemoryDeleteRequest,
  buildExternalMemorySyncPayload,
  checkExternalMemoryHealth,
  createExternalMemorySyncConfig,
  deleteExternalMemoryData,
  pullExternalMemoryUpdates,
  searchExternalMemory,
  syncExternalMemory,
  validateExternalMemoryDeleteRequest,
  validateExternalMemorySyncConfig,
  validateExternalMemorySyncPayload,
} from './externalMemorySync';
import { applyScanFindings, collectRepoPathFindings, createScanFindingRegistry } from './scanFindingRegistry';

describe('externalMemorySync', () => {
  it('is disabled by default and requires explicit consent when enabled', () => {
    const config = createExternalMemorySyncConfig();
    expect(config.enabled).toBe(false);
    expect(config.contributorId).toBe('local-contributor');
    expect(validateExternalMemorySyncConfig(config).valid).toBe(true);
    expect(buildExternalMemoryConsentText()).toContain('disabled by default');

    const enabled = { ...config, enabled: true, gatewayUrl: 'https://memory.example.test', consentAccepted: false };
    const report = validateExternalMemorySyncConfig(enabled);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('Consent');
  });

  it('rejects direct database-style port usage and non-https remote gateways unless self-hosted test mode is explicit', () => {
    const blocked = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'http://example.test:19530',
    };
    const blockedReport = validateExternalMemorySyncConfig(blocked);
    expect(blockedReport.valid).toBe(false);
    expect(blockedReport.errors.join(' ')).toContain('Gateway URL must use HTTPS');
    expect(blockedReport.errors.join(' ')).toContain('gateway instead');

    const allowed = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'http://46.202.154.25:8088',
      allowSelfHostedHttp: true,
    };
    const allowedReport = validateExternalMemorySyncConfig(allowed);
    expect(allowedReport.valid).toBe(true);
    expect(allowedReport.warnings.join(' ')).toContain('Self-hosted HTTP');
  });

  it('builds summary-only contributor-scoped payloads from active scan findings', () => {
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
      contributorId: 'install-abc',
    };

    const payload = buildExternalMemorySyncPayload({ config, scanRegistry: registry, now: 3 });
    expect(payload.redaction).toBe('summary-only-no-source-files');
    expect(payload.retrievalProfile).toBe('hybrid-dense-sparse-graph');
    expect(payload.contributorId).toBe('install-abc');
    expect(payload.contributionScope).toBe('user-submitted-summary');
    expect(payload.items.some((item) => item.kind === 'scan-finding')).toBe(true);
    expect(payload.items.every((item) => item.metadata.contributorId === 'install-abc')).toBe(true);
    expect(payload.items.every((item) => item.metadata.contributionScope === 'user-submitted-summary')).toBe(true);
    expect(validateExternalMemorySyncPayload(payload).valid).toBe(true);
  });

  it('rejects payloads where item contributor does not match payload contributor', () => {
    const config = { ...createExternalMemorySyncConfig(), contributorId: 'install-one' };
    const payload = buildExternalMemorySyncPayload({ config, now: 1 });
    const mutated = {
      ...payload,
      items: [{
        id: 'scan-1',
        kind: 'scan-finding' as const,
        title: 'Finding',
        text: 'Finding summary',
        tags: ['scan'],
        metadata: { contributorId: 'install-two', contributionScope: 'user-submitted-summary' },
      }],
    };
    const report = validateExternalMemorySyncPayload(mutated);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('contributorId does not match');
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

  it('checks gateway health', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'http://46.202.154.25:8088',
      allowSelfHostedHttp: true,
    };
    const fetcher = vi.fn(async (_url: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, service: 'sovereign-memory-gateway' }),
    }) as Response);

    const result = await checkExternalMemoryHealth({ config, fetcher: fetcher as unknown as typeof fetch });
    expect(result.ok).toBe(true);
    expect(result.status).toBe('ready');
    expect(String(fetcher.mock.calls[0][0])).toBe('http://46.202.154.25:8088/health');
  });

  it('posts to the gateway sync endpoint when enabled and valid', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'https://memory.example.test/base',
      clientAccessKey: 'session-key',
    };
    const payload = buildExternalMemorySyncPayload({ config, now: 1 });
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ accepted: true, imported: 1, exported: 2, rejected: 0, summary: 'done' }),
      init,
    }) as Response);

    const result = await syncExternalMemory({ config, payload, fetcher: fetcher as unknown as typeof fetch });
    expect(result.status).toBe('synced');
    expect(result.response?.imported).toBe(1);
    expect(String(fetcher.mock.calls[0][0])).toBe('https://memory.example.test/api/sovereign-memory/sync');
    expect((fetcher.mock.calls[0][1]?.headers as Record<string, string>)['X-Sovereign-Gateway-Key']).toBe('session-key');
  });

  it('accepts gateway sync success responses', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'https://memory.example.test',
    };
    const payload = buildExternalMemorySyncPayload({ config, now: 1 });
    const fetcher = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ success: true, imported: 2, exported: 0, rejected: 0, summary: 'gateway synced' }),
    }) as Response);

    const result = await syncExternalMemory({ config, payload, fetcher: fetcher as unknown as typeof fetch });
    expect(result.status).toBe('synced');
    expect(result.accepted).toBe(true);
    expect(result.response?.success).toBe(true);
    expect(result.response?.imported).toBe(2);
  });

  it('searches gateway patterns with contributor and shared-pattern request shape', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'https://memory.example.test',
      contributorId: 'install-abc',
    };
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ items: [{ id: 'remote-1', kind: 'solution-pattern', title: 'Lint repair', text: 'Repair lint pattern', tags: ['lint'], metadata: { contributionScope: 'shared-derived-pattern' } }] }),
      init,
    }) as Response);

    const result = await searchExternalMemory({ config, query: 'lint repair', fetcher: fetcher as unknown as typeof fetch });
    expect(result.ok).toBe(true);
    expect(result.items).toHaveLength(1);
    expect(result.query.contributorId).toBe('install-abc');
    expect(result.query.includeSharedPatterns).toBe(true);
    expect(String(fetcher.mock.calls[0][0])).toBe('https://memory.example.test/api/sovereign-memory/search');
  });

  it('pulls remote updates without making them contributor deletable', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'https://memory.example.test',
      contributorId: 'install-abc',
    };
    const fetcher = vi.fn(async (_url: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => ({ updates: [{ id: 'remote-2', kind: 'learning-pattern', title: 'Workflow hint', text: 'Use workflow watch', tags: ['workflow'], metadata: { contributionScope: 'shared-derived-pattern' } }] }),
    }) as Response);

    const result = await pullExternalMemoryUpdates({ config, fetcher: fetcher as unknown as typeof fetch });
    expect(result.ok).toBe(true);
    expect(result.items).toHaveLength(1);
    expect(String(fetcher.mock.calls[0][0])).toContain('/api/sovereign-memory/pull-updates');
    expect(String(fetcher.mock.calls[0][0])).toContain('workspaceId=local-workspace');
    expect(String(fetcher.mock.calls[0][0])).toContain('contributorId=install-abc');
    expect(String(fetcher.mock.calls[0][0])).toContain('includeSharedPatterns=true');
  });

  it('builds and validates explicit contributor-only remote memory erasure requests', () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      workspaceId: 'Pattern',
      collectionName: 'sovereign_logic_patterns',
      contributorId: 'install-abc',
    };
    const request = buildExternalMemoryDeleteRequest(config, 123);
    expect(request.contributorId).toBe('install-abc');
    expect(request.confirmDelete).toBe(true);
    expect(request.confirmationText).toBe(EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT);
    expect(request.scope).toBe('contributor-submissions');
    expect(request.preserveSharedPatterns).toBe(true);
    expect(validateExternalMemoryDeleteRequest(request).valid).toBe(true);
  });

  it('rejects erasure requests that could remove shared derived patterns', () => {
    const request = {
      schemaVersion: 1,
      client: 'sovereign-studio',
      redaction: 'summary-only-no-source-files',
      workspaceId: 'Pattern',
      collectionName: 'sovereign_logic_patterns',
      contributorId: 'install-abc',
      requestedAt: 123,
      confirmDelete: true,
      confirmationText: EXTERNAL_MEMORY_DELETE_CONFIRMATION_TEXT,
      scope: 'workspace-user-data',
      preserveSharedPatterns: false,
    } as const;
    const report = validateExternalMemoryDeleteRequest(request as never);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('contributor-submissions');
    expect(report.errors.join(' ')).toContain('preserve shared patterns');
  });

  it('posts contributor-only erasure requests and tracks retained shared items', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'https://memory.example.test',
      workspaceId: 'Pattern',
      collectionName: 'sovereign_logic_patterns',
      contributorId: 'install-abc',
    };
    const request = buildExternalMemoryDeleteRequest(config, 123);
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ success: true, deleted: true, deletedItems: 5, retainedSharedItems: 17, summary: 'contributor records removed' }),
      init,
    }) as Response);

    const result = await deleteExternalMemoryData({ config, request, fetcher: fetcher as unknown as typeof fetch });
    expect(result.status).toBe('synced');
    expect(result.deleted).toBe(true);
    expect(result.response?.deletedItems).toBe(5);
    expect(result.response?.retainedSharedItems).toBe(17);
    expect(String(fetcher.mock.calls[0][0])).toBe('https://memory.example.test/api/sovereign-memory/delete-user-data');
  });
});
