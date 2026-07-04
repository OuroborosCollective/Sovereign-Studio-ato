import { render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it } from 'vitest';
import { SovereignActionStreamPanel } from './SovereignActionStreamPanel';
import {
  appendSovereignActionEvents,
  buildInputReceivedEvent,
  buildRouteSelectionEvent,
  buildWorkerRequestEvent,
  buildWorkerResponseEvent,
  createSovereignActionStreamState,
} from '../runtime/sovereignActionStreamRuntime';

describe('SovereignActionStreamPanel', () => {
  it('renders the action stream as a chat worker bubble instead of a separate dashboard card', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Baue mir das ein'),
      buildRouteSelectionEvent({
        route: 'code-llm',
        reason: 'Code-Auftrag erkannt.',
        state: 'running',
      }),
      buildWorkerRequestEvent('Mistral 7B'),
      buildWorkerResponseEvent(),
    ]);

    render(<SovereignActionStreamPanel stream={stream} />);

    const panel = screen.getByTestId('sovereign-action-stream');
    expect(panel.getAttribute('data-layout')).toBe('chat-worker-bubble');
    expect(screen.getByText(/Sovereign wartet auf nächsten echten Schritt/i)).toBeTruthy();
    expect(screen.getByText(/Code-Auftrag braucht Ergebnis-Gate/i)).toBeTruthy();
    expect(screen.getByText(/Patch\/Diff/i)).toBeTruthy();
  });
});
