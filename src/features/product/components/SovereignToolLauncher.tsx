/**
 * SovereignToolLauncher - Compact "+" launcher for inspection tools.
 *
 * Runtime derives every shortcut gate. This component only displays the gate
 * and dispatches actions that are explicitly allowed.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLauncherStore } from '../../launcher/useLauncherStore';
import {
  createEmptySovereignToolShortcutContext,
  deriveSovereignToolShortcutGates,
  type SovereignToolShortcutContext,
  type SovereignToolShortcutGate,
  type SovereignToolShortcutId,
} from '../runtime/sovereignToolShortcutRuntime';
import { useSovereignToolInspectionStore } from '../runtime/sovereignToolInspectionRuntime';

const C = {
  bg: '#0e1116',
  surface: '#161c24',
  surfaceHi: '#1d2733',
  border: '#232d3a',
  accent: '#00d9b1',
  text: '#cdd9e5',
  textSub: '#768390',
  sky: '#22d3ee',
  amber: '#f59e0b',
} as const;

export type ToolId = SovereignToolShortcutId;
export type ToolEntry = SovereignToolShortcutGate;

const DIRECT_LAUNCHER_TOOLS: ReadonlySet<ToolId> = new Set([
  'health',
  'memory',
  'coverage',
  'settings',
]);

export interface SovereignToolLauncherProps {
  runtimeContext?: SovereignToolShortcutContext;
  onSelect: (id: ToolId) => void;
  onBlockedSelect?: (id: ToolId) => void;
  activeToolId?: ToolId | null;
  onOpenLauncher?: () => void;
}

export const SovereignToolLauncher: React.FC<SovereignToolLauncherProps> = ({
  runtimeContext = createEmptySovereignToolShortcutContext(),
  onSelect,
  onBlockedSelect,
  activeToolId = null,
  onOpenLauncher,
}) => {
  const [open, setOpen] = useState(false);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const launchTool = useLauncherStore((store) => store.launchTool);
  const inspectionEvidence = useSovereignToolInspectionStore((store) => store.evidence);
  const resolvedRuntimeContext = useMemo(
    () => ({ ...runtimeContext, inspectionEvidence }),
    [inspectionEvidence, runtimeContext],
  );
  const resolvedTools = useMemo(
    () => deriveSovereignToolShortcutGates(resolvedRuntimeContext),
    [open, resolvedRuntimeContext],
  );

  const close = useCallback(() => {
    setOpen(false);
    setFocusedId(null);
  }, []);

  useEffect(() => {
    if (!open) return;
    function onOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) close();
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }

    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      const trigger = containerRef.current?.querySelector('button[aria-haspopup="true"]');
      (trigger as HTMLElement)?.focus();
      return;
    }

    const menuitems = containerRef.current
      ? (Array.from(containerRef.current.querySelectorAll('[role="menuitem"]:not([disabled])')) as HTMLElement[])
      : [];

    if (menuitems.length === 0) return;

    const activeEl = document.activeElement as HTMLElement;
    const currentIndex = menuitems.indexOf(activeEl);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const nextIndex = (currentIndex + 1) % menuitems.length;
      menuitems[nextIndex]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prevIndex =
        currentIndex === -1
          ? menuitems.length - 1
          : (currentIndex - 1 + menuitems.length) % menuitems.length;
      menuitems[prevIndex]?.focus();
    }
  };

  function handleSelect(tool: ToolEntry) {
    if (!tool.canOpen) {
      onBlockedSelect?.(tool.id);
      setOpen(false);
      return;
    }
    onSelect(tool.id);
    if (DIRECT_LAUNCHER_TOOLS.has(tool.id)) launchTool(tool.id);
    setOpen(false);
  }

  const launcherLabel = open ? 'Tool Launcher schließen' : 'Tool Launcher öffnen';

  return (
    <div
      ref={containerRef}
      onKeyDown={handleKeyDown}
      style={{ position: 'relative', display: 'inline-block' }}
      data-testid="sovereign-tool-launcher"
    >
      <button
        type="button"
        aria-label={launcherLabel}
        title={launcherLabel}
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
            width: 244,
            maxHeight: 'min(70vh, 430px)',
            overflowY: 'auto',
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            padding: '6px 0',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            zIndex: 200,
          }}
        >
          {onOpenLauncher && (
            <button
              type="button"
              role="menuitem"
              onClick={() => { onOpenLauncher(); setOpen(false); }}
              title="Alle Tools im Launcher öffnen"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                width: '100%',
                padding: '8px 14px 9px',
                background: focusedId === 'all-tools' ? `${C.accent}20` : `${C.accent}12`,
                border: 'none',
                borderBottom: `1px solid ${C.border}`,
                borderLeft: `2px solid ${C.accent}`,
                cursor: 'pointer',
                textAlign: 'left',
                marginBottom: 4,
                outline: 'none',
              }}
              aria-label="Alle Tools im Launcher öffnen"
              onFocus={() => setFocusedId('all-tools')}
              onBlur={() => setFocusedId(null)}
            >
              <span style={{ fontSize: 13, width: 18, textAlign: 'center', flexShrink: 0, color: C.accent }}>⬡</span>
              <span style={{ fontSize: 13, color: C.accent, fontWeight: 600 }}>Alle Tools</span>
              <span style={{ fontSize: 10, color: C.textSub, marginLeft: 'auto' }}>Launcher →</span>
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
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>Werkzeuge · Runtime-Gates</span>
            <span style={{ fontSize: 8, textTransform: 'none', color: C.accent, fontWeight: 400, opacity: 0.8 }}>
              [↑↓ Navigieren]
            </span>
          </div>
          {resolvedTools.map((tool) => {
            const isActive = tool.id === activeToolId;
            const isFocused = focusedId === tool.id;
            const canExplainBlocker = !tool.canOpen && Boolean(onBlockedSelect);
            const isInteractive = tool.canOpen || canExplainBlocker;
            const tone = tool.canOpen ? (tool.state === 'ready' ? C.accent : C.sky) : C.amber;
            return (
              <button
                key={tool.id}
                type="button"
                role="menuitem"
                disabled={!isInteractive}
                aria-disabled={!isInteractive}
                onClick={() => handleSelect(tool)}
                title={`${tool.label}: ${tool.statusLabel}\n${tool.reason}\n${tool.nextAction}`}
                data-tool-id={tool.id}
                data-gate-state={tool.state}
                data-can-open={tool.canOpen ? 'true' : 'false'}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  width: '100%',
                  padding: '8px 14px',
                  background: isActive || isFocused ? `${C.accent}15` : 'transparent',
                  border: 'none',
                  borderLeft: isActive || isFocused ? `2px solid ${C.accent}` : '2px solid transparent',
                  cursor: isInteractive ? 'pointer' : 'not-allowed',
                  opacity: tool.canOpen ? 1 : 0.68,
                  textAlign: 'left',
                  transition: 'background 0.1s',
                  outline: 'none',
                }}
                aria-current={isActive ? 'true' : undefined}
                aria-label={tool.label}
                onFocus={() => setFocusedId(tool.id)}
                onBlur={() => setFocusedId(null)}
              >
                <span style={{ fontSize: 13, width: 18, textAlign: 'center', flexShrink: 0, color: isActive ? C.accent : C.textSub, marginTop: 1 }}>
                  {tool.icon}
                </span>
                <span style={{ minWidth: 0, flex: 1 }}>
                  <span style={{ display: 'block', fontSize: 13, color: isActive ? C.accent : C.text, fontWeight: isActive ? 500 : 400 }}>
                    {tool.label}
                  </span>
                  <span style={{ display: 'block', marginTop: 2, fontFamily: 'monospace', fontSize: 9, color: tone, lineHeight: 1.25 }}>
                    {tool.statusLabel}
                  </span>
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
