import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { SovereignWorkspaceEvidenceAnchor } from '../runtime/sovereignAgentRuntime';
import { WorkspaceEvidenceRail } from './WorkspaceEvidenceRail';

function anchor(overrides: Partial<SovereignWorkspaceEvidenceAnchor> = {}): SovereignWorkspaceEvidenceAnchor {
  return {
    anchorId: `evidence-${'a'.repeat(24)}`,
    claimKind: 'TEST_EXECUTION_RECEIPT_MATCH',
    verdict: 'VERIFIED',
    sourceVerdict: 'VERIFIED',
    sessionBindingHash: 'b'.repeat(64),
    runId: 'run-1',
    taskId: 'task-1',
    attemptId: 'attempt-1',
    actionId: 'tool-call-1',
    scope: `tool=test;input=${'c'.repeat(64)};effect=read`,
    sourceKind: 'AGENT_RUN_RECEIPT',
    sourceRefs: ['d'.repeat(64)],
    repositoryRevision: 'e'.repeat(40),
    observedAt: '2026-08-23T03:30:00Z',
    freshnessReasons: [],
    evidenceHash: 'f'.repeat(64),
    authoritative: false,
    ...overrides,
  };
}

describe('WorkspaceEvidenceRail', () => {
  it('renders icon and text verdict, then opens bounded technical source details', () => {
    render(<WorkspaceEvidenceRail anchors={[anchor()]} />);

    const badge = screen.getByRole('button', { name: /Verified: Test Execution Receipt Match/i });
    expect(badge).toHaveTextContent('✓ Verified');
    fireEvent.click(badge);

    const inspector = screen.getByRole('dialog', { name: 'Evidence Inspector' });
    expect(inspector).toHaveTextContent('attempt-1');
    expect(inspector).toHaveTextContent('AGENT_RUN_RECEIPT');
    expect(inspector).toHaveTextContent('eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee');
    expect(inspector).toHaveTextContent('Monitor/Frame sind selbst keine Success Authority');
  });

  it('never attaches anchors from an older attempt to the current rail', () => {
    const old = anchor({
      anchorId: `evidence-${'1'.repeat(24)}`,
      claimKind: 'WORKTREE_READBACK_RECEIPT_MATCH',
      attemptId: 'attempt-old',
      observedAt: '2026-08-23T03:20:00Z',
    });
    const current = anchor({ anchorId: `evidence-${'2'.repeat(24)}` });
    render(<WorkspaceEvidenceRail anchors={[old, current]} />);

    expect(screen.queryByRole('button', { name: /Worktree Readback Receipt Match/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Test Execution Receipt Match/i })).toBeInTheDocument();
  });

  it('shows stale and contradicted states as text, not color alone', () => {
    const contradicted = anchor({ verdict: 'CONTRADICTED', sourceVerdict: 'VERIFIED', freshnessReasons: ['IMAGE_DIGEST_CONTRADICTED'] });
    render(<WorkspaceEvidenceRail anchors={[contradicted]} />);
    expect(screen.getByRole('button', { name: /Contradicted/i })).toHaveTextContent('! Contradicted');
  });
});
