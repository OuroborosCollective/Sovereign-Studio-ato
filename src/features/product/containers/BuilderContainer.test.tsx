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
  it('renders the chat-driven ideas factory and preview', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.getByTestId('builder-container')).toBeDefined();
    expect(screen.getByText('Package summary')).toBeDefined();
    expect(screen.getByText('Brain preview')).toBeDefined();
    expect(screen.getByText(/Ideenfabrik/)).toBeDefined();
    expect(screen.getByLabelText(/Ideenfabrik Wunschfeld/i)).toBeDefined();
  });

  it('lets option buttons write into the chat wish field instead of directly replacing the mission', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.click(screen.getByRole('button', { name: 'Runtime härten' }));

    expect(screen.getByLabelText(/Ideenfabrik Wunschfeld/i)).toHaveValue(expect.stringContaining('Runtime-Checks'));
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it('analyzes the chat wish into a guarded executable mission', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.change(screen.getByLabelText(/Ideenfabrik Wunschfeld/i), {
      target: { value: 'Bitte mobile UX verbessern und Log direkt sichtbar machen.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Vorschlag analysieren' }));

    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Ideenfabrik Auftrag'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('mobile UX verbessern'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Repo-Snapshot ist geladen'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Keine Mock-, Stub- oder Facade-Live-Pfade'));
  });

  it('keeps the production action wired to the builder generation flow', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.click(screen.getByRole('button', { name: 'Auftrag in Produktion geben' }));
    fireEvent.click(screen.getByRole('button', { name: 'Fehlerlog reparieren' }));
    fireEvent.click(screen.getByRole('button', { name: /Draft PR erstellen/i }));

    expect(props.onGenerateIdeas).toHaveBeenCalledOnce();
    expect(props.onGenerateErrorWorkflow).toHaveBeenCalledOnce();
    expect(props.onPublishDraftPr).toHaveBeenCalledOnce();
  });

  it('emits direct mission changes from the analyzed mission field', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.change(screen.getByLabelText(/Builder mission/i), { target: { value: 'New mission' } });

    expect(props.onMissionChange).toHaveBeenCalledWith('New mission');
  });

  it('blocks production actions while repo is not ready', () => {
    render(<BuilderContainer {...baseProps()} repoReady={false} />);

    expect(screen.getByRole('button', { name: 'Auftrag in Produktion geben' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fehlerlog reparieren' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Draft PR erstellen/i })).toBeDisabled();
    expect(screen.getByText(/not ready/i)).toBeDefined();
  });

  it('shows publishing label while publishing', () => {
    render(<BuilderContainer {...baseProps()} isPublishing={true} />);

    expect(screen.getByRole('button', { name: /Draft PR läuft/i })).toBeDisabled();
  });
});
