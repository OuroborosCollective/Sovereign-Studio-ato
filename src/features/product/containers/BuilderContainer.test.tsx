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

    const wishField = screen.getByLabelText(/Ideenfabrik Wunschfeld/i) as HTMLTextAreaElement;
    expect(wishField.value).toContain('Prüfe den schwächsten Ablauf');
    expect(wishField.value).toContain('Runtime-Checks');
    expect(wishField.value).toContain('ohne');
    expect(wishField.value).toContain('Facade-Live-Pfade');
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  it('analyzes the chat wish into a guarded executable mission', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.change(screen.getByLabelText(/Ideenfabrik Wunschfeld/i), {
      target: { value: 'Bitte mobile UX verbessern und Log direkt sichtbar machen.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Auftrag analysieren/i }));

    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Ideenfabrik Auftrag'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('mobile UX verbessern'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Repo-Snapshot ist geladen'));
    expect(props.onMissionChange).toHaveBeenCalledWith(expect.stringContaining('Facade-Live-Pfade'));
  });

  it('syncs externally adopted insight missions into the wish field', () => {
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

    const wishField = screen.getByLabelText(/Ideenfabrik Wunschfeld/i) as HTMLTextAreaElement;
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
    fireEvent.click(screen.getByRole('button', { name: /Auftrag analysieren/i }));

    const emittedMission = props.onMissionChange.mock.calls[0][0] as string;
    expect(emittedMission.match(/Ideenfabrik Auftrag:/g)).toHaveLength(1);
    expect(emittedMission.match(/Repository-Kontext:/g)).toHaveLength(1);
    expect(emittedMission).toContain('Verbessere mobile UX und Log-Fenster.');
  });

  it('keeps the production action wired to the builder generation flow', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.click(screen.getByRole('button', { name: /Auftrag starten/i }));
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

    expect(screen.getByRole('button', { name: /Auftrag starten/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fehlerlog reparieren' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Draft PR erstellen/i })).toBeDisabled();
    expect(screen.getByText(/not ready/i)).toBeDefined();
  });

  it('shows publishing label while publishing', () => {
    render(<BuilderContainer {...baseProps()} isPublishing={true} />);

    expect(screen.getByRole('button', { name: /Draft PR läuft/i })).toBeDisabled();
  });
});
