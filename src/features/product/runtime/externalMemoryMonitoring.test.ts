import { describe, expect, it, vi } from 'vitest';
import { createExternalMemorySyncConfig } from './externalMemorySync';
import {
  fetchExternalMemoryMonitoring,
  normalizeExternalMemoryMonitoringPayload,
  validateExternalMemoryMonitoringPayload,
} from './externalMemoryMonitoring';

describe('externalMemoryMonitoring', () => {
  it('normalizes and validates gateway monitoring payloads', () => {
    const monitoring = normalizeExternalMemoryMonitoringPayload({
      service: 'sovereign-memory-gateway',
      version: '1.0.0',
      uptime: 6.5,
      memoryUsage: { rss: 100, heapUsed: 50, ignored: 'no' },
      inboundStats: {
        totalRequests: 10,
        blockedRequests: 1,
        filteredRequests: 2,
        passedRequests: 7,
      },
      milvusConnected: true,
    });

    expect(monitoring.service).toBe('sovereign-memory-gateway');
    expect(monitoring.memoryUsage.rss).toBe(100);
    expect(monitoring.inboundStats.passedRequests).toBe(7);
    expect(validateExternalMemoryMonitoringPayload(monitoring).valid).toBe(true);
  });

  it('rejects invalid monitoring counters', () => {
    const monitoring = normalizeExternalMemoryMonitoringPayload({
      service: 'sovereign-memory-gateway',
      version: '1.0.0',
      uptime: 1,
      memoryUsage: { rss: 100 },
      inboundStats: { totalRequests: -1 },
      milvusConnected: true,
    });

    const report = validateExternalMemoryMonitoringPayload(monitoring);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('totalRequests');
  });

  it('soft-fails when remote memory is disabled', async () => {
    const result = await fetchExternalMemoryMonitoring({ config: createExternalMemorySyncConfig() });
    expect(result.status).toBe('disabled');
    expect(result.ok).toBe(false);
  });

  it('fetches gateway monitoring endpoint', async () => {
    const config = {
      ...createExternalMemorySyncConfig(),
      enabled: true,
      consentAccepted: true,
      gatewayUrl: 'http://46.202.154.25:8088',
      allowSelfHostedHttp: true,
      contributorId: 'install-abc',
    };
    const fetcher = vi.fn(async (_url: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => ({
        service: 'sovereign-memory-gateway',
        version: '1.0.0',
        uptime: 6.5,
        memoryUsage: { rss: 106201088, heapUsed: 27860760 },
        inboundStats: { totalRequests: 0, blockedRequests: 0, filteredRequests: 0, passedRequests: 0 },
        milvusConnected: true,
      }),
    }) as Response);

    const result = await fetchExternalMemoryMonitoring({ config, fetcher: fetcher as unknown as typeof fetch });
    expect(result.status).toBe('ready');
    expect(result.ok).toBe(true);
    expect(result.monitoring?.milvusConnected).toBe(true);
    expect(String(fetcher.mock.calls[0][0])).toBe('http://46.202.154.25:8088/api/sovereign-memory/monitoring');
  });
});
