import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
  return screen.getByLabelText(/Sovereign Chat Eingabe/i) as HTMLTextAreaElement;
}

function sendButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: 'Senden' }) as HTMLButtonElement;
}


function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function mockWorkerReply(text = 'Worker Antwort aus Cloudflare Route.') {
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ choices: [{ message: { content: text } }] })));
}

beforeEach(() => {
  mockWorkerReply();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** ----------------------------------------------------------------
 *  Tests
 *  ---------------------------------------------------------------- */
describe('BuilderContainer (AppControl DevChat shell)', () => {
  /* ───────────────────────── structure / shell ───────────────────────── */
  it('renders the AppControl DevChat shell structure', () => {
    render(<BuilderContainer {...baseProps()} />);

    const root = screen.getByTestId('builder-container');
    expect(root).toHaveAttribute('data-layout', 'devchat-appcontrol-integrated');
    expect(root).toHaveAttribute('aria-label', 'Sovereign Builder');

    // top bar brand tokens
    expect(screen.getAllByText('Sovereign').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('DevChat')).toBeDefined();

    // AppControl module tabs are part of the new Builder truth.
    // ROU exists in both top module lamps and bottom tabbar, so this must be an all-query.
    expect(screen.getByLabelText('Sovereign Studio Tabs')).toBeDefined();
    expect(screen.getByText('CHAT')).toBeDefined();
    expect(screen.getAllByText('ROU').length).toBeGreaterThanOrEqual(1);

    // main chat viewport + composer
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(chatField()).toBeDefined();

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

  /* ───────────── worker route remains available when OpenHands is blocked ───────────── */
  it('keeps chat send available when the agent runtime is not start-ready and routes to Worker', async () => {
    const props = baseProps();
    render(<BuilderContainer {...props} openhandsReady={false} />);

    fireEvent.change(chatField(), {
      target: { value: 'Bitte mobile UX verbessern und Log direkt sichtbar machen.' },
    });

    expect(sendButton()).not.toBeDisabled();
    fireEvent.click(sendButton());

    expect(chatField().value).toBe('');
    await waitFor(() => expect(screen.getByText('Worker Antwort aus Cloudflare Route.')).toBeDefined());
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  /* ───────────── mission adoption → input synchronisation ───────────── */
  it('syncs externally adopted insight missions only into an untouched empty composer', () => {
    const props = baseProps();
    const { rerender } = render(
      <BuilderContainer {...props} mission="" />,
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
  it('does not duplicate an already analysed mission when OpenHands execution is requested', () => {
    const props = {
      ...baseProps(),
      openhandsReady: true,
      onStartOpenHands: vi.fn(),
    };
    render(<BuilderContainer {...props} mission="" />);

    fireEvent.change(chatField(), { target: { value: 'Bitte OpenHands: implementiere den mobilen Chat-Fix als Draft PR.' } });
    fireEvent.click(sendButton());

    expect(props.onMissionChange).toHaveBeenCalled();
    const emittedMission = props.onMissionChange.mock.calls[0][0] as string;
    expect(emittedMission.match(/Ideenfabrik Auftrag:/g)).toHaveLength(1);
    expect(emittedMission.match(/Repository-Kontext:/g)).toHaveLength(1);
    expect(emittedMission).toContain('implementiere den mobilen Chat-Fix');
    expect(props.onStartOpenHands).toHaveBeenCalledOnce();
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
  it('opens runtime source sheet with Cloudflare Worker as the standard LLM route', () => {
    render(<BuilderContainer {...baseProps()} openhandsReady />);

    fireEvent.click(screen.getByText('RT'));

    expect(screen.getByText('Runtime Quelle')).toBeDefined();
    expect(screen.getByText('Cloudflare Worker')).toBeDefined();
    expect(screen.getByText('Echte Agent-Runtime für Code/Draft-PR-Aufträge')).toBeDefined();
  });

  /* ───────────── agent start flow (happy path) ───────────── */
  it('starts the external agent only for explicit code or Draft-PR execution intent', () => {
    const props = {
      ...baseProps(),
      openhandsReady: true,
      onStartOpenHands: vi.fn(),
    };
    render(<BuilderContainer {...props} />);

    fireEvent.change(chatField(), { target: { value: 'Bitte implementiere einen Chat-State-Fix als Draft PR.' } });
    fireEvent.click(sendButton());

    expect(props.onStartOpenHands).toHaveBeenCalledOnce();
    expect(props.onStartOpenHands.mock.calls[0][0]).toContain('Ideenfabrik Auftrag');
    expect(props.onGenerateIdeas).not.toHaveBeenCalled();
  });

  /* ───────────── repo not ready still allows normal Worker chat ───────────── */
  it('shows repo status when not ready but does not block normal chat', async () => {
    const props = baseProps();
    render(<BuilderContainer {...props} repoReady={false} openhandsReady />);

    expect(screen.getAllByText(/Repo fehlt/).length).toBeGreaterThanOrEqual(1);
    expect(sendButton()).not.toBeDisabled();
    fireEvent.change(chatField(), { target: { value: 'Was brauchst du als nächstes?' } });
    fireEvent.click(sendButton());

    expect(chatField().value).toBe('');
    await waitFor(() => expect(screen.getByText('Worker Antwort aus Cloudflare Route.')).toBeDefined());
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  /* ───────────── repo load keeps input clean and writes to chat history ───────────── */
  it('loads a GitHub repo as runtime context without writing analysis into the composer', async () => {
    const props = baseProps();
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      tree: [
        { path: 'src/App.tsx', type: 'blob', size: 123 },
        { path: 'src/features/product/containers/BuilderContainer.tsx', type: 'blob', size: 456 },
      ],
      truncated: false,
    })));

    render(<BuilderContainer {...props} mission="" repoReady={false} />);

    const repoUrl = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/tree/main/src';
    fireEvent.change(chatField(), { target: { value: repoUrl } });
    fireEvent.click(sendButton());

    expect(chatField().value).toBe('');
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());
    expect(screen.getByText(repoUrl)).toBeDefined();
    expect(chatField().value).not.toContain('Repo geladen');
    expect(props.onMissionChange).not.toHaveBeenCalled();
  });

  /* ───────────── normal text after repo load uses Worker, not OpenHands ───────────── */
  it('routes normal text after repo load through Cloudflare Worker instead of OpenHands', async () => {
    const props = {
      ...baseProps(),
      openhandsReady: true,
      onStartOpenHands: vi.fn(),
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        tree: [{ path: 'src/App.tsx', type: 'blob', size: 123 }],
        truncated: false,
      }))
      .mockResolvedValueOnce(jsonResponse({ choices: [{ message: { content: 'Repo-Frage über Worker beantwortet.' } }] }));
    vi.stubGlobal('fetch', fetchMock);

    render(<BuilderContainer {...props} mission="" repoReady={false} />);

    fireEvent.change(chatField(), { target: { value: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato' } });
    fireEvent.click(sendButton());
    await waitFor(() => expect(screen.getByText(/Repo geladen/)).toBeDefined());

    fireEvent.change(chatField(), { target: { value: 'Was ist der nächste sinnvolle Schritt?' } });
    fireEvent.click(sendButton());

    expect(chatField().value).toBe('');
    await waitFor(() => expect(screen.getByText('Repo-Frage über Worker beantwortet.')).toBeDefined());
    expect(props.onStartOpenHands).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });



  /* ───────────── worker 500 becomes runtime diagnostic state, not blind retry ───────────── */
  it('turns Worker HTTP 500 into a local runtime diagnostic and avoids blind repeat calls', async () => {
    const props = baseProps();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ error: { message: 'Gateway exploded', type: 'server_error' } }, 500))
      .mockResolvedValueOnce(jsonResponse({ ok: true, provider: 'sovereign-llm-bridge', gateway: 'gatter', model: 'cerebras/zai-glm-4.7', upstreamConfigured: true, secretConfigured: true }));
    vi.stubGlobal('fetch', fetchMock);

    render(<BuilderContainer {...props} repoReady openhandsReady />);

    fireEvent.change(chatField(), { target: { value: 'Hast du Vorschläge für bessere UI?' } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(screen.getByText(/Ich wiederhole den kaputten Worker-Call nicht blind/i)).toBeDefined());
    expect(screen.getByText(/HTTP 500/i)).toBeDefined();
    expect(screen.getByText(/secret=ok/i)).toBeDefined();

    fireEvent.change(chatField(), { target: { value: 'Warum?' } });
    fireEvent.click(sendButton());

    await waitFor(() => expect(screen.getAllByText(/Ich wiederhole den kaputten Worker-Call nicht blind/i).length).toBeGreaterThanOrEqual(2));
    expect(fetchMock).toHaveBeenCalledTimes(2);
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

    expect(screen.getByText(/OpenHands ID/i)).toBeDefined();
    expect(screen.getByText(/1 Datei/)).toBeDefined();
    expect(screen.queryByLabelText(/Karten/i)).toBeNull();
  });

  /* ───────────── publish state disables composer ───────────── */
  it('shows publishing state correctly', () => {
    render(<BuilderContainer {...baseProps()} isPublishing />);

    expect(sendButton()).toBeDisabled();
  });
});
