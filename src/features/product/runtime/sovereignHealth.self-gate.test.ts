import { describe, expect, it } from 'vitest';
import type { RepoFile } from '../../github/types';
import { buildSovereignHealthReport, isHealthGateFeedbackTelemetry } from './sovereignHealth';
import { createInitialTelemetryState, createTelemetryEvent, appendTelemetryEvent } from './sovereignTelemetry';

const repoFiles: RepoFile[] = [
  { path: 'src/App.tsx', type: 'blob', size: 42 },
];

function telemetryWith(...events: ReturnType<typeof createTelemetryEvent>[]) {
  return events.reduce(
    (state, event) => appendTelemetryEvent(state, event),
    createInitialTelemetryState(),
  );
}

describe('sovereign health self-gate telemetry guard', () => {
  it('does not let health-gate feedback make health red again', () => {
    const event = createTelemetryEvent(
      'workflow',
      'error',
      'sequence:draft-pr-publish:failed',
      'Health red prevents guarded output: Health red: 2 critical risk(s), 8 total issue(s), 0 repair signal(s).',
      undefined,
      1_000,
    );

    expect(isHealthGateFeedbackTelemetry(event)).toBe(true);

    const report = buildSovereignHealthReport({
      repoFiles,
      telemetry: telemetryWith(event),
    });

    expect(report.criticalRisks).toBe(0);
    expect(report.status).not.toBe('red');
  });

  it('still treats real non-health telemetry errors as critical', () => {
    const event = createTelemetryEvent(
      'workflow',
      'error',
      'workflow:watch-finished',
      'GitHub workflow failed on build job.',
      undefined,
      2_000,
    );

    expect(isHealthGateFeedbackTelemetry(event)).toBe(false);

    const report = buildSovereignHealthReport({
      repoFiles,
      telemetry: telemetryWith(event),
    });

    expect(report.criticalRisks).toBe(1);
    expect(report.status).toBe('red');
  });
});
