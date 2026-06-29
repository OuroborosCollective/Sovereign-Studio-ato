import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BuilderContainer } from './BuilderContainer';

function baseProps() {
  return {
    mission: 'Test mission',
    repoReady: true,
    repoReason: 'Repo ready.',
    repoBusy: false,
    runtimeBusy: false,
    isPublishing: false,
    sovereignSummary: 'Summary',
    sovereignPreview: '',
    onMissionChange: vi.fn(),
    onGenerateIdeas: vi.fn(),
    onGenerateErrorWorkflow: vi.fn(),
    onPublishDraftPr: vi.fn(),
  };
}

describe('BuilderContainer Accessibility', () => {
  it('has correct accessibility attributes in TopBar', () => {
    render(<BuilderContainer {...baseProps()} />);

    const menuBtn = screen.getByRole('button', { name: 'Menü' });
    expect(menuBtn).toHaveAttribute('title', 'Menü');

    const repoLabel = screen.getByTitle('Repo ✓');
    expect(repoLabel).toBeDefined();

    const rtBtn = screen.getByRole('button', { name: 'Runtime Quelle' });
    expect(rtBtn).toHaveAttribute('title', 'Runtime Quelle');

    const panelToggle = screen.getByRole('button', { name: 'Status-Panel öffnen' });
    expect(panelToggle).toHaveAttribute('title', 'Status-Panel öffnen');
  });

  it('updates Panel Toggle accessibility attributes when clicked', () => {
    render(<BuilderContainer {...baseProps()} />);

    const panelToggle = screen.getByRole('button', { name: 'Status-Panel öffnen' });
    fireEvent.click(panelToggle);

    expect(screen.getByRole('button', { name: 'Status-Panel schließen' })).toHaveAttribute('title', 'Status-Panel schließen');
  });

  it('has correct accessibility attributes in SideDrawer', () => {
    render(<BuilderContainer {...baseProps()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Menü' }));

    const closeBtn = screen.getByRole('button', { name: 'Schließen' });
    expect(closeBtn).toHaveAttribute('title', 'Schließen');
  });

  it('has correct accessibility attributes in Composer', () => {
    render(<BuilderContainer {...baseProps()} />);

    const sendBtn = screen.getByRole('button', { name: 'Senden' });
    expect(sendBtn).toHaveAttribute('title', 'Senden');
  });

  it('has correct accessibility attributes in ThinkingDots', () => {
    render(<BuilderContainer {...baseProps()} repoBusy={true} />);

    const thinkingDots = screen.getByRole('status');
    expect(thinkingDots).toHaveAttribute('aria-label', 'Agent arbeitet...');
  });
});
