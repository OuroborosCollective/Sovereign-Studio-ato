import { describe, expect, it } from 'vitest';
import {
  containsSovereignSecretLikeText,
  createSovereignToolObservation,
  hasRepeatedSovereignObservation,
  sanitizeSovereignObservationText,
  summarizeSovereignToolObservation,
} from './sovereignToolObservationRuntime';

describe('sovereignToolObservationRuntime', () => {
  it('creates compact action stream events for selected and started tools', () => {
    const selected = createSovereignToolObservation({
      toolName: 'direct_patch',
      route: 'direct-github-patch',
      phase: 'selected',
      target: 'README.md',
      argumentsSummary: 'small doc change',
      createdAt: 1700000000000,
    });

    expect(selected.event.kind).toBe('route_selected');
    expect(selected.event.state).toBe('queued');
    expect(selected.event.route).toBe('direct-github-patch');
    expect(selected.event.detail).toContain('README.md');

    const started = createSovereignToolObservation({
      toolName: 'sovereign-agent',
      route: 'sovereign-agent',
      phase: 'started',
      createdAt: 1700000000001,
    });

    expect(started.event.kind).toBe('executor_started');
    expect(started.event.state).toBe('running');
  });

  it('maps completed, failed, and blocked phases to terminal event states', () => {
    expect(createSovereignToolObservation({
      toolName: 'direct_patch',
      route: 'direct-github-patch',
      phase: 'completed',
    }).event.state).toBe('done');

    expect(createSovereignToolObservation({
      toolName: 'direct_patch',
      route: 'direct-github-patch',
      phase: 'failed',
    }).event.kind).toBe('failed');

    expect(createSovereignToolObservation({
      toolName: 'direct_patch',
      route: 'direct-github-patch',
      phase: 'blocked',
      blocker: 'github_access_missing',
    }).event.kind).toBe('blocked');
  });

  it('redacts secret-like text from summaries and events', () => {
    const secret = 'token=ghp_abcdefghijklmnopqrstuvwxyz1234567890';
    expect(containsSovereignSecretLikeText(secret)).toBe(true);
    expect(sanitizeSovereignObservationText(secret)).not.toContain('ghp_');

    const observation = createSovereignToolObservation({
      toolName: 'github',
      route: 'github-access',
      phase: 'blocked',
      argumentsSummary: secret,
      blocker: 'api_key=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890',
    });

    expect(observation.argumentsSummary).toContain('[redacted-secret]');
    expect(observation.event.detail).toContain('[redacted-secret]');
    expect(observation.event.detail).not.toContain('sk-proj-');
  });

  it('summarizes observations without leaking raw details', () => {
    const observation = createSovereignToolObservation({
      toolName: 'worker_chat',
      route: 'worker',
      phase: 'observed',
      resultSummary: 'answer ready',
    });

    expect(summarizeSovereignToolObservation(observation)).toBe(
      'observed worker_chat via worker result: answer ready',
    );
  });

  it('detects repeated identical observations', () => {
    const observations = [1, 2, 3].map((n) => createSovereignToolObservation({
      toolName: 'sovereign-agent',
      route: 'sovereign-agent',
      phase: 'blocked',
      blocker: 'github_access_missing',
      createdAt: n,
    }));

    expect(hasRepeatedSovereignObservation(observations, 2)).toBe(true);
  });
});
