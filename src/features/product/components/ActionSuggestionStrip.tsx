import React from 'react';
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
  return (
    <section
      aria-label="Sovereign Vorschläge"
      data-testid="sovereign-action-suggestion-strip"
      style={{
        padding: '8px 10px 6px',
        background: C.bg,
        borderTop: `1px solid ${C.border}`,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          marginBottom: 6,
        }}
      >
        <span style={{ fontFamily: 'monospace', fontSize: 9, color: C.textMuted }}>
          Geführte Repo-Aktionen
        </span>
        <span style={{ fontFamily: 'monospace', fontSize: 8, color: C.textMuted }}>
          {repoReady ? 'Repo bereit' : 'Repo fehlt'}
        </span>
      </div>
      <div
        role="list"
        style={{
          display: 'flex',
          gap: 8,
          overflowX: 'auto',
          WebkitOverflowScrolling: 'touch',
          paddingBottom: 2,
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
                  minWidth: 138,
                  maxWidth: 178,
                  border: `1px solid ${gate.canStart ? C.border : `${C.amber}55`}`,
                  borderRadius: 14,
                  background: disabled ? '#10151c' : C.surface,
                  color: C.text,
                  padding: '10px 10px',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  textAlign: 'left',
                  opacity: disabled ? 0.55 : 1,
                  width: '100%',
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                  <span aria-hidden="true">{action.icon}</span>
                  <span style={{ fontFamily: 'monospace', fontSize: 10, fontWeight: 800, color: tone }}>
                    {action.shortLabel}
                  </span>
                </span>
                <span style={{ display: 'block', fontSize: 10.5, lineHeight: 1.25, color: C.textSub }}>
                  {action.label}
                </span>
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
