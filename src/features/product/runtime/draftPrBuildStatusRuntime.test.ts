import { describe, expect, it } from 'vitest';
import { resolveDraftPrBuildStatus } from './draftPrBuildStatusRuntime';

const draftPrUrl = 'https://example.test/pull/7';
const runUrl = 'https://example.test/actions/runs/1';

describe('resolveDraftPrBuildStatus', () => {
  it('returns success only from an actual successful run', () => {
    expect(resolveDraftPrBuildStatus({
      draftPrUrl,
      runs: [{ status: 'completed', conclusion: 'success', html_url: runUrl }],
    })).toMatchObject({
      state: 'success',
      label: 'Build erfolgreich',
      runUrl,
    });
  });

  it('returns failure for failed or cancelled runs', () => {
    expect(resolveDraftPrBuildStatus({
      draftPrUrl,
      runs: [{ status: 'completed', conclusion: 'failure' }],
    })).toMatchObject({ state: 'failure', label: 'Build fehlgeschlagen' });
  });

  it('returns running for active runs', () => {
    expect(resolveDraftPrBuildStatus({
      draftPrUrl,
      runs: [{ status: 'in_progress', conclusion: null }],
    })).toMatchObject({ state: 'running', label: 'Build läuft' });
  });

  it('returns pending for queued runs', () => {
    expect(resolveDraftPrBuildStatus({
      draftPrUrl,
      runs: [{ status: 'queued', conclusion: null }],
    })).toMatchObject({ state: 'pending', label: 'Build wartet' });
  });

  it('returns unknown instead of green when no runs exist', () => {
    const result = resolveDraftPrBuildStatus({ draftPrUrl, runs: [] });

    expect(result.state).toBe('unknown');
    expect(result.detail).toContain('kein grüner Status');
  });

  it('returns unknown with detail for fetch errors', () => {
    const result = resolveDraftPrBuildStatus({ draftPrUrl, fetchError: 'HTTP 403' });

    expect(result.state).toBe('unknown');
    expect(result.detail).toContain('HTTP 403');
  });

  it('does not request a status when no Draft PR URL exists', () => {
    expect(resolveDraftPrBuildStatus({ draftPrUrl: '' })).toMatchObject({
      state: 'unknown',
      detail: 'Kein Draft-PR-Link vorhanden; Buildstatus wird nicht abgefragt.',
    });
  });
});
