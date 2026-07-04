/**
 * SovereignToolLauncher - Compact "+" launcher for inspection tools.
 *
 * Technical panels are accessible but not dominant.
 * The main surface stays chat-first; this launcher surfaces tools on demand.
 * Android portrait safe: 393px max, no dense tab row.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLauncherStore } from '../../launcher/useLauncherStore';

const C = {
  bg:       '#0e1116',
  surface:  '#161c24',
  surfaceHi:'#1d2733',
  border:   '#232d3a',
  accent:   '#00d9b1',
  text:     '#cdd9e5',
  textSub:  '#768390',
  sky:      '#22d3ee',
} as const;

export type ToolId =
  | 'repo'
  | 'files'
  | 'diff'
  | 'github_access'
  | 'executor'
  | 'runtime_logs'
  | 'health'
  | 'memory'
  | 'coverage'
  | 'settings';

export interface ToolEntry {
  readonly id: ToolId;
  readonly label: string;
  readonly icon: string;
  readonly available: boolean;
}

const DEFAULT_TOOLS: readonly ToolEntry[] = [
  { id: 'repo',          label: 'Repo',           icon: '⎇', available: true },
  { id: 'files',         label: 'Files',          icon: '📄', available: true },
  { id: 'diff',          label: 'Diff',           icon: '±',  available: true },
  { id: 'github_access', label: 'GitHub Access',  icon: '🔑', available: true },
  { id: 'executor',      label: 'Executor',       icon: '▶',  available: true },
  { id: 'runtime_logs',  label: 'Runtime Logs',   icon: '≡',  available: true },
  { id: 'health',        label: 'Health',         icon: '♥',  available: true },
  { id: 'memory',        label: 'Memory',         icon: '◈', available: true },
  { id: 'coverage',      label: 'Coverage',       icon: '✦', available: true },
  { id: 'settings',      label: 'Settings',       icon: '⚙', available: true },
];

const DIRECT_LAUNCHER_TOOLS: ReadonlySet<ToolId> = new Set([
  'health',
  'memory',
  'coverage',
  'settings',
]);

function parentSelectId(id: ToolId): ToolId {
  // Files is a user-facing shortcut to the existing repo/file explorer surface.
  return id === 'files' ? 'repo' : id;
}

export interface SovereignToolLauncherProps {
  tools?: readonly ToolEntry[];
  onSelect: (id: ToolId) => void;
  activeToolId?: ToolId | null;
  /** Öffnet den Sovereign Launcher App-Grid (Issue #452) */
  onOpenLauncher?: () => void;
}

export const SovereignToolLauncher: React.FC<SovereignToolLauncherProps> = ({
  tools = DEFAULT_TOOLS,
  onSelect,
  activeToolId = null,
  onOpenLauncher,
}) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const launchTool = useLauncherStore((store) => store.launchTool);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    function onOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        close();
      }
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === 'Escape') close();
    }
    document.addEventListener('mousedown', onOutside);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onOutside);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open, close]);

  function handleSelect(id: ToolId) {
    onSelect(parentSelectId(id));
    if (DIRECT_LAUNCHER_TOOLS.has(id)) {
      launchTool(id);
    }
    setOpen(false);
  }

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', display: 'inline-block' }}
      data-testid="sovereign-tool-launcher"
    >
      <button
        type="button"
        aria-label="Tool Launcher öffnen"
        title="Tool Launcher öffnen"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
        style={{
          width: 36,
          height: 36,
          borderRadius: 10,
          background: open ? `${C.accent}20` : C.surface,
          border: `1px solid ${open ? C.accent : C.border}`,
          color: open ? C.accent : C.textSub,
          fontSize: 18,
          fontWeight: 300,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'border-color 0.15s, color 0.15s, background 0.15s',
        }}
      >
        +
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Tool Launcher"
          style={{
            position: 'absolute',
            bottom: 44,
            right: 0,
            width: 220,
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            padding: '6px 0',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            zIndex: 200,
          }}
        >
          {/* ── Sovereign Launcher — öffnet App-Grid (Issue #452) ── */}
          {onOpenLauncher && (
            <button
              type="button"
              role="menuitem"
              onClick={() => { onOpenLauncher(); setOpen(false); }}
              title="Alle Tools im Launcher"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                width: '100%',
                padding: '8px 14px 9px',
                background: `${C.accent}12`,
                border: 'none',
                borderBottom: `1px solid ${C.border}`,
                borderLeft: `2px solid ${C.accent}`,
                cursor: 'pointer',
                textAlign: 'left',
                marginBottom: 4,
              }}
              aria-label="Alle Tools im Launcher öffnen"
            >
              <span style={{ fontSize: 13, width: 18, textAlign: 'center', flexShrink: 0, color: C.accent }}>
                ⬡
              </span>
              <span style={{ fontSize: 13, color: C.accent, fontWeight: 600 }}>
                Alle Tools
              </span>
              <span style={{ fontSize: 10, color: C.textSub, marginLeft: 'auto' }}>
                Launcher →
              </span>
            </button>
          )}
          <div
            style={{
              padding: '6px 14px 8px',
              fontSize: 10,
              fontWeight: 600,
              color: C.textSub,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              borderBottom: `1px solid ${C.border}`,
              marginBottom: 4,
            }}
          >
            Werkzeuge
          </div>
          {tools.map((tool) => {
            const isActive = tool.id === activeToolId;
            return (
              <button
                key={tool.id}
                type="button"
                role="menuitem"
                disabled={!tool.available}
                onClick={() => handleSelect(tool.id)}
                title={tool.label}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  width: '100%',
                  padding: '8px 14px',
                  background: isActive ? `${C.accent}15` : 'transparent',
                  border: 'none',
                  borderLeft: isActive ? `2px solid ${C.accent}` : '2px solid transparent',
                  cursor: tool.available ? 'pointer' : 'not-allowed',
                  opacity: tool.available ? 1 : 0.4,
                  textAlign: 'left',
                  transition: 'background 0.1s',
                }}
                aria-current={isActive ? 'true' : undefined}
                aria-label={tool.label}
              >
                <span
                  style={{
                    fontSize: 13,
                    width: 18,
                    textAlign: 'center',
                    flexShrink: 0,
                    color: isActive ? C.accent : C.textSub,
                  }}
                >
                  {tool.icon}
                </span>
                <span
                  style={{
                    fontSize: 13,
                    color: isActive ? C.accent : C.text,
                    fontWeight: isActive ? 500 : 400,
                  }}
                >
                  {tool.label}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SovereignToolLauncher;
