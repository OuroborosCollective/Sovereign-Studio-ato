import { describe, expect, it, vi } from 'vitest';
import { createExternalMemorySyncConfig } from './externalMemorySync';
import { createSolutionPatternStore, type SolutionPatternStore } from './solutionPatternMemory';
import {
  monitorAndPullRemoteUpdatesIntoSolutionMemory,
  pullRemoteUpdatesIntoSolutionMemory,
} from './remoteMemoryGatewayBridge';

function config() {
  return {
    ...createExternalMemorySyncConfig(),
    enabled: true,
    consentAccepted: true,
    gatewayUrl: 'http://46.202.154.25:8088',
    allowSelfHostedHttp: true,
    contributorId: 'install-abc',
  };
}

describe('remoteMemoryGatewayBridge', () => {
  it('pulls shared updates into local solution memory', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => ({
        updates: [{
          id: 'remote-1',
          kind: 'solution-pattern',
          title: 'Build check fails after generated runtime update',
          text: 'Inspect the failed build check and patch generated runtime exports.',
          tags: ['build-logic', 'generated-file'],
          metadata: {
            contributionScope: 'shared-derived-pattern',
            category: 'build-logic',
            fileExtension: '.ts',
            successfulUses: 2,
          },
        }],
      }),
    }) as Response);

    const result = await pullRemoteUpdatesIntoSolutionMemory({
      config: config(),
      store: createSolutionPatternStore(1),
      now: 10,
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.updates.items).toHaveLength(1);
    expect(result.intake.accepted).toBe(1);
    expect(result.store.patterns).toHaveLength(1);
  });

  it('soft blocks pull when the local solution store is invalid', async () => {
    const badStore: SolutionPatternStore = {
      version: 1,
      patterns: [{
        id: '',
        status: 'active',
        problemSignature: '',
        contextFingerprint: '',
        fixFingerprint: '',
        category: 'workflow',
        filePathHint: '',
        fileExtension: '.ts',
        problemSummary: '',
        beforeFingerprint: '',
        solutionSummary: '',
        afterFingerprint: '',
        conditions: [],
        recommendedSteps: [],
        evidence: '',
        intakeNode: 'learning-memory',
        processingNode: 'learning-memory',
        outputNodes: [],
        confidence: 'inferred',
        tags: [],
        hits: 0,
        successfulUses: 0,
        rejectedUses: 0,
        createdAt: 10,
        updatedAt: 1,
      }],
      rejections: [],
      updatedAt: 10,
    };
    const fetcher = vi.fn();
    const result = await pullRemoteUpdatesIntoSolutionMemory({
      config: config(),
      store: badStore,
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.updates.status).toBe('soft-failed');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('monitors the gateway before pulling updates', async () => {
    const fetcher = vi.fn(async (url: RequestInfo | URL) => {
      const target = String(url);
      if (target.includes('/monitoring')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            service: 'sovereign-memory-gateway',
            version: '1.0.0',
            uptime: 5,
            memoryUsage: { rss: 100, heapUsed: 50 },
            inboundStats: { totalRequests: 4, blockedRequests: 0, filteredRequests: 0, passedRequests: 4 },
            milvusConnected: true,
          }),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          items: [{
            id: 'remote-2',
            kind: 'solution-pattern',
            title: 'Workflow watch fails after action update',
            text: 'Use workflow watch result as repair mission and regenerate guarded file.',
            tags: ['workflow', 'runtime-guard'],
            metadata: { contributionScope: 'shared-derived-pattern', category: 'workflow', fileExtension: '.ts' },
          }],
        }),
      } as Response;
    });

    const result = await monitorAndPullRemoteUpdatesIntoSolutionMemory({
      config: config(),
      store: createSolutionPatternStore(1),
      now: 10,
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.monitoring.ok).toBe(true);
    expect(result.intake.accepted).toBe(1);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});
