import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type {
  SovereignAgentJobSnapshot,
  SovereignLiveProjection,
  SovereignLiveProjectionKind,
} from '../runtime/sovereignAgentRuntime';
import { LiveWorkspaceMonitor } from './LiveWorkspaceMonitor';

function projection(
  kind: SovereignLiveProjectionKind,
  overrides: Partial<SovereignLiveProjection> = {},
): SovereignLiveProjection {
  const suffix = kind.toLowerCase().replace('_', '-');
  return {
    projectionId: `visual-${suffix}`,
    eventId: `visual-${suffix}`,
    sessionId: 'livews-1234567890abcdef12345678',
    sessionBindingHash: 'a'.repeat(64),
    attemptId: 'attempt-current',
    runId: 'run-1',
    taskId: 'task-1',
    jobId: 'job-1',
    workspaceId: 'workspace-current',
    actionId: `action-${suffix}`,
    sourceKind: kind === 'TERMINAL' ? 'PROCESS' : kind === 'BROWSER' ? 'PLAYWRIGHT' : 'REPOSITORY',
    projectionKind: kind,
    projectionState: 'REQUESTED',
    repositoryHead: 'b'.repeat(40),
    sourceReceiptRef: 'c'.repeat(64),
    sourceIdentityHash: 'd'.repeat(64),
    payload: {},
    projectionHash: 'e'.repeat(64),
    authoritative: false,
    claim: 'OBSERVED',
    ...overrides,
  };
}

function job(overrides: Partial<SovereignAgentJobSnapshot> = {}): SovereignAgentJobSnapshot {
  return {
    jobId: 'job-1',
    workspaceId: 'workspace-current',
    status: 'running',
    changedFiles: [],
    events: [],
    ...overrides,
  };
}

describe('LiveWorkspaceMonitor', () => {
  it('renders only the latest session/attempt/workspace binding and defaults to its newest pane', () => {
    const old = projection('TERMINAL', {
      projectionId: 'visual-old',
      eventId: 'visual-old',
      sessionBindingHash: '1'.repeat(64),
      attemptId: 'attempt-old',
      workspaceId: 'workspace-old',
      payload: { chunk: 'old-binding-output' },
    });
    const editor = projection('IDE_FILE', {
      payload: { path: 'src/App.tsx', contentSha256: 'f'.repeat(64), mode: 'read' },
    });
    const terminal = projection('TERMINAL', {
      projectionId: 'visual-current-terminal',
      eventId: 'visual-current-terminal',
      payload: { chunk: 'new-binding-output', processState: 'EXITED', exitCode: 0 },
    });

    render(<LiveWorkspaceMonitor projections={[old, editor, terminal]} job={job()} />);

    expect(screen.getByTestId('live-workspace-monitor')).toHaveAttribute(
      'data-binding-key',
      `${'a'.repeat(64)}:attempt-current:workspace-current`,
    );
    expect(screen.getByRole('tab', { name: /Terminal/i })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('new-binding-output')).toBeInTheDocument();
    expect(screen.queryByText('old-binding-output')).not.toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders only allowlisted editor fields and never dumps arbitrary payload content', () => {
    const editor = projection('IDE_FILE', {
      payload: {
        path: 'src/features/product/runtime/sovereignEngineBoundary.ts',
        mode: 'read',
        contentSha256: '9'.repeat(64),
        rawSource: 'DO-NOT-RENDER-RAW-SOURCE',
        internalMaterial: 'DO-NOT-RENDER-INTERNAL-MATERIAL',
      },
    });

    const { container } = render(<LiveWorkspaceMonitor projections={[editor]} job={job()} />);

    expect(screen.getAllByText('src/features/product/runtime/sovereignEngineBoundary.ts').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/999999999999999999…/)).toBeInTheDocument();
    expect(container.textContent).not.toContain('DO-NOT-RENDER-RAW-SOURCE');
    expect(container.textContent).not.toContain('DO-NOT-RENDER-INTERNAL-MATERIAL');
    expect(screen.getByText(/Dateiinhalte werden hier nicht erfunden/i)).toBeInTheDocument();
  });

  it('shows stale browser observation in text and never upgrades it to runtime truth', () => {
    const browser = projection('BROWSER', {
      projectionState: 'STALE',
      payload: {
        url: 'https://sovereign.example.test/app',
        title: 'Sovereign Runtime',
        frameHash: '7'.repeat(64),
      },
    });

    render(<LiveWorkspaceMonitor projections={[browser]} job={job({ status: 'validating' })} />);

    expect(screen.getByRole('tab', { name: /Browser/i })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByText('Veraltet').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('https://sovereign.example.test/app')).toBeInTheDocument();
    expect(screen.getByText(/Sichtbar auf dem Monitor ≠ Effekt verifiziert/i)).toBeInTheDocument();
    expect(screen.queryByText(/Runtime verifiziert/i)).not.toBeInTheDocument();
  });

  it('keeps the user-selected pane while the same binding receives newer observations', async () => {
    const editor = projection('IDE_FILE', {
      payload: { path: 'src/App.tsx', contentSha256: '1'.repeat(64), mode: 'read' },
    });
    const terminal = projection('TERMINAL', {
      payload: { chunk: 'first terminal observation', exitCode: 0 },
    });
    const { rerender } = render(
      <LiveWorkspaceMonitor projections={[editor, terminal]} job={job()} />,
    );

    fireEvent.click(screen.getByRole('tab', { name: /Editor/i }));
    expect(screen.getByRole('tab', { name: /Editor/i })).toHaveAttribute('aria-selected', 'true');

    rerender(
      <LiveWorkspaceMonitor
        projections={[
          editor,
          terminal,
          projection('TERMINAL', {
            projectionId: 'visual-terminal-newer',
            eventId: 'visual-terminal-newer',
            actionId: 'action-terminal-newer',
            payload: { chunk: 'second terminal observation', exitCode: 1 },
          }),
        ]}
        job={job()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Editor/i })).toHaveAttribute('aria-selected', 'true');
    });
    expect(screen.getAllByText('src/App.tsx').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('second terminal observation')).not.toBeInTheDocument();
  });

  it('resets selection when a new canonical binding replaces the current attempt', async () => {
    const editor = projection('IDE_FILE', {
      payload: { path: 'src/App.tsx', contentSha256: '1'.repeat(64), mode: 'read' },
    });
    const terminal = projection('TERMINAL', {
      payload: { chunk: 'current attempt terminal' },
    });
    const { rerender } = render(
      <LiveWorkspaceMonitor projections={[editor, terminal]} job={job()} />,
    );
    fireEvent.click(screen.getByRole('tab', { name: /Editor/i }));

    const newBrowser = projection('BROWSER', {
      projectionId: 'visual-new-binding',
      eventId: 'visual-new-binding',
      sessionBindingHash: '8'.repeat(64),
      attemptId: 'attempt-next',
      workspaceId: 'workspace-next',
      payload: { url: 'https://next.example.test' },
    });
    rerender(
      <LiveWorkspaceMonitor
        projections={[editor, terminal, newBrowser]}
        job={job({ workspaceId: 'workspace-next' })}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Browser/i })).toHaveAttribute('aria-selected', 'true');
    });
    expect(screen.getByText('https://next.example.test')).toBeInTheDocument();
    expect(screen.queryByText('src/App.tsx')).not.toBeInTheDocument();
  });

  it('preserves upstream redaction markers and keeps terminal claims observational', () => {
    const terminal = projection('TERMINAL', {
      payload: {
        chunk: 'provider output [REDACTED]',
        channel: 'STDOUT',
        processState: 'EXITED',
        exitCode: 0,
        successful: true,
      },
    });
    const { container } = render(<LiveWorkspaceMonitor projections={[terminal]} job={job()} />);

    expect(container.textContent).toContain('[REDACTED]');
    expect(screen.getByText(/Exitcode und Prozessausgabe sind Beobachtungen/i)).toBeInTheDocument();
    expect(screen.queryByText(/Effekt erfolgreich/i)).not.toBeInTheDocument();
  });

  it('provides five explicit 44px monitor tabs and responsive single-column rules', () => {
    const terminal = projection('TERMINAL', { payload: { chunk: 'bounded output' } });
    const { container } = render(<LiveWorkspaceMonitor projections={[terminal]} job={job()} />);
    const tabs = screen.getAllByRole('tab');

    expect(tabs).toHaveLength(5);
    expect(window.getComputedStyle(screen.getByRole('tab', { name: /Terminal/i })).minHeight).toBe('44px');
    expect(screen.getByRole('tab', { name: /Editor/i })).toBeDisabled();
    const styles = Array.from(container.querySelectorAll('style')).map((node) => node.textContent).join('\n');
    expect(styles).toContain('@media (max-width: 840px)');
    expect(styles).toContain('.live-workspace-monitor__layout { grid-template-columns: 1fr; }');
    expect(styles).toContain('@media (max-width: 560px)');
  });

  it('renders an honest empty monitor without simulated work or fabricated projection tabs', () => {
    render(<LiveWorkspaceMonitor projections={[]} job={job()} />);

    expect(screen.getByText('Keine gebundene Monitor-Beobachtung')).toBeInTheDocument();
    expect(screen.getByText(/Es wird keine Aktivität simuliert/i)).toBeInTheDocument();
    for (const tab of screen.getAllByRole('tab')) expect(tab).toBeDisabled();
    expect(screen.getByText('Runtime').parentElement).toHaveTextContent('running');
  });
});
