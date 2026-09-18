import React from 'react';
import { C } from '../builderConstants';
import { ActionSuggestionStrip } from '../ActionSuggestionStrip';
import { SOVEREIGN_PRESET_ACTIONS, type SovereignPresetActionId } from '../../runtime/sovereignPresetActionRuntime';

export interface WorkbenchEmptyStateProps {
  wishText: string;
  effectiveRepoReady: boolean;
  githubWriteAllowed: boolean;
  agentReady: boolean;
  localRepoLoading: boolean;
  chatResponseBusy: boolean;
  isPublishing: boolean;
  onPresetActionSelect: (actionId: SovereignPresetActionId) => void;
}

export function WorkbenchEmptyState({
  wishText,
  effectiveRepoReady,
  githubWriteAllowed,
  agentReady,
  localRepoLoading,
  chatResponseBusy,
  isPublishing,
  onPresetActionSelect,
}: WorkbenchEmptyStateProps): React.ReactElement | null {
  if (wishText.trim()) return null;

  return (
    <div style={{ width: 'min(760px, 100%)', textAlign: 'center' }}>
      <div aria-hidden="true" style={{ fontSize: 30, marginBottom: 8 }}>⬡</div>
      <h2 style={{ margin: 0, color: C.text, fontSize: 20, fontWeight: 650 }}>
        Was möchtest du tun?
      </h2>
      <p style={{ margin: '8px auto 18px', maxWidth: 560, color: C.textSub, fontSize: 13, lineHeight: 1.55 }}>
        Chatte ganz normal mit Sovereign. Modell und Werkzeuge kannst du unten wählen; Agent Zero und die Runtime arbeiten im Hintergrund.
      </p>
      <ActionSuggestionStrip
        actions={SOVEREIGN_PRESET_ACTIONS}
        repoReady={effectiveRepoReady}
        githubWriteReady={githubWriteAllowed}
        agentReady={agentReady}
        disabled={localRepoLoading || chatResponseBusy || isPublishing}
        onSelect={onPresetActionSelect}
      />
    </div>
  );
}
