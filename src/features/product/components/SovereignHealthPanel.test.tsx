import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import React from 'react';
import { SovereignHealthPanel } from './SovereignHealthPanel';
import type { SovereignHealthReport } from '../runtime/sovereignHealth';

describe('SovereignHealthPanel', () => {
  const mockReport: SovereignHealthReport = {
    status: 'green',
    criticalRisks: 0,
    totalIssues: 0,
    repairsLogged: 2,
    branchDelta: -1,
    summary: 'Health green: 0 critical risk(s), 0 total issue(s), 2 repair signal(s).',
    recommendations: ['No blocking health issue detected.'],
  };

  it('associates the section with the heading via aria-labelledby', () => {
    render(<SovereignHealthPanel report={mockReport} />);

    const section = screen.getByRole('region', { name: 'Sovereign Health Dashboard' });
    expect(section).toBeInTheDocument();
  });

  it('renders the status badge with status role and correct aria-label and title', () => {
    render(<SovereignHealthPanel report={mockReport} />);

    const statusBadge = screen.getByRole('status');
    expect(statusBadge).toHaveTextContent('green');
    expect(statusBadge).toHaveAttribute('aria-label', 'Sovereign Health Status: green');
    expect(statusBadge).toHaveAttribute('title', 'Sovereign Health Status: green');
  });

  it('renders metric cards as a semantic list of health metrics with correct titles and native text visible to screen readers', () => {
    const reportWithIssues: SovereignHealthReport = {
      status: 'warning',
      criticalRisks: 1,
      totalIssues: 3,
      repairsLogged: 0,
      branchDelta: 0.5,
      summary: 'Health warning: 1 critical risk(s), 3 total issue(s).',
      recommendations: ['Review high-risk paths.'],
    };

    render(<SovereignHealthPanel report={reportWithIssues} />);

    // Unordered list is present with aria-label
    const list = screen.getByRole('list', { name: 'Health Metrics' });
    expect(list).toBeInTheDocument();

    // Get list items
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(4);

    // Critical Risks metric
    const criticalRisksItem = items[0];
    expect(criticalRisksItem).toHaveAttribute('title', 'Critical Risks: 1');
    expect(within(criticalRisksItem).getByText('Critical Risks')).toBeInTheDocument();
    expect(within(criticalRisksItem).getByText('1')).toBeInTheDocument();

    // Total Issues metric
    const totalIssuesItem = items[1];
    expect(totalIssuesItem).toHaveAttribute('title', 'Total Issues: 3');
    expect(within(totalIssuesItem).getByText('Total Issues')).toBeInTheDocument();
    expect(within(totalIssuesItem).getByText('3')).toBeInTheDocument();

    // Repair Signals metric
    const repairsItem = items[2];
    expect(repairsItem).toHaveAttribute('title', 'Repair Signals: 0');
    expect(within(repairsItem).getByText('Repair Signals')).toBeInTheDocument();
    expect(within(repairsItem).getByText('0')).toBeInTheDocument();

    // Branch Delta metric
    const deltaItem = items[3];
    expect(deltaItem).toHaveAttribute('title', 'Branch Delta: +0.5');
    expect(within(deltaItem).getByText('Branch Delta')).toBeInTheDocument();
    expect(within(deltaItem).getByText('+0.5')).toBeInTheDocument();
  });
});
