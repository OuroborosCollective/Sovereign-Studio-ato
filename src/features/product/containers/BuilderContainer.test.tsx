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

function chatField(): HTMLTextAreaElement {
  return screen.getByLabelText(/Sovereign Chat Eingabe/i) as HTMLTextAreaElement;
}

describe('BuilderContainer', () => {
  it('renders the fixed DevChat shell structure', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.getByTestId('builder-container')).toHaveAttribute('data-layout', 'devchat-runtime-shell');
    expect(screen.getByTestId('sovereign-devchat-statusbar')).toBeDefined();
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(screen.getByPlaceholderText('Nachricht, Planung, Feature…')).toBeDefined();
    expect(screen.getByLabelText('Sovereign Menü öffnen')).toBeDefined();
    expect(screen.getByText('Sovereign Chat')).toBeDefined();
    expect(screen.getByText('OpenHands Runtime')).toBeDefined();
  });

  it('keeps DevChat content as runtime-derived messages, not demo flow', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.getByText(/Repo-Snapshot verbunden/)).toBeDefined();
    expect(screen.getByText('Bitte mobile UX verbessern und Log direkt sichtbar machen.')).toBeDefined();
    expect(screen.getByText('Package summary')).toBeDefined();
    expect(screen.queryByText(/AutoSwitchOrchestrator/)).toBeNull();
    expect(screen.queryByText(/simulate/i)).toBeNull();
  });

  it('shows suggestions only in empty chat state and writes them into the input', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} mission="" />);

    expect(screen.getByText("Let's start building!")).toBeDefined();
    fireEvent.click(screen.getByText('Runtime härten'));

    expect(chatField().value).toContain('Prüfe den schwächsten Ablauf');
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it('prepares a guarded executable mission when the agent is not start-ready', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} openhandsReady={false} />);

    fireEvent.change(chatField(), {
      target: { value: 'Bitte mobile UX verbessern und Log direkt sichtbar machen.' },
    });
    fireEvent.submit(document.querySelector('form') as HTMLFormElement);

    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Ideenfabrik Auftrag'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('mobile UX verbessern'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Repo-Snapshot ist geladen'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Facade-Live-Pfade'));
  });

  it('syncs externally adopted insight missions into the chat input', () => {
    const props = baseProps();
    const { rerender } = render(<BuilderContainer {...props} mission="README + Update History" />);

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

    expect(chatField().value).toBe('Verbessere mobile UX und Log-Fenster.');
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
    fireEvent.submit(document.querySelector('form') as HTMLFormElement);

    const emittedMission = props.onMissionChange.mock.calls[0][0] as string;
    expect(emittedMission.match(/Ideenfabrik Auftrag:/g)).toHaveLength(1);
    expect(emittedMission.match(/Repository-Kontext:/g)).toHaveLength(1);
    expect(emittedMission).toContain('Verbessere mobile UX und Log-Fenster.');
  });

  it('opens the DevChat side menu as overlay without changing the shell structure', () => {
    render(<BuilderContainer {...baseProps()} />);

    fireEvent.click(screen.getByLabelText('Sovereign Menü öffnen'));

    expect(screen.getByTestId('sovereign-devchat-side-menu')).toBeDefined();
    expect(screen.getByText('Sovereign Studio')).toBeDefined();
    expect(screen.getAllByText('Repo laden').length).toBeGreaterThanOrEqual(1);
  });

  it('opens runtime source sheet from the status bar', () => {
    render(<BuilderContainer {...baseProps()} openhandsReady />);

    fireEvent.click(screen.getByText('OpenHands'));

    expect(screen.getByText('Runtime Quelle')).toBeDefined();
    expect(screen.getByText('Echte Agent-Runtime verbunden')).toBeDefined();
    expect(screen.getByText('Repo-Kontext geladen')).toBeDefined();
  });

  it('starts the external agent from the chat mission when ready', () => {
    const props = {
      ...baseProps(),
      openhandsReady: true,
      onStartOpenHands: vi.fn(),
    };
    render(<BuilderContainer {...props} />);

    fireEvent.change(chatField(), { target: { value: 'Test mission' } });
    fireEvent.submit(document.querySelector('form') as HTMLFormElement);

    expect(props.onStartOpenHands).toHaveBeenCalledOnce();
    expect(props.onStartOpenHands.mock.calls[0][0]).toContain('Ideenfabrik Auftrag');
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
  });

  it('shows repo status when not ready and blocks direct send', () => {
    render(<BuilderContainer {...baseProps()} repoReady={false} openhandsReady />);

    expect(screen.getByText(/Repo fehlt/)).toBeDefined();
    expect(screen.getByRole('button', { name: 'Agent starten' })).toBeDisabled();
  });

  it('keeps OpenHands output as plain hints and not result cards', () => {
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
      />,
    );

    expect(screen.getByTestId('sovereign-chat-outcome-hints')).toBeDefined();
    expect(screen.getByText(/OpenHands Runtime-ID/)).toBeDefined();
    expect(screen.getByText(/1 Datei/)).toBeDefined();
    expect(screen.queryByLabelText(/Karten/i)).toBeNull();
  });

  it('shows publishing state correctly', () => {
    render(<BuilderContainer {...baseProps()} isPublishing />);

    expect(screen.getByRole('button', { name: 'Agent starten' })).toBeDisabled();
  });
});
