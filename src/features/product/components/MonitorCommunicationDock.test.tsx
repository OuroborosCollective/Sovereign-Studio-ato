import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MonitorCommunicationDock, type MonitorCommunicationEntry } from './MonitorCommunicationDock';

const entries: readonly MonitorCommunicationEntry[] = [
  { id: '1', kind: 'runtime', text: 'Workspace wird validiert.', createdAt: 1 },
  { id: '2', kind: 'user', text: 'Was machst du gerade?', createdAt: 2 },
  { id: '3', kind: 'communicate', text: 'Ich prüfe die Runtime-Evidence.', createdAt: 3 },
  { id: '4', kind: 'communicate', text: 'Der Monitor bleibt währenddessen sichtbar.', createdAt: 4 },
];

function renderDock(overrides: Partial<React.ComponentProps<typeof MonitorCommunicationDock>> = {}) {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  render(
    <MonitorCommunicationDock
      value=""
      onChange={onChange}
      onSubmit={onSubmit}
      disabled={false}
      busy={false}
      runtimeStatus="Sovereign Agent Runtime arbeitet"
      entries={entries}
      {...overrides}
    />,
  );
  return { onChange, onSubmit };
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

  it('shows only the latest bounded communication bubbles with explicit roles', () => {
    renderDock();

    const rail = screen.getByTestId('monitor-communication-bubbles');
    expect(rail.querySelectorAll('li')).toHaveLength(3);
    expect(screen.queryByText('Workspace wird validiert.')).toBeNull();
    expect(screen.getByText('Was machst du gerade?')).toBeTruthy();
    expect(screen.getAllByText('COMMUNICATE')).toHaveLength(2);
    expect(screen.getByText('YOU')).toBeTruthy();
  });

  it('allows a question by Enter without leaving the monitor and keeps 44px touch controls', () => {
    const { onSubmit } = renderDock({ value: 'Wie ist der Stand?' });
    const input = screen.getByLabelText('Frage an Sovereign während Live Monitor');
    const send = screen.getByRole('button', { name: 'Monitor Frage senden' });

    expect(input).toHaveStyle({ minHeight: '44px' });
    expect(send).toHaveStyle({ width: '44px', height: '44px' });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('redacts secret-shaped assistant output before it reaches the monitor bubble', () => {
    const secret = `ghp_${'A'.repeat(40)}`;
    renderDock({
      entries: [{ id: 'secret', kind: 'communicate', text: `credential ${secret}`, createdAt: 1 }],
    });

    expect(screen.queryByText(new RegExp(secret))).toBeNull();
    expect(screen.getByTestId('monitor-communication-bubbles').textContent).not.toContain(secret);
  });
});
