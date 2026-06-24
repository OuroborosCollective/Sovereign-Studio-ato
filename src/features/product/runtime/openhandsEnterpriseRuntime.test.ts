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
});
