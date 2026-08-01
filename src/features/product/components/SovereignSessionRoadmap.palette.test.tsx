import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { SovereignSessionRoadmap } from './SovereignSessionRoadmap';
import type { SovereignExecutionSession } from '../runtime/sovereignExecutionSessionRuntime';

function createMockSession(): SovereignExecutionSession {
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
          status: 'blocked' as const,
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
  };
}

describe('SovereignSessionRoadmap Accessibility Enhancements', () => {
  it('renders the full step list with list roles and accessible step elements', () => {
    const session = createMockSession();
    const progress = {
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
      />
    );

    // List container check
    const listElement = screen.getByRole('list', { name: 'Plan-Schritte' });
    expect(listElement).toBeInTheDocument();

    // List items checks
    const listItems = screen.getAllByRole('listitem');
    expect(listItems).toHaveLength(3);

    // Step 1: Completed
    const step1 = listItems[0];
    expect(step1).toHaveAttribute('aria-label', 'Abgeschlossen: Schritt 1');
    expect(step1).toHaveAttribute('title', 'Abgeschlossen: Schritt 1');
    expect(step1).not.toHaveAttribute('aria-current');

    // Step 2: In Progress / Current
    const step2 = listItems[1];
    expect(step2).toHaveAttribute('aria-label', 'Aktueller Schritt: Schritt 2');
    expect(step2).toHaveAttribute('title', 'Aktueller Schritt: Schritt 2');
    expect(step2).toHaveAttribute('aria-current', 'step');

    // Step 3: Blocked
    const step3 = listItems[2];
    expect(step3).toHaveAttribute('aria-label', 'Blockiert: Schritt 3');
    expect(step3).toHaveAttribute('title', 'Blockiert: Schritt 3');
    expect(step3).not.toHaveAttribute('aria-current');
  });

  it('renders the compact view with comprehensive accessible tooltip and label attributes', () => {
    const session = createMockSession();
    const progress = {
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

    const compactContainer = screen.getByTestId('roadmap-compact');
    expect(compactContainer).toHaveAttribute(
      'aria-label',
      'Session-Roadmap: 1 von 3 Schritten abgeschlossen. Aktueller Schritt: Schritt 2, 1 blockiert'
    );
    expect(compactContainer).toHaveAttribute(
      'title',
      'Session-Roadmap: 1 von 3 abgeschlossen. Aktueller Schritt: Schritt 2, 1 blockiert'
    );

    // Health indicator status
    const healthIndicator = screen.getByText('⚠');
    expect(healthIndicator).toHaveAttribute('aria-label', 'Status: Warnung');
    expect(healthIndicator).toHaveAttribute('title', 'Status: Warnung');
  });
});
