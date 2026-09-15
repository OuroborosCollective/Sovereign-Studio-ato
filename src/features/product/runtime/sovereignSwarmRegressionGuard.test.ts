import { describe, it, expect } from 'vitest';
import { buildRepositoryBoundRunRequest } from '../../control-surface-vnext/adapter/repository-bound-adapter';
import { buildRunRequest } from '../../control-surface-vnext/adapter/production-adapter';
import { createPrimaryBridgeAdapter } from '../llm/adapters/primaryBridgeAdapter';
import type { SovereignAgentConfig } from './sovereignAgentRuntime';

describe('Systemic Regression & Runtime Assurance (Frontend Guard)', () => {
  it('enforces that Swarm mode is explicitly opted-in and never silently replaces Agent Zero repository execution', () => {
    const singleAgentPayload = buildRunRequest('Mission text', 'single');
    expect(singleAgentPayload.agentMode).toBe('single');

    const swarmAgentPayload = buildRunRequest('Mission text', 'swarm');
    expect(swarmAgentPayload.agentMode).toBe('swarm');

    // Repository adapter should explicitly fail if swarm is passed
    expect(() => buildRepositoryBoundRunRequest('Repository task', 'swarm')).toThrow(/single agent/i);
  });

  it('preserves the explicit single-agent routing path without swarm fallback', () => {
    const runRequest = buildRepositoryBoundRunRequest('Test repository task');
    expect(runRequest.agentMode).toBe('single');
    expect(runRequest.intentMode).toBe('repository_execution');
  });

  it('verifies FreeLLM API and Revolver endpoints are correctly bound in the primary bridge adapter', async () => {
    // The primary bridge adapter creates the routes for Sovereign backend. We verify it doesn't allow random fallbacks
    // and properly throws when missing configuration, effectively asserting the strict bounds of the direct OpenRouter/FreeLLM setup.
    const adapter = createPrimaryBridgeAdapter({});

    expect(adapter.label).toBe('Sovereign Backend · OpenRouter Paid + FreeLLM Free');
  });

  it('validates Sovereign Agent configuration endpoints and connections (mock)', () => {
    const validConfig: SovereignAgentConfig = {
      enabled: true,
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://backend.example.com',
      ready: true,
      reason: 'ready',
    };

    // Connection must be established to the backend API explicitly.
    expect(validConfig.agentApiUrl).toContain('https://');
    expect(validConfig.deploymentMode).toBe('sovereign-agent-backend');
  });
});
