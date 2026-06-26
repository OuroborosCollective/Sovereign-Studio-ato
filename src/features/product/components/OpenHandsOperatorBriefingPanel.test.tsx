import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { OpenHandsOperatorBriefingPanel } from './OpenHandsOperatorBriefingPanel';

const readyConfig = {
  enabled: true,
  deploymentMode: 'external-agent-runtime' as const,
  agentApiUrl: 'https://openhands.example.com/api',
  adminConsoleUrl: 'https://openhands.example.com/admin',
  ready: true,
  reason: 'Ready.',
};

const disabledConfig = {
  enabled: false,
  deploymentMode: 'disabled' as const,
  agentApiUrl: '',
  adminConsoleUrl: '',
  ready: false,
  reason: 'OpenHands is disabled.',
};

describe('OpenHandsOperatorBriefingPanel', () => {
  it('renders without crashing when ready', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.getByRole('region', { name: /operator-briefing/i })).toBeInTheDocument();
  });

  it('renders without crashing when disabled', () => {
    render(<OpenHandsOperatorBriefingPanel config={disabledConfig} />);
    expect(screen.getByRole('region', { name: /operator-briefing/i })).toBeInTheDocument();
  });

  it('shows header with briefing summary', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.getByText('OpenHands Operator-Briefing')).toBeInTheDocument();
    expect(screen.getByText(/vollständig konfiguriert/)).toBeInTheDocument();
  });

  it('shows blocked warning when config is not ready', () => {
    render(<OpenHandsOperatorBriefingPanel config={disabledConfig} />);
    expect(screen.getByText(/blockierende/)).toBeInTheDocument();
  });

  it('renders all 5 sections', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.getByText('OpenHands starten')).toBeInTheDocument();
    expect(screen.getByText('Aktive Workflows')).toBeInTheDocument();
    expect(screen.getByText('Lauf-Ergebnis')).toBeInTheDocument();
    expect(screen.getByText('Konfiguration prüfen')).toBeInTheDocument();
    expect(screen.getByText('Fehlende Secrets/Settings')).toBeInTheDocument();
  });

  it('shows trigger labels', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.getByText(/openhands-review/)).toBeInTheDocument();
    expect(screen.getByText('/openhands')).toBeInTheDocument();
  });

  it('shows comment marker', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.getByText('Kommentar-Marker')).toBeInTheDocument();
  });

  it('shows blocked items with correct status', () => {
    render(<OpenHandsOperatorBriefingPanel config={disabledConfig} />);
    expect(screen.getByText('Agent API URL')).toBeInTheDocument();
    expect(screen.getAllByText('Blockiert')).toHaveLength(2); // Agent API and ready status
  });

  it('can expand and collapse sections', async () => {
    const user = userEvent.setup();
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);

    // Click to collapse first section
    const firstSection = screen.getByRole('button', { name: /openhands starten/i });
    await user.click(firstSection);
    
    // Section should be collapsed
    expect(screen.queryByText('Start-Labels')).not.toBeVisible();

    // Click to expand again
    await user.click(firstSection);
    expect(screen.getByText('Start-Labels')).toBeVisible();
  });

  it('shows expand/collapse all button', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.getByText('Alle ausklappen')).toBeInTheDocument();
  });

  it('shows warning badge when warnings exist', () => {
    const configWithWarning = {
      ...readyConfig,
      adminConsoleUrl: '',
    };
    render(<OpenHandsOperatorBriefingPanel config={configWithWarning} />);
    // Should show warnings count badge
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('shows blocked badge when blocked items exist', () => {
    render(<OpenHandsOperatorBriefingPanel config={disabledConfig} />);
    // Should show blocked count badge
    const badges = screen.getAllByText(/\d+/);
    const blockedBadges = badges.filter(b => b.className.includes('bg-red'));
    expect(blockedBadges.length).toBeGreaterThan(0);
  });

  it('shows alert when blocked', () => {
    render(<OpenHandsOperatorBriefingPanel config={disabledConfig} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/kann nicht starten/)).toBeInTheDocument();
  });

  it('does not show alert when ready', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} onClose={onClose} />);
    
    const closeButton = screen.getByRole('button', { name: /briefing schließen/i });
    await user.click(closeButton);
    
    expect(onClose).toHaveBeenCalled();
  });

  it('uses data-testid attribute', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.getByTestId('openhands-operator-briefing')).toBeInTheDocument();
  });

  it('shows Agent API URL value when configured', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    expect(screen.getByText('https://openhands.example.com/api')).toBeInTheDocument();
  });

  it('shows hint text for items', () => {
    render(<OpenHandsOperatorBriefingPanel config={readyConfig} />);
    // Check for hint text in the document
    expect(document.body.textContent).toContain('Ein Label auf ein Issue oder PR setzen');
  });
});