import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BuilderContainer } from './BuilderContainer';

function baseProps() {
  return {
    mission: 'README + Update History',
    repoReady: true,
    repoReason: 'Repo ready.',
    repoBusy: false,
    runtimeBusy: false,
    isPublishing: false,
    sovereignSummary: 'Package summary',
    sovereignPreview: '{ "ok": true }',
    onMissionChange: vi.fn(),
    onGenerateIdeas: vi.fn(),
    onGenerateErrorWorkflow: vi.fn(),
    onPublishDraftPr: vi.fn(),
  };
}

describe('BuilderContainer', () => {
  it('renders builder state and preview', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.getByTestId('builder-container')).toBeDefined();
    expect(screen.getByText('Package summary')).toBeDefined();
    expect(screen.getByText('Brain preview')).toBeDefined();
  });

  it('emits mission changes and button actions', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.change(screen.getByLabelText(/Builder mission/i), { target: { value: 'New mission' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ideen' }));
    fireEvent.click(screen.getByRole('button', { name: 'Fehler' }));
    fireEvent.click(screen.getByRole('button', { name: /Draft PR erstellen/i }));

    expect(props.onMissionChange).toHaveBeenCalledWith('New mission');
    expect(props.onGenerateIdeas).toHaveBeenCalledOnce();
    expect(props.onGenerateErrorWorkflow).toHaveBeenCalledOnce();
    expect(props.onPublishDraftPr).toHaveBeenCalledOnce();
  });

  it('blocks actions while repo is not ready', () => {
    render(<BuilderContainer {...baseProps()} repoReady={false} />);

    expect(screen.getByRole('button', { name: 'Ideen' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fehler' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Draft PR erstellen/i })).toBeDisabled();
    expect(screen.getByText(/not ready/i)).toBeDefined();
  });

  it('shows publishing label while publishing', () => {
    render(<BuilderContainer {...baseProps()} isPublishing={true} />);

    expect(screen.getByRole('button', { name: /Draft PR läuft/i })).toBeDisabled();
  });
});
