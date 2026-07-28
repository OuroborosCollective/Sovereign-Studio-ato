/**
 * LauncherTaskbar & LauncherWindow — Snapshot & Interaction Tests
 * Issue #453
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LauncherTaskbar } from './LauncherTaskbar';
import { LauncherWindow } from './LauncherWindow';
import { useLauncherStore } from '../useLauncherStore';

// Registry mocken
vi.mock('../launcherRegistry', async () => {
  const { Terminal } = await import('lucide-react');
  const MockTool = () => null;
  MockTool.displayName = 'MockTool';
  return {
    LAUNCHER_REGISTRY: [
      {
        id: 'mock-tool',
        label: 'Mock Tool',
        description: 'Test',
        icon: Terminal,
        color: 'bg-violet-600',
        component: MockTool,
      },
    ],
  };
});

beforeEach(() => {
  useLauncherStore.setState({ isMenuOpen: false, windows: [] });
});

describe('LauncherTaskbar & LauncherWindow Accessibility', () => {
  it('LauncherTaskbar rendert nichts wenn windows leer ist', () => {
    const { container } = render(<LauncherTaskbar />);
    expect(container.firstChild).toBeNull();
  });

  it('LauncherTaskbar zeigt offene Tools mit barrierefreier Beschriftung', () => {
    useLauncherStore.setState({
      windows: [
        { id: 'mock-tool', minimized: false, zIndex: 100 },
      ],
    });

    render(<LauncherTaskbar />);
    const button = screen.getByRole('button', { name: 'Mock Tool fokussieren' });
    expect(button).toHaveAttribute('title', 'Mock Tool fokussieren');
  });

  it('LauncherTaskbar zeigt minimierte Tools mit barrierefreier Beschriftung', () => {
    useLauncherStore.setState({
      windows: [
        { id: 'mock-tool', minimized: true, zIndex: 100 },
      ],
    });

    render(<LauncherTaskbar />);
    const button = screen.getByRole('button', { name: 'Mock Tool wiederherstellen' });
    expect(button).toHaveAttribute('title', 'Mock Tool wiederherstellen');
  });

  it('LauncherWindow hat barrierefreie Beschriftungen und Tooltips auf Schließen und Minimieren', () => {
    render(<LauncherWindow id="mock-tool" zIndex={100} />);

    const minimizeBtn = screen.getByRole('button', { name: 'Mock Tool minimieren' });
    expect(minimizeBtn).toHaveAttribute('title', 'Mock Tool minimieren');

    const closeBtn = screen.getByRole('button', { name: 'Mock Tool schließen' });
    expect(closeBtn).toHaveAttribute('title', 'Mock Tool schließen');
  });
});
