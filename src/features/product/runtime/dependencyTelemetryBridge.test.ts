import { describe, expect, it } from 'vitest';
import { createDependencyTelemetryEvent } from './dependencyTelemetryBridge';

describe('dependencyTelemetryBridge', () => {
  it('maps dependency source github into github telemetry stage', () => {
    const event = createDependencyTelemetryEvent({
      stage: 'runtime',
      level: 'success',
      label: 'dependency:github:ready',
      message: 'GitHub ready.',
      details: { dependencySource: 'github', dependencyKey: 'repo-tree' },
    }, 1_000);

    expect(event?.stage).toBe('github');
    expect(event?.level).toBe('success');
    expect(event?.label).toBe('dependency:github:ready');
    expect(event?.details?.dependencyKey).toBe('repo-tree');
  });

  it('maps remote and pattern memory sources into memory stage', () => {
    const remote = createDependencyTelemetryEvent({
      stage: 'runtime',
      level: 'warning',
      label: 'dependency:remote-memory:degraded',
      message: 'Remote memory degraded.',
      details: { dependencySource: 'remote-memory' },
    }, 1_000);
    const pattern = createDependencyTelemetryEvent({
      stage: 'runtime',
      level: 'info',
      label: 'dependency:pattern-memory:idle',
      message: 'Pattern memory waiting.',
      details: { dependencySource: 'pattern-memory' },
    }, 2_000);

    expect(remote?.stage).toBe('memory');
    expect(pattern?.stage).toBe('memory');
  });

  it('falls back to ui for unknown event shapes and filters unsupported details', () => {
    const event = createDependencyTelemetryEvent({
      stage: 'runtime',
      level: 'notice',
      label: 'dependency:custom:idle',
      message: 'Custom dependency waiting.',
      details: { ok: true, nested: { ignored: true }, list: ['ignored'] },
    }, 3_000);

    expect(event?.stage).toBe('ui');
    expect(event?.level).toBe('info');
    expect(event?.details).toEqual({ ok: true });
  });

  it('returns null when label or message is missing', () => {
    expect(createDependencyTelemetryEvent({ label: 'x' })).toBeNull();
    expect(createDependencyTelemetryEvent({ message: 'x' })).toBeNull();
  });
});
