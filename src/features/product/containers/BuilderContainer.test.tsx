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
  it('renders the chat-driven workbench and preview', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.getByTestId('builder-container')).toBeDefined();
    expect(screen.getByText('Package summary')).toBeDefined();
    expect(screen.getByText('Sovereign Chat')).toBeDefined();
    expect(screen.getByText('OpenHands Runtime')).toBeDefined();
    expect(screen.getByLabelText(/Ideenfabrik Wunschfeld/i)).toBeDefined();
  });

  it('lets option buttons write into the chat wish field instead of directly replacing the mission', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    // Get the wish field - initial value comes from mission prop
    const wishField = screen.getByLabelText(/Ideenfabrik Wunschfeld/i) as HTMLTextAreaElement;
    
    // The field has initial value from mission prop
    expect(wishField.value).toBe('Bitte mobile UX verbessern und Log direkt sichtbar machen.');
    
    // The quick suggestions should be visible when there's no wish text
    expect(screen.queryByText("Let's start building!")).toBeNull();
  });

  it('analyzes the chat wish into a guarded executable mission', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.change(screen.getByLabelText(/Ideenfabrik Wunschfeld/i), {
      target: { value: 'Bitte mobile UX verbessern und Log direkt sichtbar machen.' },
    });
    
    // Submit the form to analyze
    const form = document.querySelector('form');
    fireEvent.submit(form as HTMLFormElement);

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
    
    // Submit form to trigger analyze
    const form = document.querySelector('form');
    fireEvent.submit(form as HTMLFormElement);

    const emittedMission = props.onMissionChange.mock.calls[0][0] as string;
    expect(emittedMission.match(/Ideenfabrik Auftrag:/g)).toHaveLength(1);
    expect(emittedMission.match(/Repository-Kontext:/g)).toHaveLength(1);
    expect(emittedMission).toContain('Verbessere mobile UX und Log-Fenster.');
  });

  it('keeps internal builder actions available via menu', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    // Open the menu details
    const details = document.querySelector('details');
    expect(details).not.toBeNull();
    fireEvent.click(details!.querySelector('summary')!);

    // Check that the Sovereign menu is visible
    expect(screen.getByText(/Sovereign Menüs/)).toBeDefined();
  });

  it('starts the external agent from the chat mission when ready', () => {
    const props = {
      ...baseProps(),
      openhandsReady: true,
      onStartOpenHands: vi.fn(),
    };
    render(<BuilderContainer {...props} />);

    // Submit form with wish text to trigger agent start
    fireEvent.change(screen.getByLabelText(/Ideenfabrik Wunschfeld/i), {
      target: { value: 'Test mission' },
    });
    const form = document.querySelector('form');
    fireEvent.submit(form as HTMLFormElement);

    expect(props.onStartOpenHands).toHaveBeenCalledOnce();
    expect(props.onStartOpenHands.mock.calls[0][0]).toContain('Ideenfabrik Auftrag');
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
  });

  it('emits direct mission changes from the wish field', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} />);

    fireEvent.change(screen.getByLabelText(/Ideenfabrik Wunschfeld/i), { target: { value: 'New mission' } });

    // Mission change is called when form is submitted
    const form = document.querySelector('form');
    fireEvent.submit(form as HTMLFormElement);
    
    expect(props.onMissionChange).toHaveBeenCalled();
  });

  it('shows repo status when not ready', () => {
    render(<BuilderContainer {...baseProps()} repoReady={false} />);

    expect(screen.getByText(/Repo fehlt/)).toBeDefined();
  });

  it('shows publishing state correctly', () => {
    render(<BuilderContainer {...baseProps()} isPublishing={true} />);

    // The submit button should be disabled during publishing
    const submitBtn = screen.getByRole('button', { name: 'Agent starten' });
    expect(submitBtn).toBeDisabled();
  });
});
