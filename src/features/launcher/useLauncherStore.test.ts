/**
 * useLauncherStore — Unit Tests
 * Issue #451
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useLauncherStore } from './useLauncherStore';

// Store vor jedem Test zurücksetzen
beforeEach(() => {
  useLauncherStore.setState({
    isMenuOpen: false,
    windows: [],
  });
});

describe('useLauncherStore — Menu', () => {
  it('öffnet das Menu via openMenu()', () => {
    useLauncherStore.getState().openMenu();
    expect(useLauncherStore.getState().isMenuOpen).toBe(true);
  });

  it('schließt das Menu via closeMenu()', () => {
    useLauncherStore.setState({ isMenuOpen: true });
    useLauncherStore.getState().closeMenu();
    expect(useLauncherStore.getState().isMenuOpen).toBe(false);
  });
});

describe('useLauncherStore — launchTool()', () => {
  it('öffnet ein neues Fenster', () => {
    useLauncherStore.getState().launchTool('test-tool');
    const { windows, isMenuOpen } = useLauncherStore.getState();
    expect(windows).toHaveLength(1);
    expect(windows[0].id).toBe('test-tool');
    expect(windows[0].minimized).toBe(false);
    expect(isMenuOpen).toBe(false);
  });

  it('öffnet nicht doppelt — fokussiert stattdessen', () => {
    useLauncherStore.getState().launchTool('test-tool');
    useLauncherStore.getState().launchTool('test-tool');
    expect(useLauncherStore.getState().windows).toHaveLength(1);
  });

  it('kann mehrere verschiedene Tools gleichzeitig öffnen', () => {
    useLauncherStore.getState().launchTool('tool-a');
    useLauncherStore.getState().launchTool('tool-b');
    expect(useLauncherStore.getState().windows).toHaveLength(2);
  });

  it('schließt das Menu beim Starten eines Tools', () => {
    useLauncherStore.setState({ isMenuOpen: true });
    useLauncherStore.getState().launchTool('test-tool');
    expect(useLauncherStore.getState().isMenuOpen).toBe(false);
  });

  it('vergibt aufsteigende z-index Werte', () => {
    useLauncherStore.getState().launchTool('tool-a');
    useLauncherStore.getState().launchTool('tool-b');
    const { windows } = useLauncherStore.getState();
    expect(windows[1].zIndex).toBeGreaterThan(windows[0].zIndex);
  });
});

describe('useLauncherStore — closeWindow()', () => {
  it('entfernt das Fenster aus dem Stack', () => {
    useLauncherStore.getState().launchTool('test-tool');
    useLauncherStore.getState().closeWindow('test-tool');
    expect(useLauncherStore.getState().windows).toHaveLength(0);
  });

  it('entfernt nur das angegebene Fenster', () => {
    useLauncherStore.getState().launchTool('tool-a');
    useLauncherStore.getState().launchTool('tool-b');
    useLauncherStore.getState().closeWindow('tool-a');
    const { windows } = useLauncherStore.getState();
    expect(windows).toHaveLength(1);
    expect(windows[0].id).toBe('tool-b');
  });
});

describe('useLauncherStore — minimizeWindow() / restoreWindow()', () => {
  it('minimiert ein Fenster', () => {
    useLauncherStore.getState().launchTool('test-tool');
    useLauncherStore.getState().minimizeWindow('test-tool');
    expect(useLauncherStore.getState().windows[0].minimized).toBe(true);
  });

  it('stellt ein minimiertes Fenster wieder her', () => {
    useLauncherStore.getState().launchTool('test-tool');
    useLauncherStore.getState().minimizeWindow('test-tool');
    useLauncherStore.getState().restoreWindow('test-tool');
    expect(useLauncherStore.getState().windows[0].minimized).toBe(false);
  });
});

describe('useLauncherStore — focusWindow()', () => {
  it('gibt dem Fenster den höchsten z-index', () => {
    useLauncherStore.getState().launchTool('tool-a');
    useLauncherStore.getState().launchTool('tool-b');
    // tool-b hat höheren z-index — tool-a fokussieren
    useLauncherStore.getState().focusWindow('tool-a');
    const { windows } = useLauncherStore.getState();
    const a = windows.find((w) => w.id === 'tool-a')!;
    const b = windows.find((w) => w.id === 'tool-b')!;
    expect(a.zIndex).toBeGreaterThan(b.zIndex);
  });

  it('stellt minimiertes Fenster beim Fokussieren wieder her', () => {
    useLauncherStore.getState().launchTool('test-tool');
    useLauncherStore.getState().minimizeWindow('test-tool');
    useLauncherStore.getState().focusWindow('test-tool');
    expect(useLauncherStore.getState().windows[0].minimized).toBe(false);
  });
});
