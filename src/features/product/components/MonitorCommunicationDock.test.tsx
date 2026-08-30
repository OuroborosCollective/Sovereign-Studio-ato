import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MonitorCommunicationDock, type MonitorCommunicationEntry } from './MonitorCommunicationDock';
import type { SovereignLlmRouteOption } from '../runtime/devChatWorkerBridge';

const entries: readonly MonitorCommunicationEntry[] = [
  { id: '1', kind: 'runtime', text: 'Workspace wird validiert.', createdAt: 1 },
  { id: '2', kind: 'user', text: 'Was machst du gerade?', createdAt: 2 },
  { id: '3', kind: 'communicate', text: 'Ich prüfe die Runtime-Evidence.', createdAt: 3 },
  { id: '4', kind: 'communicate', text: 'Der Monitor bleibt währenddessen sichtbar.', createdAt: 4 },
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

function renderDock(overrides: Partial<React.ComponentProps<typeof MonitorCommunicationDock>> = {}) {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  const onRouteChange = vi.fn();
  const onOpenFlow = vi.fn();
  const onRequestIdea = vi.fn();
  const onOpenToolchain = vi.fn();
  const onOpenTools = vi.fn();

  render(
    <MonitorCommunicationDock
      value=""
      onChange={onChange}
      onSubmit={onSubmit}
      disabled={false}
      busy={false}
      runtimeStatus="Sovereign Agent Runtime arbeitet"
      entries={entries}
      routeOptions={[]}
      onRouteChange={onRouteChange}
      runtimeMood="😊✨"
      onOpenFlow={onOpenFlow}
      onRequestIdea={onRequestIdea}
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
    onOpenFlow,
    onRequestIdea,
    onOpenToolchain,
    onOpenTools,
  };
}

describe('MonitorCommunicationDock', () => {
  it('keeps THINK limited to observable runtime status and stays in document flow', () => {
    renderDock();

    const dock = screen.getByTestId('monitor-communication-dock');
    expect(dock).toHaveAttribute('data-overlay', 'false');
    expect(dock.style.position).toBe('');
    expect(screen.getByText('THINK')).toBeTruthy();
    expect(screen.getByTestId('monitor-runtime-status')).toHaveTextContent('Sovereign Agent Runtime arbeitet');
    expect(screen.getByTitle(/keine verborgene Modell-Gedankenkette/i)).toBeTruthy();
  });

  it('keeps recent receipts and the latest user mission visible with explicit roles', () => {
    renderDock();

    const rail = screen.getByTestId('monitor-communication-bubbles');
    expect(rail.querySelectorAll('li')).toHaveLength(4);
    expect(screen.getByText('Workspace wird validiert.')).toBeTruthy();
    expect(screen.getByText('Was machst du gerade?')).toBeTruthy();
    expect(screen.getAllByText('COMMUNICATE')).toHaveLength(2);
    expect(screen.getByText('YOU')).toBeTruthy();
  });

  it('allows a question by Enter without leaving the monitor and keeps 44px touch controls', () => {
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

    expect(screen.getByTestId('monitor-route-hint')).toHaveTextContent('Repo erkannt · Laden');
  });

  it('redacts secret-shaped assistant output before it reaches the monitor bubble', () => {
    const secret = 'ghp_' + 'A'.repeat(40);
    renderDock({
      entries: [{ id: 'secret', kind: 'communicate', text: 'credential ' + secret, createdAt: 1 }],
    });

    expect(screen.queryByText(new RegExp(secret))).toBeNull();
    expect(screen.getByTestId('monitor-communication-bubbles').textContent).not.toContain(secret);
  });

  it('exposes the compact THINK, FLOW, IDEA, mood, TOOLCHAIN and launcher rail with real callbacks', () => {
    const {
      onOpenFlow,
      onRequestIdea,
      onOpenToolchain,
      onOpenTools,
    } = renderDock();
    const rail = within(screen.getByTestId('monitor-status-rail'));

    expect(rail.getByText('THINK')).toBeTruthy();
    expect(rail.getByLabelText('Sovereign bereit')).toHaveTextContent('😊✨');

    const flow = rail.getByRole('button', { name: 'FLOW' });
    const idea = rail.getByRole('button', { name: 'IDEA' });
    const toolchain = rail.getByRole('button', { name: 'TOOLCHAIN' });
    const launcher = rail.getByRole('button', { name: 'Tool Launcher öffnen' });

    expect(toolchain).toHaveAttribute('title', 'Toolchain: bereit');
    fireEvent.click(flow);
    fireEvent.click(idea);
    fireEvent.click(toolchain);
    fireEvent.click(launcher);

    expect(onOpenFlow).toHaveBeenCalledOnce();
    expect(onRequestIdea).toHaveBeenCalledOnce();
    expect(onOpenToolchain).toHaveBeenCalledOnce();
    expect(onOpenTools).toHaveBeenCalledOnce();
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

    fireEvent.keyDown(screen.getByTestId('monitor-llm-route-picker'), { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'LLM-Modell auswählen' })).toBeNull();
    expect(onRouteChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Monitor LLM Route auf Auto zurücksetzen' }));
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
