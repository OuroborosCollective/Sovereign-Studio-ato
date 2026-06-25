import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BuilderContainer } from './BuilderContainer';

function baseProps() {
  return {
    mission: 'Bitte mobile UX verbessern und Log direkt sichtbar machen.',
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
  it('renders no-code chat shell with empty state', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.getByTestId('builder-container')).toBeDefined();
    expect(screen.getByText('Sovereign Chat')).toBeDefined();
    expect(screen.getByText("Let's start building!")).toBeDefined();
    expect(screen.getByPlaceholderText('What do you want to build?')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Neue Chat Aufgabe' })).toBeDefined();
    expect(screen.getByLabelText('Sovereign Arbeitsbereiche')).toBeDefined();
  });

  it('lets option buttons write into the chat wish field only', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.click(screen.getByRole('button', { name: 'Runtime härten' }));

    const wishField = screen.getByPlaceholderText('What do you want to build?') as HTMLTextAreaElement;
    expect(wishField.value).toContain('Prüfe den schwächsten Ablauf');
    expect(wishField.value).toContain('Runtime-Checks');
    expect(wishField.value).toContain('ohne');
    expect(wishField.value).toContain('Facade-Live-Pfade');
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it('prepares mission when clicking Auftrag vorbereiten', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.change(screen.getByPlaceholderText('What do you want to build?'), {
      target: { value: 'Bitte mobile UX verbessern.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Auftrag vorbereiten/i }));

    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Ideenfabrik Auftrag'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('mobile UX verbessern'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Repo-Snapshot ist geladen'));
  });

  it('syncs externally adopted insight missions into the wish field', () => {
    const props = baseProps();
    const { rerender } = render(<BuilderContainer {...props} mission="" />);

    const adoptedMission = [
      'Ideenfabrik Auftrag:',
      'Verbessere mobile UX und Log-Fenster.',
      '',
      'Repository-Kontext:',
      'Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.',
      '',
      'Umsetzung:',
      '- Erzeuge echte Änderungen im passenden Codepfad.',
    ].join('\n');
    rerender(<BuilderContainer {...props} mission={adoptedMission} />);

    const wishField = screen.getByPlaceholderText('What do you want to build?') as HTMLTextAreaElement;
    expect(wishField.value).toBe('Verbessere mobile UX und Log-Fenster.');
  });

  it('does not duplicate an already analyzed mission', () => {
    const props = baseProps();
    const analyzedMission = [
      'Ideenfabrik Auftrag:',
      'Ideenfabrik Auftrag:',
      'Verbessere mobile UX und Log-Fenster.',
      '',
      'Repository-Kontext:',
      'Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.',
      '',
      'Umsetzung:',
      '- Erzeuge echte Änderungen im passenden Codepfad.',
      '',
      'Repository-Kontext:',
      'Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.',
      '',
      'Umsetzung:',
      '- Erzeuge echte Änderungen im passenden Codepfad.',
    ].join('\n');

    render(<BuilderContainer {...props} mission={analyzedMission} />);
    fireEvent.click(screen.getByRole('button', { name: /Auftrag vorbereiten/i }));

    const emittedMission = props.onMissionChange.mock.calls[0][0] as string;
    expect(emittedMission.match(/Ideenfabrik Auftrag:/g)).toHaveLength(1);
    expect(emittedMission.match(/Repository-Kontext:/g)).toHaveLength(1);
    expect(emittedMission).toContain('Verbessere mobile UX und Log-Fenster.');
  });

  it('keeps old tools hidden as inspector in details', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    // Open the details element
    const details = document.querySelector('details');
    expect(details).not.toBeNull();
    fireEvent.click(details!.querySelector('summary')!);

    fireEvent.click(screen.getByRole('button', { name: 'Interne Paketprüfung starten' }));
    fireEvent.click(screen.getByRole('button', { name: 'Fehleranalyse' }));
    fireEvent.click(screen.getByRole('button', { name: /Draft PR/i }));

    expect(props.onGenerateIdeas).toHaveBeenCalledOnce();
    expect(props.onGenerateErrorWorkflow).toHaveBeenCalledOnce();
    expect(props.onPublishDraftPr).toHaveBeenCalledOnce();
  });

  it('starts agent when submitting with repoReady and openhandsReady', () => {
    const props = {
      ...baseProps(),
      openhandsReady: true,
      onStartOpenHands: vi.fn(),
    };
    render(<BuilderContainer {...props} />);

    fireEvent.change(screen.getByPlaceholderText('What do you want to build?'), {
      target: { value: 'Bau mir ein cooles Feature' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Agent starten' }));

    expect(props.onStartOpenHands).toHaveBeenCalledOnce();
    expect(props.onStartOpenHands.mock.calls[0][0]).toContain('Ideenfabrik Auftrag');
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
  });

  it('blocks agent start when repo not ready', () => {
    render(<BuilderContainer {...baseProps()} repoReady={false} />);

    expect(screen.getByRole('button', { name: 'Agent starten' })).toBeDisabled();
    expect(screen.getByText('Repo fehlt')).toBeDefined();
  });

  it('keeps output as plain hints and not result cards', () => {
    render(
      <BuilderContainer
        {...baseProps()}
        openhandsReady
        openhandsJob={{
          status: 'running',
          openHandsId: 'conv_123',
          changedFiles: ['src/App.tsx'],
          events: [],
        }}
      />
    );

    expect(screen.getByTestId('sovereign-chat-outcome-hints')).toBeDefined();
    expect(screen.getByText(/OpenHands Runtime-ID/)).toBeDefined();
    expect(screen.getByText(/1 Datei/)).toBeDefined();
    expect(screen.queryByLabelText(/Karten/i)).toBeNull();
  });

  it('shows workbench tabs and help text', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.getByRole('button', { name: /Planner/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Changes/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Code/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Terminal/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Browser/i })).toBeDefined();
  });

  it('shows publishing label while publishing', () => {
    render(<BuilderContainer {...baseProps()} isPublishing={true} />);

    expect(screen.getByRole('button', { name: /Draft PR läuft/i })).toBeDisabled();
  });
});
