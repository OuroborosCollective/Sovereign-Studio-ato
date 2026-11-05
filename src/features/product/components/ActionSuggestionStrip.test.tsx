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

  it('renders keyboard-navigable scroll region and accessible focus-visible action buttons', () => {
    render(
      <ActionSuggestionStrip
        actions={SOVEREIGN_PRESET_ACTIONS}
        repoReady
        githubWriteReady
        agentReady
        onSelect={vi.fn()}
      />,
    );

    const scrollRegion = screen.getByRole('region', { name: 'Geführte Aktionen Liste' });
    expect(scrollRegion).toBeInTheDocument();
    expect(scrollRegion).toHaveAttribute('tabIndex', '0');
    expect(scrollRegion).toHaveClass('focus-visible:ring-1');

    const actionButton = screen.getByRole('button', { name: /Feature-Vorschläge aus Architektur/i });
    expect(actionButton).toHaveClass('focus-visible:ring-2');
    expect(actionButton).toHaveClass('hover:border-[#00d9b1]/70');
  });
});
