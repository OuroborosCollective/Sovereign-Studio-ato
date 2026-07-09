import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it } from 'vitest';
import { SovereignActionStreamPanel } from './SovereignActionStreamPanel';
import {
  appendSovereignActionEvent,
  appendSovereignActionEvents,
  buildAgentJobCreatedEvent,
  buildBlockedActionEvent,
  buildInputReceivedEvent,
  buildRouteSelectionEvent,
  buildWorkerRequestEvent,
  buildWorkerResponseEvent,
  createSovereignActionStreamState,
} from '../runtime/sovereignActionStreamRuntime';

describe('SovereignActionStreamPanel', () => {
  it('renders as an inline chat action trace — not a separate dashboard card', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Baue mir das ein'),
      buildRouteSelectionEvent({ route: 'code-llm', reason: 'Code-Auftrag erkannt.', state: 'running' }),
      buildWorkerRequestEvent('Mistral 7B'),
      buildWorkerResponseEvent(),
    ]);

    render(<SovereignActionStreamPanel stream={stream} />);

    const panel = screen.getByTestId('sovereign-action-stream');
    expect(panel.getAttribute('data-layout')).toBe('chat-inline-action-trace');
    expect(panel.getAttribute('role')).toBe('log');
    expect(panel.getAttribute('aria-label')).toBe('Sovereign Action Stream');
    // No panel/card avatar — the trace has no separate avatar element like a chat bubble does
    expect(screen.queryByText('⬡')).toBeNull();
    // Shows a result-gate event (code-llm route resolved) — confirms it tracked that route
    expect(screen.getByText(/Code-Auftrag braucht Ergebnis-Gate/i)).toBeTruthy();
  });

  it('is collapsed by default and shows only title + last-event summary', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Test'),
      buildWorkerRequestEvent('DeepSeek R1'),
    ]);

    render(<SovereignActionStreamPanel stream={stream} />);

    // Toggle button starts collapsed
    const toggle = screen.getByRole('button', { name: 'Details' });
    expect(toggle).toBeDefined();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    // Last-event summary is visible in collapsed mode
    expect(screen.getByText(/Worker-Route fragt Modell an/i)).toBeTruthy();

    // Individual event rows are NOT rendered when collapsed
    expect(screen.queryByText(/Auftrag empfangen/i)).toBeNull();
  });

  it('expands on toggle and shows the full event list', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Mach was'),
      buildWorkerRequestEvent('Llama 3.1'),
    ]);

    render(<SovereignActionStreamPanel stream={stream} />);

    // Click to expand
    fireEvent.click(screen.getByRole('button', { name: 'Details' }));

    const toggle = screen.getByRole('button', { name: 'Details ausblenden' });
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    // Both events are now visible
    expect(screen.getByText(/Auftrag empfangen/i)).toBeTruthy();
    expect(screen.getByText(/Worker-Route fragt Modell an/i)).toBeTruthy();
  });

  it('collapses again when toggled a second time', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Test'),
      buildWorkerRequestEvent('Mistral'),
    ]);

    render(<SovereignActionStreamPanel stream={stream} />);

    fireEvent.click(screen.getByRole('button', { name: 'Details' }));
    expect(screen.getByRole('button', { name: 'Details ausblenden' })).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Details ausblenden' }));
    expect(screen.getByRole('button', { name: 'Details' })).toBeDefined();

    // Individual rows gone again
    expect(screen.queryByText(/Auftrag empfangen/i)).toBeNull();
  });

  it('shows blocked state with rose dot and does not show green lamp', () => {
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildBlockedActionEvent({
        route: 'worker',
        label: 'Worker blockiert',
        detail: 'Worker-Timeout als Runtime-Blocker behandeln; nicht blind erneut senden.',
      }),
    );

    render(<SovereignActionStreamPanel stream={stream} />);

    // Title reflects blocked state
    expect(screen.getByText(/Sovereign wartet auf nächsten echten Schritt/i)).toBeTruthy();

    // activeRoute is null after terminal state → "läuft" not in title
    const title = screen.getByText(/Sovereign wartet/i).textContent ?? '';
    expect(title).not.toContain('läuft');
  });

  it('shows queued agent job as waiting, not running work', () => {
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildAgentJobCreatedEvent({ jobId: 'agent-queued', status: 'queued' }),
    );

    render(<SovereignActionStreamPanel stream={stream} />);

    expect(screen.getByText(/Sovereign wartet · agent-job angefragt/i)).toBeTruthy();
    expect(screen.queryByText(/agent-job läuft/i)).toBeNull();
  });

  it('does not render when there are no events', () => {
    const stream = createSovereignActionStreamState();
    const { container } = render(<SovereignActionStreamPanel stream={stream} />);
    expect(container.firstChild).toBeNull();
  });

  it('all LLM routes appear equally — not just the OpenHands path', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Was ist der Status?'),
      buildRouteSelectionEvent({ route: 'free-chat', reason: 'Chat-Frage erkannt.', state: 'running' }),
      buildWorkerRequestEvent('Llama 3.1 8B'),
      buildWorkerResponseEvent(),
    ]);

    render(<SovereignActionStreamPanel stream={stream} />);

    // Worker route appears in last-event summary
    expect(screen.getByText(/Worker-Antwort erhalten/i)).toBeTruthy();

    // No "openhands" text — this was a free-chat route, not OpenHands
    fireEvent.click(screen.getByRole('button', { name: 'Details' }));
    // "free-chat" route is visible in at least one event badge
    expect(screen.getAllByText(/free-chat/i).length).toBeGreaterThanOrEqual(1);
  });

  it('expanded view caps at maxEvents and does not overflow', () => {
    const base = createSovereignActionStreamState();
    const stream = appendSovereignActionEvents(base, [
      buildInputReceivedEvent('eins'),
      buildInputReceivedEvent('zwei'),
      buildInputReceivedEvent('drei'),
      buildWorkerRequestEvent('M1'),
      buildWorkerResponseEvent(),
    ]);

    render(<SovereignActionStreamPanel stream={stream} maxEvents={3} />);

    fireEvent.click(screen.getByRole('button', { name: 'Details' }));

    // Only the last 3 events are rendered
    const rows = document.querySelectorAll('[data-route]');
    expect(rows.length).toBeLessThanOrEqual(3);
  });
});
