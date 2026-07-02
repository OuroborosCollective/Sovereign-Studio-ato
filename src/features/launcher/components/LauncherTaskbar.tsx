/**
 * LauncherTaskbar — Strip mit Chips für offene Launcher-Tools.
 *
 * Rendert direkt über dem SovereignToolLauncher/Composer.
 * Aktive Tools: hervorgehobener Chip (Klick → Fokus).
 * Minimierte Tools: gedimmter Chip (Klick → Restore).
 * Unsichtbar wenn keine Tools offen sind.
 *
 * Issue #453
 */

import React from 'react';
import { useLauncherStore } from '../useLauncherStore';
import { LAUNCHER_REGISTRY } from '../launcherRegistry';

const C = {
  surface: '#161c24',
  border:  '#232d3a',
  accent:  '#00d9b1',
  text:    '#cdd9e5',
  textSub: '#768390',
} as const;

export function LauncherTaskbar() {
  const { windows, restoreWindow, focusWindow } = useLauncherStore();

  if (windows.length === 0) return null;

  return (
    <div
      data-testid="launcher-taskbar"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 10px',
        overflowX: 'auto',
        flexShrink: 0,
        borderBottom: `1px solid ${C.border}`,
      }}
    >
      {windows.map((win) => {
        const entry = LAUNCHER_REGISTRY.find((e) => e.id === win.id);
        if (!entry) return null;
        const Icon = entry.icon;
        const isMinimized = win.minimized;

        return (
          <button
            key={win.id}
            type="button"
            aria-label={`${entry.label} ${isMinimized ? 'wiederherstellen' : 'fokussieren'}`}
            data-testid={`taskbar-chip-${win.id}`}
            onClick={() => (isMinimized ? restoreWindow(win.id) : focusWindow(win.id))}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              padding: '4px 10px',
              borderRadius: 8,
              border: `1px solid ${isMinimized ? C.border : C.accent + '50'}`,
              background: isMinimized ? 'transparent' : `${C.accent}12`,
              color: isMinimized ? C.textSub : C.accent,
              fontSize: 10,
              fontWeight: 700,
              cursor: 'pointer',
              flexShrink: 0,
              transition: 'all 0.15s',
              letterSpacing: '0.04em',
            }}
          >
            <Icon size={11} />
            <span>{entry.label}</span>
            {isMinimized && (
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: C.textSub,
                  marginLeft: 2,
                }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
