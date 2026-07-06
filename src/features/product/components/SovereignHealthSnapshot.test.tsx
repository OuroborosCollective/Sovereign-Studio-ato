import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import {
  SovereignHealthSnapshot,
  SovereignHealthDot,
  SovereignSessionBadge,
} from './SovereignHealthSnapshot';
import type { SovereignIntelligenceStats } from '../runtime/sovereignRuntimeIntelligenceIntegration';

describe('SovereignHealthSnapshot', () => {
  const mockStats: SovereignIntelligenceStats = {
    predictive: {
      active: true,
      nodeCount: 10,
      patternCount: 5,
      avgConfidence: 0.78,
    },
    learning: {
      totalSignals: 100,
      successCount: 75,
      failureCount: 25,
      successRate: 75,
    },
  };

  it('renders compact snapshot', () => {
    render(<SovereignHealthSnapshot stats={mockStats} />);

    expect(screen.getByTestId('health-snapshot-compact')).toBeInTheDocument();
    expect(screen.getByText(/Intel/)).toBeInTheDocument();
    expect(screen.getByText(/Nodes/)).toBeInTheDocument();
    expect(screen.getByText(/Sig/)).toBeInTheDocument();
  });

  it('renders detailed snapshot', () => {
    render(<SovereignHealthSnapshot stats={mockStats} showDetails />);

    expect(screen.getByTestId('health-snapshot-detailed')).toBeInTheDocument();
    expect(screen.getByText(/Predictive/)).toBeInTheDocument();
    expect(screen.getByText(/Learning/)).toBeInTheDocument();
  });

  it('shows inactive indicator when no active stats', () => {
    const emptyStats: SovereignIntelligenceStats = {
      predictive: {
        active: false,
        nodeCount: 0,
        patternCount: 0,
        avgConfidence: 0,
      },
      learning: {
        totalSignals: 0,
        successCount: 0,
        failureCount: 0,
        successRate: 0,
      },
    };

    render(<SovereignHealthSnapshot stats={emptyStats} />);
    // Shows inactive indicator even when no active stats
    expect(screen.getByText(/⚪ Intel/)).toBeInTheDocument();
  });
});

describe('SovereignHealthDot', () => {
  it('renders healthy dot', () => {
    render(<SovereignHealthDot health="healthy" />);
    expect(screen.getByTestId('health-dot')).toBeInTheDocument();
  });

  it('renders warning dot', () => {
    render(<SovereignHealthDot health="warning" />);
    expect(screen.getByTestId('health-dot')).toBeInTheDocument();
  });

  it('renders critical dot', () => {
    render(<SovereignHealthDot health="critical" />);
    expect(screen.getByTestId('health-dot')).toBeInTheDocument();
  });
});

describe('SovereignSessionBadge', () => {
  it('renders idle badge', () => {
    render(<SovereignSessionBadge status="idle" />);
    expect(screen.getByText(/Idle/)).toBeInTheDocument();
  });

  it('renders running badge', () => {
    render(<SovereignSessionBadge status="running" stepCount={3} />);
    expect(screen.getByText(/Active/)).toBeInTheDocument();
    expect(screen.getByText(/3 steps/)).toBeInTheDocument();
  });

  it('renders blocked badge with blocker count', () => {
    render(<SovereignSessionBadge status="blocked" blockerCount={2} />);
    expect(screen.getByText(/Blocked/)).toBeInTheDocument();
    expect(screen.getByText(/2 blockers/)).toBeInTheDocument();
  });

  it('renders finished badge', () => {
    render(<SovereignSessionBadge status="finished" stepCount={5} />);
    expect(screen.getByText(/Done/)).toBeInTheDocument();
  });

  it('renders error badge', () => {
    render(<SovereignSessionBadge status="error" />);
    expect(screen.getByText(/Error/)).toBeInTheDocument();
  });
});
