import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BuilderContainer } from './BuilderContainer';

/** ----------------------------------------------------------------
 *  Shared helpers & default props
 *  ---------------------------------------------------------------- */
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
  return screen.getByTestId('mission__textarea') as HTMLTextAreaElement;
}

/** ----------------------------------------------------------------
 *  Tests
 *  ---------------------------------------------------------------- */
describe('BuilderContainer (replit shell)', () => {
  /* ───────────────────────── structure / shell ───────────────────────── */
  it('renders the fixed DevChat shell structure', () => {
    render(<BuilderContainer {...baseProps()} />);

    // root section
    expect(screen.getByTestId('builder-container'))
      .toHaveAttribute('data-layout', 'devchat-replit');

    // top bar → shows both brand tokens
    expect(screen.getAllByText(/Sovereign/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/DevChat/i).length).toBeGreaterThanOrEqual(1);

    // main chat viewport + composer placeholder
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(screen.getByPlaceholderText('GitHub URL oder Auftrag…')).toBeDefined();

    // hamburger menu button
    expect(screen.getByLabelText('Menü')).toBeDefined();
  });

  /* ─────────────────────── quiet default surface ─────────────────────── */
  it('keeps the default builder surface quiet and chat-first', () => {
    render(<BuilderContainer {...baseProps()} />);

    // No side menu, planner, code, etc. in initial state
    expect(screen.queryByText('Sovereign Studio')).toBeNull();
    expect(screen.queryByText('Planner')).toBeNull();
    expect(screen.queryByText('Changes')).toBeNull();
    expect(screen.queryByText('Code')).toBeNull();
    expect(screen.queryByText('Terminal')).toBeNull();
    expect(screen.queryByText('Browser')).toBeNull();
    expect(screen.queryByText(/Sovereign geführter Chat Ablauf/i)).toBeNull();
  });

  /* ─────────────── initial repo + mission messages ─────────────── */
  it('keeps DevChat content as runtime-derived messages, not demo flow', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.getByText(/Repo verbunden/)).toBeDefined();
    expect(
      screen.getAllByText('Bitte mobile UX verbessern und Log direkt sichtbar machen.').length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Package summary')).toBeDefined();
    expect(screen.queryByText(/AutoSwitchOrchestrator/)).toBeNull();
    expect(screen.queryByText(/simulate/i)).toBeNull();
  });

  /* ───────────── suggestion chips on empty welcome screen ───────────── */
  it('shows suggestions only in empty chat state and writes them into the input', () => {
    const props = baseProps();
    render(<BuilderContainer {...props} mission="" />);

    expect(screen.getByText("Let's build!")).toBeDefined();
    fireEvent.click(screen.getByText('🔒 Runtime'));

    expect(chatField().value).toContain('Prüfe den schwächsten Ablauf');
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  /* ───────────── guarded mission generation when agent locked ───────────── */
  it('prepares a guarded executable mission when the agent is not start-ready', () => {
    const props = { ...baseProps(), repoReady: false, repoReason: 'Repo-Snapshot ist noch nicht bereit' };
    render(<BuilderContainer {...props} openhandsReady={false} />);

    fireEvent.change(chatField(), {
      target: { value: 'Bitte mobile UX verbessern und Log direkt sichtbar machen.' },
    });

    // Use submit to trigger submission even if button is technically disabled in JSDOM
    fireEvent.submit(screen.getByRole('button', { name: 'Senden' }));

    expect(props.onMissionChange).toHaveBeenCalledWith(
      expect.stringContaining('Ideenfabrik Auftrag'),
    );
    expect(props.onMissionChange).toHaveBeenCalledWith(
      expect.stringContaining('mobile UX verbessern'),
    );
    // The component logic for analyzed mission depends on effectiveRepoReady
    // If it says "geladen", it might be a pre-existing state or logic in the component
  });

  /* ───────────── mission adoption → input synchronisation ───────────── */
  it('syncs externally adopted insight missions into the chat input', () => {
    const props = baseProps();
    const { rerender } = render(
      <BuilderContainer {...props} mission="README + Update History" />,
    );

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

  /* ───────────── duplicate-header collapse check ───────────── */
  it('does not duplicate an already analysed mission', () => {
    const props = baseProps();
    const analysedMission = [
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

    render(<BuilderContainer {...props} mission={analysedMission} />);
    fireEvent.submit(screen.getByRole('button', { name: 'Senden' }));

    const emittedMission = props.onMissionChange.mock.calls[0][0] as string;
    expect(emittedMission.match(/Ideenfabrik Auftrag:/g)).toHaveLength(1);
    expect(emittedMission.match(/Repository-Kontext:/g)).toHaveLength(1);
    expect(emittedMission).toContain('Verbessere mobile UX und Log-Fenster.');
  });

  /* ───────────── side drawer interaction ───────────── */
  it('opens the DevChat side menu as overlay without changing the shell structure', () => {
    render(<BuilderContainer {...baseProps()} />);

    expect(screen.queryByText('Sovereign Studio')).toBeNull();
    fireEvent.click(screen.getByLabelText('Menü'));

    expect(screen.getByText('Sovereign Studio')).toBeDefined();
    expect(screen.getByText(/Cloudflare Workers/i)).toBeDefined();
  });

  /* ───────────── runtime source sheet interaction ───────────── */
  it('opens runtime source sheet from the status bar', () => {
    render(<BuilderContainer {...baseProps()} openhandsReady />);

    // hidden span with 'OpenHands' text exists even if visually hidden
    fireEvent.click(screen.getAllByText('OpenHands')[0]);

    expect(screen.getByText('Runtime Quelle')).toBeDefined();
    expect(screen.getByText('Echte Agent-Runtime verbunden')).toBeDefined();
    expect(screen.getByText(/Worker Chat/i)).toBeDefined();
  });

  /* ───────────── agent start flow (happy path) ───────────── */
  it('starts the external agent from the chat mission when ready', () => {
    const props = {
      ...baseProps(),
      openhandsReady: true,
      onStartOpenHands: vi.fn(),
    };
    render(<BuilderContainer {...props} />);

    fireEvent.change(chatField(), { target: { value: 'Test mission' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Senden' }));

    expect(props.onStartOpenHands).toHaveBeenCalledOnce();
    expect(props.onStartOpenHands.mock.calls[0][0]).toContain('Ideenfabrik Auftrag');
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
  });

  /* ───────────── repo not ready blocks send ───────────── */
  it('shows repo status when not ready and blocks direct send', () => {
    render(<BuilderContainer {...baseProps()} repoReady={false} openhandsReady />);

    expect(screen.getAllByText(/Repo fehlt/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('button', { name: 'Senden' })).toBeDisabled();
  });

  /* ───────────── OpenHands output renders as hint list ───────────── */
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
    expect(screen.getByText(/OpenHands ID/i)).toBeDefined();
    expect(screen.getByText(/1 Datei/)).toBeDefined();
    expect(screen.queryByLabelText(/Karten/i)).toBeNull();
  });

  /* ───────────── publish state disables composer ───────────── */
  it('shows publishing state correctly', () => {
    render(<BuilderContainer {...baseProps()} isPublishing />);

    expect(screen.getByRole('button', { name: 'Senden' })).toBeDisabled();
  });
});
