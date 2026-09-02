import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SovereignChatDock, type SovereignChatEntry } from './MonitorCommunicationDock';
import type { SovereignLlmRouteOption } from '../runtime/devChatWorkerBridge';

const entries: readonly SovereignChatEntry[] = [
  { id: '1', kind: 'user', text: 'Was machst du gerade?', createdAt: 1 },
  { id: '2', kind: 'assistant', text: 'Ich prüfe den Auftrag im Hintergrund.', createdAt: 2 },
  { id: '3', kind: 'system', text: 'Für den nächsten Schritt brauche ich deine Freigabe.', createdAt: 3 },
];

function makeRoute(
  index: number,
  billingCategory: 'free' | 'standard' | 'premium' = 'free',
): SovereignLlmRouteOption {
  return {
    id: 'route-' + index,
    defaultModelId: 'model-' + index,
    label: 'Model ' + index,
    provider: 'Provider ' + index,
    billingCategory,
    priority: index,
    enabled: true,
  };
}

function renderDock(overrides: Partial<React.ComponentProps<typeof SovereignChatDock>> = {}) {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  const onRouteChange = vi.fn();
  const onOpenToolchain = vi.fn();
  const onOpenTools = vi.fn();

  render(
    <SovereignChatDock
      value=""
      onChange={onChange}
      onSubmit={onSubmit}
      disabled={false}
      busy={false}
      entries={entries}
      routeOptions={[]}
      onRouteChange={onRouteChange}
      onOpenToolchain={onOpenToolchain}
      toolchainState="ready"
      toolsLauncher={(
        <button type="button" aria-label="Tool Launcher öffnen" onClick={onOpenTools}>
          +
        </button>
      )}
      {...overrides}
    />,
  );

  return {
    onChange,
    onSubmit,
    onRouteChange,
    onOpenToolchain,
    onOpenTools,
  };
}

describe('SovereignChatDock', () => {
  it('renders one normal chat surface without monitor runtime rails', () => {
    renderDock();

    const dock = screen.getByTestId('sovereign-chat-dock');
    expect(dock).toHaveAttribute('data-overlay', 'false');
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(screen.queryByText('THINK')).toBeNull();
    expect(screen.queryByText('FLOW')).toBeNull();
    expect(screen.queryByText('IDEA')).toBeNull();
    expect(screen.queryByTestId('monitor-runtime-status')).toBeNull();
  });

  it('renders the complete conversation with user and Sovereign roles', () => {
    renderDock();

    const chat = screen.getByTestId('sovereign-chat-body-window');
    expect(chat.querySelectorAll('li')).toHaveLength(3);
    expect(screen.getByText('Was machst du gerade?')).toBeTruthy();
    expect(screen.getByText('Ich prüfe den Auftrag im Hintergrund.')).toBeTruthy();
    expect(screen.getAllByText('SOVEREIGN')).toHaveLength(2);
    expect(screen.getByText('DU')).toBeTruthy();
    expect(screen.queryByText('COMMUNICATE')).toBeNull();
    expect(screen.queryByText('RUNTIME')).toBeNull();
  });

  it('sends a chat message with Enter and keeps 44px touch controls', () => {
    const { onSubmit } = renderDock({ value: 'Wie ist der Stand?' });
    const input = screen.getByLabelText('Codeauftrag an Sovereign');
    const send = screen.getByRole('button', { name: 'Senden' });

    expect(input).toHaveStyle({ minHeight: '44px' });
    expect(send).toHaveStyle({ width: '44px', height: '44px' });
    expect(send).toHaveAttribute('title', 'Senden');
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('shows a structural route hint without interpreting free language locally', () => {
    renderDock({ routeHint: 'Repo erkannt · Laden' });

    expect(screen.getByTestId('sovereign-route-hint')).toHaveTextContent('Repo erkannt · Laden');
  });

  it('redacts secret-shaped assistant output before it reaches the chat', () => {
    const secret = 'ghp_' + 'A'.repeat(40);
    renderDock({
      entries: [{ id: 'secret', kind: 'assistant', text: 'credential ' + secret, createdAt: 1 }],
    });

    expect(screen.queryByText(new RegExp(secret))).toBeNull();
    expect(screen.getByTestId('sovereign-chat-body-window').textContent).not.toContain(secret);
  });

  it('keeps toolchain and launcher next to the composer without a monitor rail', () => {
    const { onOpenToolchain, onOpenTools } = renderDock();
    const toolRow = within(screen.getByTestId('sovereign-chat-tool-row'));

    const toolchain = toolRow.getByRole('button', { name: 'TOOLCHAIN' });
    const launcher = toolRow.getByRole('button', { name: 'Tool Launcher öffnen' });
    expect(toolchain).toHaveAttribute('title', 'Toolchain: bereit');
    fireEvent.click(toolchain);
    fireEvent.click(launcher);

    expect(onOpenToolchain).toHaveBeenCalledOnce();
    expect(onOpenTools).toHaveBeenCalledOnce();
    expect(screen.queryByTestId('monitor-status-rail')).toBeNull();
  });

  it('keeps the route picker compact, limits visible results to 24 and searches the full catalog', () => {
    const routes = Array.from({ length: 80 }, (_, index) => makeRoute(index));
    const { onRouteChange, onSubmit } = renderDock({ routeOptions: routes });

    expect(screen.queryByRole('dialog', { name: 'LLM-Modell auswählen' })).toBeNull();
    expect(screen.queryByText('Model 79')).toBeNull();

    fireEvent.click(screen.getByTestId('sovereign-llm-route-picker-trigger'));

    const dialog = screen.getByRole('dialog', { name: 'LLM-Modell auswählen' });
    expect(within(dialog).getAllByRole('option')).toHaveLength(24);
    expect(within(dialog).getByText('56 weitere Treffer · Suche verfeinern')).toBeTruthy();

    fireEvent.change(within(dialog).getByLabelText('Modelle durchsuchen'), {
      target: { value: 'route-79' },
    });

    const filteredOptions = within(dialog).getAllByRole('option');
    expect(filteredOptions).toHaveLength(1);
    expect(filteredOptions[0]).toHaveTextContent('Provider 79 · Model 79');

    fireEvent.click(filteredOptions[0]);

    expect(onRouteChange).toHaveBeenCalledOnce();
    expect(onRouteChange).toHaveBeenCalledWith('route-79');
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: 'LLM-Modell auswählen' })).toBeNull();
  });

  it('preserves a stale pinned route until the user explicitly resets it to Auto', () => {
    const { onRouteChange } = renderDock({
      routeOptions: [makeRoute(1)],
      selectedRouteId: 'retired-route',
    });

    const trigger = screen.getByTestId('sovereign-llm-route-picker-trigger');
    expect(trigger).toHaveTextContent('Fixierte Route nicht verfügbar · retired-route');
    expect(onRouteChange).not.toHaveBeenCalled();

    fireEvent.click(trigger);
    expect(screen.getByRole('dialog', { name: 'LLM-Modell auswählen' })).toBeTruthy();
    expect(onRouteChange).not.toHaveBeenCalled();

    fireEvent.keyDown(screen.getByTestId('sovereign-llm-route-picker'), { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'LLM-Modell auswählen' })).toBeNull();
    expect(onRouteChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Chat LLM Route auf Auto zurücksetzen' }));
    expect(onRouteChange).toHaveBeenCalledOnce();
    expect(onRouteChange).toHaveBeenCalledWith('');
  });

  it('labels paid routes before selection and pins without submitting an action', () => {
    const paidRoute = makeRoute(7, 'standard');
    const { onRouteChange, onSubmit } = renderDock({ routeOptions: [paidRoute] });

    fireEvent.click(screen.getByTestId('sovereign-llm-route-picker-trigger'));
    const option = screen.getByRole('option', { name: /Model 7/ });

    expect(option).toHaveTextContent('PAID · Bestätigung vor Nutzung');
    fireEvent.click(option);

    expect(onRouteChange).toHaveBeenCalledOnce();
    expect(onRouteChange).toHaveBeenCalledWith('route-7');
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
