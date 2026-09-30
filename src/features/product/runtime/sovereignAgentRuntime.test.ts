import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buildSovereignAgentJobRequest,
  createSovereignAgentIdleSnapshot,
  isSovereignAgentTerminalStatus,
  resolveSovereignAgentConfig,
  summarizeSovereignAgentJob,
} from './sovereignAgentRuntime';

describe('sovereignAgentRuntime', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });
  it('uses only the internal backend mode', () => {
    expect(resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'https://agent.example.test' })).toMatchObject({ ready: true, deploymentMode: 'sovereign-agent-backend' });
  });
  it('resolves the production backend from the same browser origin when no override exists', () => {
    vi.stubGlobal('window', { location: { origin: 'https://knd.arelorian.de' } });
    const config = resolveSovereignAgentConfig();
    expect(config).toMatchObject({
      enabled: true,
      ready: true,
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://knd.arelorian.de',
    });
  });
  it('allows an explicit same-origin backend mode without inventing an external agent host', () => {
    expect(resolveSovereignAgentConfig({
      enabled: true,
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: '',
    })).toMatchObject({
      enabled: true,
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: '',
      ready: true,
    });
  });
  it('rejects unsafe non-local HTTP URLs', () => {
    expect(resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'http://agent.example.test' }).ready).toBe(false);
  });
  it('builds a sovereign-local-runner request', () => {
    expect(buildSovereignAgentJobRequest({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })).toMatchObject({ executor: 'sovereign-local-runner', draftPrOnly: true, allowAutoMerge: false, cloneRepo: false });
  });
  it('keeps completion without a Draft PR visibly unproven', () => {
    expect(summarizeSovereignAgentJob({ ...createSovereignAgentIdleSnapshot(), status: 'completed' })).toContain('kein Draft PR');
  });
  it('recognizes terminal states', () => {
    expect(isSovereignAgentTerminalStatus('completed')).toBe(true);
    expect(isSovereignAgentTerminalStatus('running')).toBe(false);
  });
});
