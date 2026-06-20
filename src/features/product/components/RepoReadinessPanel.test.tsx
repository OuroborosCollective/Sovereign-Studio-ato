// @vitest-environment jsdom

import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RepoReadinessPanel } from './RepoReadinessPanel';
import type { SovereignHealthReport } from '../runtime/sovereignHealth';

function health(status: SovereignHealthReport['status'], recommendations: string[] = []): SovereignHealthReport {
  return {
    status,
    criticalRisks: status === 'red' ? 1 : 0,
    totalIssues: status === 'green' ? 0 : 1,
    repairsLogged: 0,
    branchDelta: status === 'red' ? 1 : 0,
    summary: `Health ${status}`,
    recommendations,
  };
}

describe('RepoReadinessPanel', () => {
  it('surfaces blocked telemetry health gate inside readiness', () => {
    render(
      <RepoReadinessPanel
        repoUrl="https://github.com/OuroborosCollective/Sovereign-Studio-ato"
        files={[{ path: 'README.md', type: 'blob' }]}
        status="Loaded repository snapshot"
        healthReport={health('red', ['Open Telemetry.', 'Resolve dependency.'])}
      />,
    );

    const gate = screen.getByTestId('telemetry-health-gate');
    expect(within(gate).getByText('Telemetry Health Gate')).toBeDefined();
    expect(within(gate).getByText('blocked · red')).toBeDefined();
    expect(within(gate).getByText(/Health red prevents guarded output/)).toBeDefined();
    expect(within(gate).getByText('Open Telemetry.')).toBeDefined();
  });

  it('surfaces allowed health gate inside readiness', () => {
    render(
      <RepoReadinessPanel
        repoUrl="https://github.com/OuroborosCollective/Sovereign-Studio-ato"
        files={[{ path: 'README.md', type: 'blob' }]}
        healthReport={health('green')}
      />,
    );

    const gate = screen.getByTestId('telemetry-health-gate');
    expect(within(gate).getByText('allowed · green')).toBeDefined();
  });
});
