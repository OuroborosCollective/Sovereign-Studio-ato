/**
 * LauncherMenu — Snapshot & Interaction Tests
 * Issue #452 / #454
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LauncherMenu } from './LauncherMenu';
import { useLauncherStore } from '../useLauncherStore';

// Registry mocken — Tests sollen nicht von konkreten Einträgen abhängen
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

describe('LauncherMenu', () => {
  it('rendert nichts wenn isMenuOpen === false', () => {
    render(<LauncherMenu />);
    expect(screen.queryByTestId('launcher-menu')).toBeNull();
  });

  it('rendert das Overlay wenn isMenuOpen === true', () => {
    useLauncherStore.setState({ isMenuOpen: true });
    render(<LauncherMenu />);
    expect(screen.getByTestId('launcher-menu')).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('zeigt registrierte Tools im Grid', () => {
    useLauncherStore.setState({ isMenuOpen: true });
    render(<LauncherMenu />);
    expect(screen.getByText('Mock Tool')).toBeTruthy();
  });

  it('schließt das Menu beim Klick auf den Close-Button', () => {
    useLauncherStore.setState({ isMenuOpen: true });
    render(<LauncherMenu />);
    fireEvent.click(screen.getByLabelText('Launcher schließen'));
    expect(useLauncherStore.getState().isMenuOpen).toBe(false);
  });

  it('schließt das Menu beim Klick auf den Backdrop', () => {
    useLauncherStore.setState({ isMenuOpen: true });
    render(<LauncherMenu />);
    fireEvent.click(screen.getByTestId('launcher-menu-backdrop'));
    expect(useLauncherStore.getState().isMenuOpen).toBe(false);
  });
});
