import React, { useMemo, useState } from 'react';
import {
  builderPublishLabel,
  deriveBuilderContainerState,
} from '../runtime/builderContainerRuntime';
import { getSovereignContainerContract } from '../runtime/sovereignContainerContracts';
import { SOVEREIGN_FORM_MISSION } from '../runtime/sovereignFormContracts';
import {
  SOVEREIGN_ACTION_ANALYZE_MISSION,
  SOVEREIGN_ACTION_START_TASK,
  SOVEREIGN_ACTION_REPAIR_LOG,
  SOVEREIGN_ACTION_DRAFT_PR,
} from '../runtime/sovereignActionContracts';

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

interface IdeaOption {
  readonly label: string;
  readonly text: string;
}

const IDEA_OPTIONS: IdeaOption[] = [
  {
    label: 'README erklären',
    text: 'Erstelle oder verbessere README und Update History so, dass ein normaler Nutzer versteht, was das Tool kann und wie man es benutzt.',
  },
  {
    label: 'Fehlerlog fixen',
    text: 'Analysiere den aktuellen Fehlerlog, finde die betroffenen Dateien und erzeuge einen minimalen echten Fix mit passenden Tests.',
  },
  {
    label: 'UX verbessern',
    text: 'Verbessere die Bedienbarkeit auf Android: Start, Navigation, Monitor, Logs, Settings und klare Nutzerführung.',
  },
  {
    label: 'Runtime härten',
    text: 'Prüfe den schwächsten Ablauf und ergänze Runtime-Checks, Validierungen und Tests ohne Mock-, Stub- oder Facade-Live-Pfade.',
  },
  {
    label: 'PR vorbereiten',
    text: 'Baue einen guarded Draft-PR-Auftrag mit echten Repo-Dateien, Review-Zusammenfassung, Diff-Prüfung und Workflow-Watch.',
  },
];

const builderContainerContract = getSovereignContainerContract('builder');
const primaryButtonClassName = 'sovereign-action-button rounded-2xl border border-cyan-300/40 bg-cyan-500/15 px-4 py-3 text-sm font-black text-cyan-50 shadow-lg shadow-cyan-950/20 disabled:cursor-not-allowed disabled:opacity-45';
const secondaryButtonClassName = 'sovereign-action-button rounded-2xl border border-slate-600 bg-slate-900/80 px-4 py-3 text-sm font-bold text-slate-100 disabled:cursor-not-allowed disabled:opacity-45';
const dangerButtonClassName = 'sovereign-action-button rounded-2xl border border-amber-300/35 bg-amber-500/10 px-4 py-3 text-sm font-bold text-amber-100 disabled:cursor-not-allowed disabled:opacity-45';

function appendOption(current: string, option: IdeaOption): string {
  const clean = current.trim();
  if (!clean) return option.text;
  return `${clean}\n${option.text}`;
}

function buildAnalyzedMission(args: {
  readonly wish: string;
  readonly repoReady: boolean;
  readonly repoReason: string;
}): string {
  const wish = args.wish.trim() || 'Verbessere das Sovereign Tool so, dass es für Nutzer klar bedienbar ist.';
  const repoState = args.repoReady ? 'Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.' : `Repo-Snapshot ist noch nicht bereit: ${args.repoReason}`;

  return [
    'Ideenfabrik Auftrag:',
    wish,
    '',
    'Repository-Kontext:',
    repoState,
    '',
    'Umsetzung:',
    '- Analysiere zuerst die vorhandene Repo-Struktur und betroffene Dateien.',
    '- Erzeuge echte Änderungen im passenden Codepfad.',
    '- Halte Sovereign Tool getrennt von WASD/Science-Portal Drift.',
    '- Nutze Runtime-Checks, Validierungen und Tests, soweit sinnvoll.',
    '- Keine Mock-, Stub- oder Facade-Live-Pfade.',
    '- Gib am Ende klar aus, was geändert wurde und welche Checks noch offen sind.',
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
  const [wishText, setWishText] = useState('');
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
  const analyzedMission = useMemo(() => buildAnalyzedMission({ wish: wishText, repoReady, repoReason }), [repoReady, repoReason, wishText]);

  const analyzeWish = () => {
    onMissionChange(analyzedMission);
  };

  return (
    <section
      className={`${builderContainerContract.rootClass} mt-4 rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-200`}
      data-role={builderContainerContract.dataRole}
      data-testid={builderContainerContract.testId}
      aria-label={builderContainerContract.ariaLabel}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-black">Ideenfabrik · Chat Auftrag</h2>
          <p className="mt-1 text-xs text-slate-400">Schritt 2: Wunsch eintragen, Auftrag analysieren und danach Auftrag starten.</p>
        </div>
        <span className={repoReady ? 'rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-200' : 'rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-200'}>
          {repoReady ? 'Repo snapshot ready' : 'Repo snapshot required'}
        </span>
      </div>

      <div className="mt-4 grid gap-2 text-xs sm:grid-cols-3">
        <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-3 text-emerald-100">1 · Repo ist die Quelle</div>
        <div className="rounded-xl border border-cyan-400/20 bg-cyan-500/10 p-3 text-cyan-100">2 · Auftrag analysieren</div>
        <div className="rounded-xl border border-indigo-400/20 bg-indigo-500/10 p-3 text-indigo-100">3 · Auftrag starten</div>
      </div>

      <p className="mt-3 text-xs text-slate-400">{repoReason}</p>
      {state.disabledReason ? <p className="mt-1 text-xs text-amber-300">{state.disabledReason}</p> : null}

      <div className="mt-4 flex flex-wrap gap-2" aria-label="Ideenfabrik Optionen">
        {IDEA_OPTIONS.map((option) => (
          <button
            key={option.label}
            type="button"
            className="rounded-full border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100 hover:border-cyan-400/60"
            onClick={() => setWishText((current) => appendOption(current, option))}
          >
            {option.label}
          </button>
        ))}
      </div>

      <label className="mt-4 block">
        <span className="text-xs font-bold uppercase tracking-wide text-slate-400">{SOVEREIGN_FORM_MISSION.label}</span>
        <textarea
          id={SOVEREIGN_FORM_MISSION.id}
          name={SOVEREIGN_FORM_MISSION.id}
          data-role={SOVEREIGN_FORM_MISSION.dataRole}
          data-testid={SOVEREIGN_FORM_MISSION.testId}
          className="mt-2 min-h-28 w-full rounded-xl border border-slate-700 bg-slate-900 p-3 text-base leading-6"
          value={wishText}
          onChange={(event) => setWishText(event.target.value)}
          placeholder="Schreib einfach: mach die App verständlicher, zeig Logs, prüfe Buildfehler, mach einen Draft PR..."
          aria-label={SOVEREIGN_FORM_MISSION.ariaLabel}
        />
      </label>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          className={secondaryButtonClassName}
          type="button"
          onClick={analyzeWish}
          data-role={SOVEREIGN_ACTION_ANALYZE_MISSION.dataRole}
          data-testid={SOVEREIGN_ACTION_ANALYZE_MISSION.testId}
          aria-label={SOVEREIGN_ACTION_ANALYZE_MISSION.ariaLabel}
          data-state={generateDisabled ? 'disabled' : 'idle'}
        >
          2 · {SOVEREIGN_ACTION_ANALYZE_MISSION.label}
        </button>
        <button
          className={primaryButtonClassName}
          onClick={onGenerateIdeas}
          disabled={generateDisabled}
          type="button"
          data-role={SOVEREIGN_ACTION_START_TASK.dataRole}
          data-testid={SOVEREIGN_ACTION_START_TASK.testId}
          aria-label={SOVEREIGN_ACTION_START_TASK.ariaLabel}
          data-state={generateDisabled ? 'disabled' : 'idle'}
        >
          3 · {SOVEREIGN_ACTION_START_TASK.label}
        </button>
        <button
          className={dangerButtonClassName}
          onClick={onGenerateErrorWorkflow}
          disabled={generateDisabled}
          type="button"
          data-role={SOVEREIGN_ACTION_REPAIR_LOG.dataRole}
          data-testid={SOVEREIGN_ACTION_REPAIR_LOG.testId}
          aria-label={SOVEREIGN_ACTION_REPAIR_LOG.ariaLabel}
          data-state={generateDisabled ? 'disabled' : 'idle'}
        >
          {SOVEREIGN_ACTION_REPAIR_LOG.label}
        </button>
        <button
          className={secondaryButtonClassName}
          onClick={onPublishDraftPr}
          disabled={publishDisabled}
          type="button"
          data-role={SOVEREIGN_ACTION_DRAFT_PR.dataRole}
          data-testid={SOVEREIGN_ACTION_DRAFT_PR.testId}
          aria-label={SOVEREIGN_ACTION_DRAFT_PR.ariaLabel}
          data-state={publishDisabled ? 'disabled' : 'idle'}
        >
          {builderPublishLabel(isPublishing)}
        </button>
      </div>

      <label className="mt-4 block">
        <span className="text-xs font-bold uppercase tracking-wide text-slate-400">Analysierter ausführbarer Auftrag</span>
        <textarea
          className="mt-2 min-h-36 w-full rounded-xl border border-slate-700 bg-slate-900 p-3 text-sm leading-6"
          value={mission}
          onChange={(event) => onMissionChange(event.target.value)}
          placeholder="Hier erscheint nach Analyse der ausführbare Auftrag. Du kannst ihn vor Produktion noch ändern."
          aria-label="Builder mission"
        />
      </label>

      <pre className="mt-3 whitespace-pre-wrap rounded-xl bg-black/40 p-3 text-xs text-slate-300">{sovereignSummary}</pre>
      {state.hasPreview ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400">Brain preview</summary>
          <pre className="mt-2 max-h-96 overflow-auto rounded-xl bg-black/40 p-3 text-[11px] text-slate-300">{sovereignPreview}</pre>
        </details>
      ) : null}
    </section>
  );
}
