import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ActionSuggestionStrip } from './ActionSuggestionStrip';
import { SOVEREIGN_PRESET_ACTIONS } from '../runtime/sovereignPresetActionRuntime';

describe('ActionSuggestionStrip', () => {
  it('renders guided actions even when repo is missing', () => {
    render(
      <ActionSuggestionStrip
        actions={SOVEREIGN_PRESET_ACTIONS}
        repoReady={false}
        githubWriteReady={false}
        agentReady={false}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByTestId('sovereign-action-suggestion-strip')).toBeInTheDocument();
    expect(screen.getByText('Feature-Vorschläge aus Architektur')).toBeInTheDocument();
    expect(screen.getByText('README & Docs aktualisieren')).toBeInTheDocument();
    expect(screen.getByText('Repo fehlt')).toBeInTheDocument();
  });

  it('calls onSelect with the runtime action id', () => {
    const onSelect = vi.fn();
    render(
      <ActionSuggestionStrip
        actions={SOVEREIGN_PRESET_ACTIONS}
        repoReady
        githubWriteReady
        agentReady={false}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Feature-Vorschläge aus Architektur/i }));
    expect(onSelect).toHaveBeenCalledWith('architecture_feature_suggestions');
  });

  it('links section landmark to title and provides focus visible styling and native tooltips', () => {
    render(
      <ActionSuggestionStrip
        actions={SOVEREIGN_PRESET_ACTIONS}
        repoReady={true}
        githubWriteReady={true}
        agentReady={true}
        onSelect={vi.fn()}
      />,
    );

    const section = screen.getByRole('region', { name: 'Geführte Repo-Aktionen' });
    expect(section).toBeInTheDocument();
    expect(section).toHaveAttribute('aria-labelledby', 'action-suggestion-strip-title');

    const list = screen.getByRole('list', { name: 'Geführte Repo-Aktionen' });
    expect(list).toBeInTheDocument();

    const button = screen.getByRole('button', { name: /Feature-Vorschläge aus Architektur/i });
    expect(button).toHaveClass('focus-visible:ring-2');
    expect(button).toHaveAttribute('title');
    expect(button.getAttribute('title')).toContain('Feature-Vorschläge aus Architektur');
  });
});
