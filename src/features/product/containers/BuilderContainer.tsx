import React from 'react';
import {
  builderPublishLabel,
  deriveBuilderContainerState,
} from '../runtime/builderContainerRuntime';

export interface BuilderContainerProps {
  mission: string;
  repoReady: boolean;
  repoReason: string;
  repoBusy: boolean;
  runtimeBusy: boolean;
  isPublishing: boolean;
  sovereignSummary: string;
  sovereignPreview: string;
  onMissionChange: (mission: string) => void;
  onGenerateIdeas: () => void;
  onGenerateErrorWorkflow: () => void;
  onPublishDraftPr: () => void;
}

export function BuilderContainer({
  mission,
  repoReady,
  repoReason,
  repoBusy,
  runtimeBusy,
  isPublishing,
  sovereignSummary,
  sovereignPreview,
  onMissionChange,
  onGenerateIdeas,
  onGenerateErrorWorkflow,
  onPublishDraftPr,
}: BuilderContainerProps) {
  const state = deriveBuilderContainerState({
    repoReady,
    repoBusy,
    runtimeBusy,
    isPublishing,
    mission,
    sovereignSummary,
    sovereignPreview,
  });
  const generateDisabled = !state.canGenerate;
  const publishDisabled = !state.canPublish;

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200" data-testid="builder-container">
      <h2 className="font-bold">Sovereign Action Builder</h2>
      <p className="mt-1 text-xs text-slate-400">{repoReason}</p>
      {state.disabledReason ? <p className="mt-1 text-xs text-amber-300">{state.disabledReason}</p> : null}
      <textarea
        className="mt-2 min-h-24 w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
        value={mission}
        onChange={(event) => onMissionChange(event.target.value)}
        placeholder="Auftrag, z.B. README + Update History"
        aria-label="Builder mission"
      />
      <div className="mt-2 flex flex-wrap gap-2">
        <button onClick={onGenerateIdeas} disabled={generateDisabled} type="button">Ideen</button>
        <button onClick={onGenerateErrorWorkflow} disabled={generateDisabled} type="button">Fehler</button>
        <button onClick={onPublishDraftPr} disabled={publishDisabled} type="button">
          {builderPublishLabel(isPublishing)}
        </button>
      </div>
      <pre className="mt-3 whitespace-pre-wrap rounded bg-black/40 p-3 text-xs text-slate-300">{sovereignSummary}</pre>
      {state.hasPreview ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400">Brain preview</summary>
          <pre className="mt-2 max-h-96 overflow-auto rounded bg-black/40 p-3 text-[11px] text-slate-300">{sovereignPreview}</pre>
        </details>
      ) : null}
    </section>
  );
}
