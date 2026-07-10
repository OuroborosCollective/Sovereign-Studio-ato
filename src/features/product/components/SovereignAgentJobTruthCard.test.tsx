import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SovereignAgentJobTruthCard } from './SovereignAgentJobTruthCard';

describe('SovereignAgentJobTruthCard', () => {
  it('does not show Draft PR ready for completed job without draftPrUrl', () => {
    render(<SovereignAgentJobTruthCard job={{ status: 'completed', changedFiles: [], events: [] }} />);

    expect(screen.getAllByText('Blockiert').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/keine Draft-PR-URL liegt vor/i)).toBeDefined();
    expect(screen.queryByRole('button', { name: /Draft PR öffnen/i })).toBeNull();
    expect(screen.getByText('Sovereign Agent Job')).toBeDefined();
  });

  it('shows Draft PR ready only when completed job includes draftPrUrl evidence', () => {
    render(<SovereignAgentJobTruthCard job={{ status: 'completed', changedFiles: ['README.md'], draftPrUrl: 'https://github.com/o/r/pull/1', events: [] }} />);

    expect(screen.getAllByText('Draft PR bereit').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/keine Draft-PR-URL liegt vor/i)).toBeNull();
  });
});
