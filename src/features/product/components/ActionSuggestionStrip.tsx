import React, { useState } from 'react';
import type { SovereignPresetAction, SovereignPresetActionId } from '../runtime/sovereignPresetActionRuntime';
import { evaluateSovereignPresetActionGate } from '../runtime/sovereignPresetActionRuntime';
import { C } from './builderConstants';

export interface ActionSuggestionStripProps {
  readonly actions: readonly SovereignPresetAction[];
  readonly repoReady: boolean;
  readonly githubWriteReady: boolean;
  readonly agentReady: boolean;
  readonly disabled?: boolean;
  readonly onSelect: (actionId: SovereignPresetActionId) => void;
}

export function ActionSuggestionStrip({
  actions,
  repoReady,
  githubWriteReady,
  agentReady,
  disabled = false,
  onSelect,
}: ActionSuggestionStripProps): React.ReactElement {
  const [expanded, setExpanded] = useState(false);

  return (
    <section
      aria-label="Sovereign Vorschläge"
      data-testid="sovereign-action-suggestion-strip"
      data-expanded={expanded ? 'true' : 'false'}
      style={{
        background: C.bg,
        borderTop: `1px solid ${C.border}`,
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-controls="sovereign-guided-actions"
        style={{
          width: '100%',
          minHeight: 34,
          padding: '5px 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          border: 'none',
          background: C.bg,
          color: C.textMuted,
          cursor: 'pointer',
        }}
      >
        <span style={{ fontFamily: 'monospace', fontSize: 9 }}>
          {expanded ? '▾' : '▸'} Geführte Repo-Aktionen
        </span>
        <span style={{ fontFamily: 'monospace', fontSize: 8 }}>
          {repoReady ? 'Repo bereit' : 'Repo fehlt'}
        </span>
      </button>

      {expanded && (
        <div
          id="sovereign-guided-actions"
          role="list"
          style={{
            display: 'flex',
            gap: 8,
            overflowX: 'auto',
            WebkitOverflowScrolling: 'touch',
            padding: '4px 10px 8px',
          }}
        >
          {actions.map((action) => {
            const gate = evaluateSovereignPresetActionGate(action, {
              repoReady,
              githubWriteReady,
              agentReady,
            });
            const tone = gate.canStart ? C.accent : C.amber;
            return (
              <div key={action.id} role="listitem" style={{ flexShrink: 0 }}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onSelect(action.id)}
                  aria-label={`${action.label}: ${action.description}`}
                  title={`${action.description}\n${gate.canStart ? gate.nextAction : `${gate.reason} ${gate.nextAction}`}`}
                  style={{
                    minWidth: 132,
                    maxWidth: 170,
                    border: `1px solid ${gate.canStart ? C.border : `${C.amber}55`}`,
                    borderRadius: 12,
                    background: disabled ? '#10151c' : C.surface,
                    color: C.text,
                    padding: '8px 9px',
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    textAlign: 'left',
                    opacity: disabled ? 0.55 : 1,
                    width: '100%',
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <span aria-hidden="true">{action.icon}</span>
                    <span style={{ fontFamily: 'monospace', fontSize: 10, fontWeight: 800, color: tone }}>
                      {action.shortLabel}
                    </span>
                  </span>
                  <span style={{ display: 'block', fontSize: 10, lineHeight: 1.25, color: C.textSub }}>
                    {action.label}
                  </span>
                </button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
