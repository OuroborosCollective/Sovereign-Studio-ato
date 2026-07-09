import { describe, expect, it } from 'vitest';
import {
  buildOpenHandsJobRequest,
  createOpenHandsIdleSnapshot,
  isOpenHandsTerminalStatus,
  maskOpenHandsSensitiveText,
  resolveOpenHandsEnterpriseConfig,
  summarizeOpenHandsJob,
} from './openhandsEnterpriseRuntime';

describe('openhandsEnterpriseRuntime', () => {
  it('is disabled by default and does not invent a runtime endpoint', () => {
    const config = resolveOpenHandsEnterpriseConfig();

    expect(config.enabled).toBe(false);
    expect(config.ready).toBe(false);
    expect(config.agentApiUrl).toBe('');
  });


  it('does not auto-enable the legacy external agent from URL alone', () => {
    const config = resolveOpenHandsEnterpriseConfig({
      agentApiUrl: 'https://openhands.example.com/api/',
    });

    expect(config.enabled).toBe(false);
    expect(config.ready).toBe(false);
    expect(config.agentApiUrl).toBe('https://openhands.example.com/api');
    expect(config.reason).toContain('disabled');
  });

  it('accepts an HTTPS agent API as external runtime backend', () => {
    const config = resolveOpenHandsEnterpriseConfig({
      enabled: true,
      agentApiUrl: 'https://openhands.example.com/api/',
      adminConsoleUrl: 'https://openhands.example.com/admin/',
    });

    expect(config.ready).toBe(true);
    expect(config.deploymentMode).toBe('external-agent-runtime');
    expect(config.agentApiUrl).toBe('https://openhands.example.com/api');
    expect(config.adminConsoleUrl).toBe('https://openhands.example.com/admin');
  });

  it('rejects unsafe non-local HTTP agent URLs', () => {
    const config = resolveOpenHandsEnterpriseConfig({
      enabled: true,
      agentApiUrl: 'http://openhands.example.com/api',
    });

    expect(config.ready).toBe(false);
    expect(config.reason).toContain('HTTPS');
  });



  it('enables the internal Sovereign Agent backend without OpenHands flag when mode is explicit', () => {
    const config = resolveOpenHandsEnterpriseConfig({
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://sovereign-backend.example',
    });

    expect(config.enabled).toBe(true);
    expect(config.ready).toBe(true);
    expect(config.deploymentMode).toBe('sovereign-agent-backend');
    expect(config.reason).toContain('Sovereign Agent Backend');
  });

  it('builds requests for the sovereign local runner by default', () => {
    const request = buildOpenHandsJobRequest({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      mission: 'Run internal agent path.',
    });

    expect(request.executor).toBe('sovereign-local-runner');
    expect(request.provisionWorkspace).toBe(true);
    expect(request.cloneRepo).toBe(true);
  });

  it('builds draft-pr-only job requests', () => {
    const request = buildOpenHandsJobRequest({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      mission: 'Fix UI truth flow',
    });

    expect(request.draftPrOnly).toBe(true);
    expect(request.allowAutoMerge).toBe(false);
    expect(request.runtimeTruthRequired).toBe(true);
    expect(request.source).toBe('sovereign-studio');
  });

  it('summarizes idle, blocked and completed states without fake progress', () => {
    expect(summarizeOpenHandsJob(createOpenHandsIdleSnapshot())).toContain('wartet');
    expect(summarizeOpenHandsJob({ status: 'blocked', changedFiles: [], events: [], lastError: 'Guard red' })).toBe('Guard red');
    expect(summarizeOpenHandsJob({ status: 'completed', changedFiles: ['README.md'], events: [], draftPrUrl: 'https://github.test/pr/1' })).toContain('Draft PR');
    expect(summarizeOpenHandsJob({ status: 'completed', changedFiles: [], events: [] })).toContain('kein Draft PR ist belegt');
  });

  it('detects terminal states', () => {
    expect(isOpenHandsTerminalStatus('running')).toBe(false);
    expect(isOpenHandsTerminalStatus('blocked')).toBe(true);
    expect(isOpenHandsTerminalStatus('failed')).toBe(true);
    expect(isOpenHandsTerminalStatus('completed')).toBe(true);
  });

  it('masks license, token and registry password text', () => {
    const raw = [
      'licenseID: abc123',
      'Authorization: secret-token',
      'registry-password hunter2',
      'token=secret',
    ].join('\n');

    const masked = maskOpenHandsSensitiveText(raw);

    expect(masked).not.toContain('abc123');
    expect(masked).not.toContain('secret-token');
    expect(masked).not.toContain('hunter2');
    expect(masked).not.toContain('token=secret');
    expect(masked).toContain('[redacted]');
  });

  it('rejects empty repoUrl in job request', () => {
    expect(() => buildOpenHandsJobRequest({
      repoUrl: '',
      mission: 'test',
    })).toThrow('repository URL');
  });

  it('rejects empty mission in job request', () => {
    expect(() => buildOpenHandsJobRequest({
      repoUrl: 'https://github.com/test/repo',
      mission: '',
    })).toThrow('mission');
  });

  it('defaults branch to main when not provided', () => {
    const request = buildOpenHandsJobRequest({
      repoUrl: 'https://github.com/test/repo',
      mission: 'test mission',
    });
    expect(request.branch).toBe('main');
  });

  it('does not fabricate ready state when no config is provided', () => {
    const config = resolveOpenHandsEnterpriseConfig();
    expect(config.ready).toBe(false);
    expect(config.reason).toContain('disabled');
  });

  it('requires HTTPS for non-local URLs', () => {
    const config = resolveOpenHandsEnterpriseConfig({
      enabled: true,
      agentApiUrl: 'https://api.openhands.com/v1',
    });
    expect(config.ready).toBe(true);
    expect(config.reason).not.toContain('missing or unsafe');
  });

  it('summarizes running state with runtime ID when available', () => {
    const snapshot = {
      status: 'running' as const,
      openHandsId: 'oh-12345',
      changedFiles: ['README.md'],
      events: [],
    };
    const summary = summarizeOpenHandsJob(snapshot);
    expect(summary).toContain('oh-12345');
    expect(summary).toContain('1 Datei');
  });

  it('summarizes waiting-for-user state correctly', () => {
    const snapshot = {
      status: 'waiting-for-user' as const,
      changedFiles: [],
      events: [],
    };
    expect(summarizeOpenHandsJob(snapshot)).toContain('wartet');
  });

  it('detects non-terminal states correctly', () => {
    expect(isOpenHandsTerminalStatus('idle')).toBe(false);
    expect(isOpenHandsTerminalStatus('queued')).toBe(false);
    expect(isOpenHandsTerminalStatus('running')).toBe(false);
    expect(isOpenHandsTerminalStatus('waiting-for-user')).toBe(false);
  });
});
