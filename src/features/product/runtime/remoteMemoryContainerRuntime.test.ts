import { describe, expect, it } from 'vitest';
import {
  buildRemoteMemoryContainerStatus,
  createRemoteMemoryContainerConfig,
  remoteMemoryErrorMessage,
  summarizeRemoteMemoryPreview,
} from './remoteMemoryContainerRuntime';
import type { ExternalMemorySyncPreview } from './externalMemorySyncPreview';

describe('remoteMemoryContainerRuntime', () => {
  it('creates stable default config with caller overrides', () => {
    const config = createRemoteMemoryContainerConfig({ enabled: true, gatewayUrl: 'https://memory.example.test' });

    expect(config.enabled).toBe(true);
    expect(config.gatewayUrl).toBe('https://memory.example.test');
    expect(config.workspaceId).toBe('Pattern');
    expect(config.collectionName).toBe('sovereign_logic_patterns');
    expect(config.contributorId).toBe('sovereign-local-install');
  });

  it('reports disabled, busy and ready status', () => {
    const disabled = buildRemoteMemoryContainerStatus(createRemoteMemoryContainerConfig(), false);
    expect(disabled.canRun).toBe(false);
    expect(disabled.label).toContain('aus');

    const readyConfig = createRemoteMemoryContainerConfig({ enabled: true, gatewayUrl: 'https://memory.example.test' });
    expect(buildRemoteMemoryContainerStatus(readyConfig, true).label).toContain('arbeitet');
    expect(buildRemoteMemoryContainerStatus(readyConfig, false).canRun).toBe(true);
  });

  it('summarizes preview counts', () => {
    const preview: ExternalMemorySyncPreview = {
      valid: true,
      itemCount: 3,
      estimatedBytes: 123,
      contributorId: 'install-abc',
      workspaceId: 'Pattern',
      collectionName: 'collection',
      redaction: 'summary-only-no-source-files',
      includesRawSourceFiles: false,
      includesSessionSecret: false,
      kindCounts: { 'scan-finding': 1, 'learning-pattern': 1, 'solution-pattern': 1 },
      validation: { valid: true, errors: [], warnings: [], summary: 'ok' },
      summary: 'ready',
    };

    expect(summarizeRemoteMemoryPreview(preview)).toContain('items=3');
    expect(summarizeRemoteMemoryPreview(null)).toContain('Noch keine');
  });

  it('normalizes error messages', () => {
    expect(remoteMemoryErrorMessage(new Error('boom'))).toBe('boom');
    expect(remoteMemoryErrorMessage(' text ')).toBe('text');
    expect(remoteMemoryErrorMessage(null)).toBe('Remote memory action failed.');
  });
});
