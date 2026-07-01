/**
 * useLauncherStore — Zustand-Store für den Sovereign Launcher.
 *
 * Hält den Zustand des Launcher-Menus und aller offenen Tool-Fenster.
 * Session-only: kein localStorage, kein persistierter Zustand.
 *
 * Issue #451
 */

import { create } from 'zustand';

// ── Typen ────────────────────────────────────────────────────────────────────

export interface OpenWindow {
  /** Entspricht LauncherEntry.id */
  id: string;
  minimized: boolean;
  /** z-index für Fokus-Management */
  zIndex: number;
  openedAt: number;
}

interface LauncherStore {
  isMenuOpen: boolean;
  windows: OpenWindow[];

  /** App-Grid-Overlay öffnen */
  openMenu: () => void;
  /** App-Grid-Overlay schließen */
  closeMenu: () => void;
  /**
   * Tool starten — oder existierendes Fenster fokussieren.
   * Verhindert doppeltes Öffnen desselben Tools.
   */
  launchTool: (id: string) => void;
  /** Floating Window schließen und aus Stack entfernen */
  closeWindow: (id: string) => void;
  /** Fenster minimieren → Chip erscheint in LauncherTaskbar */
  minimizeWindow: (id: string) => void;
  /** Minimiertes Fenster wiederherstellen */
  restoreWindow: (id: string) => void;
  /** Fenster in den Vordergrund bringen (z-index erhöhen) */
  focusWindow: (id: string) => void;
}

// ── Store ────────────────────────────────────────────────────────────────────

export const useLauncherStore = create<LauncherStore>((set, get) => ({
  isMenuOpen: false,
  windows: [],

  openMenu: () => set({ isMenuOpen: true }),

  closeMenu: () => set({ isMenuOpen: false }),

  launchTool: (id: string) => {
    const existing = get().windows.find((w) => w.id === id);
    if (existing) {
      // Bereits offen: fokussieren statt doppelt öffnen
      get().focusWindow(id);
      set({ isMenuOpen: false });
      return;
    }
    const maxZ = get().windows.reduce((m, w) => Math.max(m, w.zIndex), 0);
    set((s) => ({
      isMenuOpen: false,
      windows: [
        ...s.windows,
        { id, minimized: false, zIndex: maxZ + 1, openedAt: Date.now() },
      ],
    }));
  },

  closeWindow: (id: string) =>
    set((s) => ({ windows: s.windows.filter((w) => w.id !== id) })),

  minimizeWindow: (id: string) =>
    set((s) => ({
      windows: s.windows.map((w) =>
        w.id === id ? { ...w, minimized: true } : w,
      ),
    })),

  restoreWindow: (id: string) =>
    set((s) => ({
      windows: s.windows.map((w) =>
        w.id === id ? { ...w, minimized: false } : w,
      ),
    })),

  focusWindow: (id: string) => {
    const maxZ = get().windows.reduce((m, w) => Math.max(m, w.zIndex), 0);
    set((s) => ({
      windows: s.windows.map((w) =>
        w.id === id ? { ...w, zIndex: maxZ + 1, minimized: false } : w,
      ),
    }));
  },
}));
