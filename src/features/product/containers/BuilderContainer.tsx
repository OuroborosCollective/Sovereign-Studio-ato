import React, { useMemo, useState } from 'react';
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

interface IdeaPreset {
  readonly title: string;
  readonly description: string;
  readonly mission: string;
}

const IDEA_PRESETS: IdeaPreset[] = [
  {
    title: 'README + Update History',
    description: 'README, Changelog und klare Release-Erklärung erzeugen.',
    mission: 'README + Update History mit klarer Nutzer-Erklärung, echten Repo-Dateien und ohne Preview-only Output.',
  },
  {
    title: 'Runtime + Tests härten',
    description: 'Validierungen, Guards und Tests für einen riskanten Ablauf ergänzen.',
    mission: 'Analysiere den aktuellen Repo-Snapshot und baue Runtime-Checks, Validierungen und passende Unit-Tests für den schwächsten Ablauf.',
  },
  {
    title: 'Fehlerlog reparieren',
    description: 'CI-/Build-/TypeScript-Fehler aus Log in echte Patch-Dateien übersetzen.',
    mission: 'Nutze den aktuellen Fehlerlog, finde die betroffenen Dateien und erstelle einen minimalen, testbaren Fix mit Erklärung.',
  },
  {
    title: 'Operator UX verbessern',
    description: 'Startscreen, Navigation, Monitor, Settings oder Workflow sichtbar nutzbarer machen.',
    mission: 'Verbessere die Operator-UX ohne Mock, ohne Stub und ohne WASD-Drift. Fokus: Klarheit, Mobile, Monitoring und Bedienbarkeit.',
  },
];

function buildCustomMission(baseMission: string, wish: string): string {
  const cleanWish = wish.trim();
  const cleanBase = baseMission.trim() || 'Sovereign Tool Verbesserung';
  if (!cleanWish) return cleanBase;

  return [
    cleanBase,
    '',
    'Individueller Nutzerwunsch:',
    cleanWish,
    '',
    'Bitte als echte Repo-Änderung umsetzen, mit Runtime-Checks, Validierungen und Tests, soweit sinnvoll. Keine Mock-/Stub-/Facade-Live-Pfade.',
  ].join('\n');
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
  const [customWish, setCustomWish] = useState('');
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
  const customMissionPreview = useMemo(() => buildCustomMission(mission, customWish), [mission, customWish]);

  const applyCustomWish = () => {
    onMissionChange(customMissionPreview);
  };

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200" data-testid="builder-container">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-bold">Ideenfabrik · Sovereign Action Builder</h2>
          <p className="mt-1 text-xs text-slate-400">Beschreibe wie in einem Chat, was du willst. Die Ideenfabrik formt daraus einen ausführbaren Sovereign-Auftrag.</p>
        </div>
        <span className={repoReady ? 'rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-200' : 'rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-200'}>
          {repoReady ? 'Repo snapshot ready' : 'Repo snapshot required'}
        </span>
      </div>

      <p className="mt-2 text-xs text-slate-400">{repoReason}</p>
      {state.disabledReason ? <p className="mt-1 text-xs text-amber-300">{state.disabledReason}</p> : null}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {IDEA_PRESETS.map((preset) => (
          <button
            key={preset.title}
            type="button"
            className="rounded border border-slate-800 bg-slate-900/70 p-3 text-left hover:border-cyan-500/40 hover:bg-slate-900"
            onClick={() => onMissionChange(preset.mission)}
          >
            <span className="block font-bold text-slate-100">{preset.title}</span>
            <span className="mt-1 block text-xs text-slate-400">{preset.description}</span>
          </button>
        ))}
      </div>

      <label className="mt-4 block">
        <span className="text-xs font-bold uppercase tracking-wide text-slate-400">Chat-Wunsch / individuelle Anpassung</span>
        <textarea
          className="mt-2 min-h-20 w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
          value={customWish}
          onChange={(event) => setCustomWish(event.target.value)}
          placeholder="Beispiel: Mach daraus eine mobile-first UX, zeige die Logs direkt, prüfe GitHub Actions und baue Tests dazu."
          aria-label="Builder custom wish"
        />
      </label>
      <button className="mt-2" type="button" onClick={applyCustomWish}>Wunsch in Auftrag übernehmen</button>

      <label className="mt-4 block">
        <span className="text-xs font-bold uppercase tracking-wide text-slate-400">Ausführbarer Auftrag</span>
        <textarea
          className="mt-2 min-h-28 w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
          value={mission}
          onChange={(event) => onMissionChange(event.target.value)}
          placeholder="Auftrag, z.B. README + Update History"
          aria-label="Builder mission"
        />
      </label>

      <div className="mt-3 flex flex-wrap gap-2">
        <button onClick={onGenerateIdeas} disabled={generateDisabled} type="button">Vorschlag erzeugen</button>
        <button onClick={onGenerateErrorWorkflow} disabled={generateDisabled} type="button">Fehlerlog reparieren</button>
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
