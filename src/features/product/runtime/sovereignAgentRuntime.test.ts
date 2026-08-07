import { describe, expect, it } from 'vitest';
import {
  buildSovereignAgentJobRequest,
  createSovereignAgentIdleSnapshot,
  isSovereignAgentTerminalStatus,
  resolveSovereignAgentConfig,
  summarizeSovereignAgentJob,
} from './sovereignAgentRuntime';

describe('sovereignAgentRuntime', () => {
  it('uses only the internal backend mode', () => {
    expect(resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'https://agent.example.test' })).toMatchObject({ ready: true, deploymentMode: 'sovereign-agent-backend' });
  });
  it('uses the current HTTPS or localhost origin when no build-time backend URL is present', () => {
    const config = resolveSovereignAgentConfig();
    expect(config.agentApiUrl).toBe(window.location.origin);
    expect(config).toMatchObject({ ready: true, deploymentMode: 'sovereign-agent-backend' });
  });
  it('rejects unsafe non-local HTTP URLs', () => {
    expect(resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'http://agent.example.test' }).ready).toBe(false);
  });
  it('builds a sovereign-local-runner request', () => {
    expect(buildSovereignAgentJobRequest({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })).toMatchObject({ executor: 'sovereign-local-runner', draftPrOnly: true, allowAutoMerge: false, cloneRepo: true });
  });
  it('keeps completion without a Draft PR visibly unproven', () => {
    expect(summarizeSovereignAgentJob({ ...createSovereignAgentIdleSnapshot(), status: 'completed' })).toContain('kein Draft PR');
  });
  it('recognizes terminal states', () => {
    expect(isSovereignAgentTerminalStatus('completed')).toBe(true);
    expect(isSovereignAgentTerminalStatus('running')).toBe(false);
  });
});
