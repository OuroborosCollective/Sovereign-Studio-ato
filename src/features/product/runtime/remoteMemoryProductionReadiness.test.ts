import { describe, expect, it } from 'vitest';
import { createExternalMemorySyncConfig } from './externalMemorySync';
import {
  formatRemoteMemoryProductionChecklist,
  validateRemoteMemoryProductionReadiness,
} from './remoteMemoryProductionReadiness';

function productionConfig() {
  return {
    ...createExternalMemorySyncConfig(),
    enabled: true,
    consentAccepted: true,
    gatewayUrl: 'https://memory.example.test',
    workspaceId: 'Pattern',
    collectionName: 'sovereign_logic_patterns',
    contributorId: 'install-abc',
  };
}

describe('remoteMemoryProductionReadiness', () => {
  it('passes a locked-down production gateway setup', () => {
    const report = validateRemoteMemoryProductionReadiness({
      config: productionConfig(),
      allowedOrigins: ['https://app.example.test'],
      rateLimitPerMinute: 60,
      maxBodyBytes: 128_000,
      maxResponseBytes: 256_000,
      gatewayHealthPath: '/health',
    });

    expect(report.ready).toBe(true);
    expect(report.blockers).toHaveLength(0);
    expect(formatRemoteMemoryProductionChecklist(report)).toContain('production readiness passed');
  });

  it('blocks non-https production gateway and wildcard origins', () => {
    const report = validateRemoteMemoryProductionReadiness({
      config: { ...productionConfig(), gatewayUrl: 'http://memory.example.test', allowSelfHostedHttp: true },
      allowedOrigins: ['*'],
      rateLimitPerMinute: 60,
      maxBodyBytes: 128_000,
      maxResponseBytes: 256_000,
      gatewayHealthPath: '/health',
    });

    expect(report.ready).toBe(false);
    expect(report.blockers.join(' ')).toContain('HTTPS');
    expect(report.blockers.join(' ')).toContain('Wildcard');
  });

  it('blocks direct database port and private hosts', () => {
    const report = validateRemoteMemoryProductionReadiness({
      config: { ...productionConfig(), gatewayUrl: 'http://127.0.0.1:19530', allowSelfHostedHttp: true },
      allowedOrigins: ['https://app.example.test'],
      rateLimitPerMinute: 60,
      maxBodyBytes: 128_000,
      maxResponseBytes: 256_000,
      gatewayHealthPath: '/health',
    });

    expect(report.ready).toBe(false);
    expect(report.blockers.join(' ')).toContain('private LAN');
    expect(report.blockers.join(' ')).toContain('vector database port');
  });

  it('requires explicit limits', () => {
    const report = validateRemoteMemoryProductionReadiness({
      config: productionConfig(),
      allowedOrigins: ['https://app.example.test'],
    });

    expect(report.ready).toBe(false);
    expect(report.blockers.join(' ')).toContain('rate limit');
    expect(report.blockers.join(' ')).toContain('body limit');
    expect(report.blockers.join(' ')).toContain('response size limit');
  });
});
