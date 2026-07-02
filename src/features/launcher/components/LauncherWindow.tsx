/**
 * LauncherWindow — Floating Tool Panel für den Sovereign Launcher.
 *
 * Rendert ein einzelnes Tool als fixiertes Panel über der App-Oberfläche.
 * Titelleiste: Icon, Name, Minimize-Button, Close-Button.
 * Fokus-Verwaltung via z-index aus useLauncherStore.
 *
 * Issue #453
 */

import React from 'react';
import { X, Minus } from 'lucide-react';
import { useLauncherStore } from '../useLauncherStore';
import { LAUNCHER_REGISTRY } from '../launcherRegistry';

const C = {
  bg:      '#0e1116',
  surface: '#161c24',
  border:  '#232d3a',
  accent:  '#00d9b1',
  text:    '#cdd9e5',
  textSub: '#768390',
} as const;

interface LauncherWindowProps {
  id: string;
  zIndex: number;
}

export function LauncherWindow({ id, zIndex }: LauncherWindowProps) {
  const { closeWindow, minimizeWindow, focusWindow } = useLauncherStore();
  const entry = LAUNCHER_REGISTRY.find((e) => e.id === id);
  if (!entry) return null;

  const Icon = entry.icon;
  const ToolComponent = entry.component;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={entry.label}
      data-testid={`launcher-window-${id}`}
      onClick={() => focusWindow(id)}
      style={{
        position: 'fixed',
        inset: '70px 12px 120px',
        zIndex,
        display: 'flex',
        flexDirection: 'column',
        background: `${C.bg}f7`,
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        border: `1px solid ${C.border}`,
        borderRadius: 16,
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
        overflow: 'hidden',
      }}
    >
      {/* ── Titelleiste ─────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          borderBottom: `1px solid ${C.border}`,
          flexShrink: 0,
          background: C.surface,
        }}
      >
        {/* Icon */}
        <div
          className={entry.color}
          style={{
            width: 24,
            height: 24,
            borderRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Icon size={13} className="text-white" />
        </div>

        {/* Label */}
        <span
          style={{
            flex: 1,
            fontSize: 11,
            fontWeight: 700,
            color: C.text,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
          }}
        >
          {entry.label}
        </span>

        {/* Badge */}
        {entry.badge && (
          <span
            style={{
              fontSize: 8,
              fontWeight: 900,
              background: '#6366f1',
              color: '#fff',
              padding: '2px 6px',
              borderRadius: 99,
              letterSpacing: '0.08em',
            }}
          >
            {entry.badge}
          </span>
        )}

        {/* Minimize */}
        <button
          type="button"
          aria-label={`${entry.label} minimieren`}
          onClick={(e) => { e.stopPropagation(); minimizeWindow(id); }}
          style={{
            width: 26,
            height: 26,
            borderRadius: 6,
            border: 'none',
            background: 'transparent',
            color: C.textSub,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'color 0.15s, background 0.15s',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.color = C.text;
            (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.08)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.color = C.textSub;
            (e.currentTarget as HTMLElement).style.background = 'transparent';
          }}
        >
          <Minus size={13} />
        </button>

        {/* Close */}
        <button
          type="button"
          aria-label={`${entry.label} schließen`}
          onClick={(e) => { e.stopPropagation(); closeWindow(id); }}
          style={{
            width: 26,
            height: 26,
            borderRadius: 6,
            border: 'none',
            background: 'transparent',
            color: C.textSub,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'color 0.15s, background 0.15s',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.color = '#f87171';
            (e.currentTarget as HTMLElement).style.background = 'rgba(248,113,113,0.1)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.color = C.textSub;
            (e.currentTarget as HTMLElement).style.background = 'transparent';
          }}
        >
          <X size={13} />
        </button>
      </div>

      {/* ── Tool-Inhalt ──────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <ToolComponent
          onClose={() => closeWindow(id)}
          onMinimize={() => minimizeWindow(id)}
        />
      </div>
    </div>
  );
}
