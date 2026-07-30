import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { WorkflowWatchPanel } from './WorkflowWatchPanel';
import type { WorkflowWatchReport } from '../runtime/workflowWatch';

describe('WorkflowWatchPanel Accessibility and Interaction Enhancements', () => {
  const onWatchMock = vi.fn();

  it('renders blocked state when no report is present and helperText mentions draft pr', () => {
    render(
      <WorkflowWatchPanel
        report={null}
        isWatching={false}
        canWatch={true}
        onWatch={onWatchMock}
      />
    );

    const button = screen.getByRole('button', { name: 'Draft PR zuerst erstellen' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Aktion blockiert: Draft-PR erforderlich');
    expect(button).toHaveTextContent('Draft PR zuerst erstellen');
    expect(screen.getByText('Create a Draft PR first, then watch the commit checks.')).toBeInTheDocument();
  });

  it('renders watching state with Loader2 and updated accessible label', () => {
    const report: WorkflowWatchReport = {
      status: 'pending',
      commitSha: 'abc1234',
      branch: 'feature/new-ui',
      summary: 'Running 3 checks',
      checks: [],
      fixes: [],
    };

    render(
      <WorkflowWatchPanel
        report={report}
        isWatching={true}
        canWatch={true}
        onWatch={onWatchMock}
      />
    );

    const button = screen.getByRole('button', { name: 'Watching...' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Die Überwachung der Commit-Checks läuft aktuell');
    expect(button).toHaveTextContent('Watching...');
  });

  it('allows clicking the watch button in idle state when report is present', () => {
    const report: WorkflowWatchReport = {
      status: 'green',
      commitSha: 'abc1234',
      branch: 'feature/new-ui',
      summary: 'All checks passed',
      checks: [],
      fixes: [],
    };

    render(
      <WorkflowWatchPanel
        report={report}
        isWatching={false}
        canWatch={true}
        onWatch={onWatchMock}
      />
    );

    const button = screen.getByRole('button', { name: 'Watch Commit Checks' });
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute('title', 'Commit-Checks für diesen Draft-PR überwachen');
    expect(button).toHaveTextContent('Watch Commit Checks');

    fireEvent.click(button);
    expect(onWatchMock).toHaveBeenCalledTimes(1);
  });

  it('renders table headers with scope="col" and populates check entries', () => {
    const report: WorkflowWatchReport = {
      status: 'red',
      commitSha: 'abc1234',
      branch: 'feature/new-ui',
      summary: '1 failing check',
      checks: [
        {
          name: 'Build Project',
          status: 'green',
          source: 'GitHub Actions',
          summary: 'Compilation successful',
        },
        {
          name: 'Lint & Audit',
          status: 'red',
          source: 'GitHub Actions',
          summary: 'Failed with 2 warnings',
          url: 'https://github.com/test/repo/actions/runs/12345',
        },
      ],
      fixes: ['Fix lint errors in App.tsx'],
    };

    render(
      <WorkflowWatchPanel
        report={report}
        isWatching={false}
        canWatch={true}
        onWatch={onWatchMock}
      />
    );

    // Verify Scope of table headers
    const headers = screen.getAllByRole('columnheader');
    expect(headers).toHaveLength(4);
    expect(headers[0]).toHaveAttribute('scope', 'col');
    expect(headers[1]).toHaveAttribute('scope', 'col');

    // Verify Check without URL (rendered as static text)
    expect(screen.getByText('Build Project')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Build Project/i })).toBeNull();

    // Verify Check with URL (rendered as accessible external link with title and aria-label)
    const link = screen.getByRole('link', { name: 'GitHub Check Details für Lint & Audit öffnen' });
    expect(link).toHaveAttribute('href', 'https://github.com/test/repo/actions/runs/12345');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('title', 'GitHub Check Details für Lint & Audit in neuem Tab öffnen');

    // Verify next repair ideas block
    expect(screen.getByText('Fix lint errors in App.tsx')).toBeInTheDocument();
  });
});
