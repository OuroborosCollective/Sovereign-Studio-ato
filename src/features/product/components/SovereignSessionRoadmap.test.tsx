import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import {
  SovereignSessionRoadmap,
  extractPlanProgress,
  formatNextAllowedAction,
  type SovereignPlanProgress,
} from './SovereignSessionRoadmap';
import type { SovereignExecutionSession } from '../runtime/sovereignExecutionSessionRuntime';

function createMockSession(overrides: Partial<SovereignExecutionSession> = {}): SovereignExecutionSession {
  return {
    id: 'test-session',
    request: 'Test request',
    status: 'running',
    plan: {
      id: 'plan-1',
      title: 'Test Plan',
      steps: [
        {
          id: 'step-1',
          title: 'Schritt 1',
          status: 'completed' as const,
          notes: [],
          artifacts: [],
          updatedAt: Date.now(),
        },
        {
          id: 'step-2',
          title: 'Schritt 2',
          status: 'in_progress' as const,
          notes: [],
          artifacts: [],
          updatedAt: Date.now(),
        },
        {
          id: 'step-3',
          title: 'Schritt 3',
          status: 'not_started' as const,
          notes: [],
          artifacts: [],
          updatedAt: Date.now(),
        },
      ],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    },
    observations: [],
    currentStepId: 'step-2',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    ...overrides,
  };
}

describe('SovereignSessionRoadmap', () => {
  it('renders empty state when no session', () => {
    render(
      <SovereignSessionRoadmap
        session={null}
        progress={{ completed: 0, blocked: 0, total: 0, currentStepId: null, nextStepId: null }}
        health="healthy"
      />
    );

    expect(screen.getByText(/Keine aktive Session/)).toBeInTheDocument();
  });

  it('renders compact view', () => {
    const session = createMockSession();
    const progress: SovereignPlanProgress = {
      completed: 1,
      blocked: 0,
      total: 3,
      currentStepId: 'step-2',
      nextStepId: 'step-3',
    };

    render(
      <SovereignSessionRoadmap
        session={session}
        progress={progress}
        health="healthy"
        compact
      />
    );

    expect(screen.getByTestId('roadmap-compact')).toBeInTheDocument();
    expect(screen.getByText('1/3')).toBeInTheDocument();
  });

  it('renders full view with steps', () => {
    const session = createMockSession();
    const progress: SovereignPlanProgress = {
      completed: 1,
      blocked: 0,
      total: 3,
      currentStepId: 'step-2',
      nextStepId: 'step-3',
    };

    render(
      <SovereignSessionRoadmap
        session={session}
        progress={progress}
        health="healthy"
      />
    );

    expect(screen.getByTestId('roadmap-full')).toBeInTheDocument();
    expect(screen.getByText(/Test Plan/)).toBeInTheDocument();
    expect(screen.getByText('Schritt 1')).toBeInTheDocument();
    expect(screen.getByText('Schritt 2')).toBeInTheDocument();
    expect(screen.getByText('Schritt 3')).toBeInTheDocument();
  });

  it('shows blocker count in compact view', () => {
    const session = createMockSession();
    const progress: SovereignPlanProgress = {
      completed: 1,
      blocked: 1,
      total: 3,
      currentStepId: 'step-2',
      nextStepId: 'step-3',
    };

    render(
      <SovereignSessionRoadmap
        session={session}
        progress={progress}
        health="warning"
        compact
      />
    );

    expect(screen.getByText(/1 blockiert/)).toBeInTheDocument();
  });

  it('shows next allowed action', () => {
    const session = createMockSession();
    const progress: SovereignPlanProgress = {
      completed: 1,
      blocked: 0,
      total: 3,
      currentStepId: 'step-2',
      nextStepId: 'step-3',
    };

    render(
      <SovereignSessionRoadmap
        session={session}
        progress={progress}
        health="healthy"
        nextAllowedAction="Fortsetzen"
      />
    );

    expect(screen.getByText(/→ Fortsetzen/)).toBeInTheDocument();
  });
});

describe('extractPlanProgress', () => {
  it('extracts progress from session', () => {
    const session = createMockSession();
    const progress = extractPlanProgress(session);

    expect(progress).not.toBeNull();
    expect(progress!.completed).toBe(1);
    expect(progress!.blocked).toBe(0);
    expect(progress!.total).toBe(3);
    expect(progress!.currentStepId).toBe('step-2');
  });

  it('returns null for no session', () => {
    const progress = extractPlanProgress(null);
    expect(progress).toBeNull();
  });

  it('counts blocked steps', () => {
    const session = createMockSession({
      plan: {
        ...createMockSession().plan!,
        steps: [
          {
            id: 'step-1',
            title: 'Step 1',
            status: 'completed' as const,
            notes: [],
            artifacts: [],
            updatedAt: Date.now(),
          },
          {
            id: 'step-2',
            title: 'Step 2',
            status: 'blocked' as const,
            notes: [],
            artifacts: [],
            blocker: 'missing_token',
            updatedAt: Date.now(),
          },
        ],
      },
    });

    const progress = extractPlanProgress(session);
    expect(progress!.blocked).toBe(1);
  });
});

describe('formatNextAllowedAction', () => {
  it('formats known actions', () => {
    expect(formatNextAllowedAction('resolve_blocker')).toBe('Blocker lösen');
    expect(formatNextAllowedAction('continue')).toBe('Fortsetzen');
    expect(formatNextAllowedAction('finish')).toBe('Abschließen');
  });

  it('formats unknown actions', () => {
    expect(formatNextAllowedAction('custom-action')).toBe('Nächster: custom-action');
  });

  it('returns undefined for null', () => {
    expect(formatNextAllowedAction(null)).toBeUndefined();
  });
});
