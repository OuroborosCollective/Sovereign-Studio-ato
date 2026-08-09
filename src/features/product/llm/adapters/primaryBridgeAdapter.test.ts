import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPrimaryBridgeAdapter } from './primaryBridgeAdapter';

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
  });
}

const VALID_BRAIN = {
  perception: {
    domain: 'runtime',
    intent: 'fix',
    architecture: 'direct route',
    confidence: 0.9,
  },
  analysis: {
    severity: 'medium',
    issues: [],
    rootCause: 'A stale provider alias was selected.',
    systemicRisk: 'The route can be rejected before transport.',
  },
  plan: {
    strategy: 'Use the persisted route identity.',
    phases: [],
    estimatedComplexity: 'low',
  },
  execution: {
    patches: [{
      file: 'src/runtime.ts',
      type: 'replace',
      description: 'Resolve the verified route.',
      code: 'export const route = "verified";',
    }],
    integrationNotes: 'No direct provider credential is exposed.',
    testStrategy: 'Run route selection tests.',
  },
  learning: {
    patterns: [],
    rules: [],
    architectureUpgrade: 'Keep provider aliases behind persisted routes.',
  },
};

describe('primaryBridgeAdapter', () => {
  it('posts the immutable selected route ID instead of its provider model alias', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [{
          id: 'route-verified-free',
          defaultModelId: 'revolver-free-provider-model',
          enabled: true,
        }],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'revolver-free-provider-model',
        choices: [{ message: { content: JSON.stringify(VALID_BRAIN) } }],
      }));
    vi.stubGlobal('fetch', fetchMock);

    const adapter = createPrimaryBridgeAdapter({
      proxyUrl: 'https://sovereign-backend.arelorian.de',
      model: 'revolver-free-provider-model',
    });
    const result = await adapter.run({
      mission: 'Repair the runtime route.',
      repoPaths: ['src/runtime.ts'],
      selectedFilePath: 'src/runtime.ts',
    });

    expect(result.providerId).toBe('optional-user-keys');
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request.model).toBe('route-verified-free');
  });
});
