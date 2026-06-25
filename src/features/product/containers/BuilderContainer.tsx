import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
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
import { formatCuteThinkingLabel } from '../runtime/cuteThinkingStatus';
import type { OpenHandsJobSnapshot } from '../runtime/openhandsEnterpriseRuntime';
import type { PredictiveLayerSnapshot } from '../../predictive/types';
import type { SolutionPatternStore } from '../runtime/solutionPatternMemory';
import { derivePredictiveSuggestions, deriveChatPredictiveContext } from '../runtime/chatPredictiveIntegration';
import type { Suggestion } from '../types';

type WorkbenchPane = 'planner' | 'changes' | 'code' | 'terminal' | 'browser';

const WORKBENCH_PANES = [
  { id: 'planner' as const, label: 'Planner', icon: '☷' },
  { id: 'changes' as const, label: 'Changes', icon: '☑' },
  { id: 'code' as const, label: 'Code', icon: '</>' },
  { id: 'terminal' as const, label: 'Terminal', icon: '▻' },
  { id: 'browser' as const, label: 'Browser', icon: '◎' },
] as const;

function paneHelpText(pane: WorkbenchPane): string {
  if (pane === 'planner') return 'Planung bleibt im Chat: Auftrag verstehen, Repo prüfen, Stopper erklären.';
  if (pane === 'changes') return 'Änderungen erscheinen als ruhige Hinweise. Details bleiben im Files/Diff-Menü.';
  if (pane === 'code') return 'Code-Kontext wird von der Runtime genutzt; die UI erzeugt keinen Code selbst.';
  if (pane === 'terminal') return 'Terminal und Logs sind nur lesende Diagnoseflächen, nicht die Hauptbedienung.';
  return 'Browser/Preview bleibt optionaler Inspektor, nicht der Hauptablauf.';
}

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
  openhandsReady?: boolean;
  openhandsJob?: OpenHandsJobSnapshot;
  openhandsJobStatus?: string;
  openhandsIsRunning?: boolean;
  onStartOpenHands?: (mission: string) => void;
  onCancelOpenHands?: () => void;
  /** Predictive layer snapshot for intelligent suggestions */
  predictiveSnapshot?: PredictiveLayerSnapshot | null;
  /** Solution pattern store from learning */
  patternStore?: SolutionPatternStore | null;
  /** @deprecated Internal pane state - kept for minimal backward compat */
  _activePane?: WorkbenchPane;
}

interface IdeaOption {
  readonly label: string;
  readonly text: string;
}

interface ChatOutcomeHint {
  readonly kind: 'runtime' | 'files' | 'draft-pr' | 'stopper' | 'done';
  readonly text: string;
  readonly href?: string;
}

const CUTE_THINKING_FRAME_MS = 1100;

const IDEA_OPTIONS: IdeaOption[] = [
  {
    label: 'Cooles Feature',
    text: 'Schlage mir ein kleines, cooles Feature vor, prüfe zuerst das Repo und baue es nur als echten, sicheren Draft-PR-tauglichen Änderungspfad.',
  },
  {
    label: 'Fehler fixen',
    text: 'Analysiere den aktuellen Fehlerstatus, finde die betroffenen Dateien und erzeuge einen minimalen echten Fix mit passenden Tests.',
  },
  {
    label: 'Android UX',
    text: 'Verbessere die Bedienbarkeit auf Android: Chat, Navigation, Statushinweise und klare Nutzerführung ohne neue Fensterflut.',
  },
  {
    label: 'Runtime härten',
    text: 'Prüfe den schwächsten Ablauf und ergänze Runtime-Checks, Validierungen und Tests ohne Mock-, Stub- oder Facade-Live-Pfade.',
  },
  {
    label: 'README erklären',
    text: 'Verbessere README oder Dokumentation so, dass normale Nutzer verstehen, was das Tool kann und wie man es benutzt.',
  },
];

const builderContainerContract = getSovereignContainerContract('builder');
const primaryButtonClassName = 'sovereign-action-button rounded-2xl border border-cyan-300/40 bg-cyan-500/15 px-4 py-3 text-sm font-black text-cyan-50 shadow-lg shadow-cyan-950/20 disabled:cursor-not-allowed disabled:opacity-45';
const secondaryButtonClassName = 'sovereign-action-button rounded-2xl border border-slate-600 bg-slate-900/80 px-4 py-3 text-sm font-bold text-slate-100 disabled:cursor-not-allowed disabled:opacity-45';
const dangerButtonClassName = 'sovereign-action-button rounded-2xl border border-amber-300/35 bg-amber-500/10 px-4 py-3 text-sm font-bold text-amber-100 disabled:cursor-not-allowed disabled:opacity-45';

function appendOption(current: string, option: IdeaOption): string {
  const clean = current.trim();
  if (!clean) return option.text;
  if (clean.includes(option.text)) return clean;
  return `${clean}\n${option.text}`;
}

function normalizeMissionText(value: string): string {
  return value.replace(/\r\n/g, '\n').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}

function collapseRepeatedAnalyzedMission(value: string): string {
  let clean = normalizeMissionText(value).replace(/^Ideenfabrik Auftrag:\s*Ideenfabrik Auftrag:/i, 'Ideenfabrik Auftrag:');
  const marker = '\nRepository-Kontext:';
  const firstContext = clean.indexOf(marker);
  const secondContext = firstContext >= 0 ? clean.indexOf(marker, firstContext + marker.length) : -1;
  if (secondContext >= 0) clean = clean.slice(0, secondContext).trim();
  return clean;
}

function isAnalyzedMission(value: string): boolean {
  const clean = collapseRepeatedAnalyzedMission(value).toLowerCase();
  return clean.startsWith('ideenfabrik auftrag:') && clean.includes('repository-kontext:') && clean.includes('umsetzung:');
}

function missionToWishText(value: string): string {
  const clean = collapseRepeatedAnalyzedMission(value);
  if (!clean) return '';
  if (!isAnalyzedMission(clean)) return clean.replace(/^Ideenfabrik Auftrag:\s*/i, '').trim();

  const withoutHeader = clean.replace(/^Ideenfabrik Auftrag:\s*/i, '').trim();
  const contextIndex = withoutHeader.indexOf('\nRepository-Kontext:');
  return (contextIndex >= 0 ? withoutHeader.slice(0, contextIndex) : withoutHeader).trim();
}

function buildAnalyzedMission(args: {
  readonly wish: string;
  readonly repoReady: boolean;
  readonly repoReason: string;
}): string {
  const existingMission = collapseRepeatedAnalyzedMission(args.wish);
  if (isAnalyzedMission(existingMission)) return existingMission;

  const wish = missionToWishText(args.wish) || 'Verbessere das Sovereign Tool so, dass es für Nutzer klar bedienbar ist.';
  const repoState = args.repoReady ? 'Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.' : `Repo-Snapshot ist noch nicht bereit: ${args.repoReason}`;

  return [
    'Ideenfabrik Auftrag:',
    wish,
    '',
    'Repository-Kontext:',
    repoState,
    '',
    'Umsetzung:',
    '- Antworte wie ein hilfreicher No-Code-Freund: kurz, freundlich und handlungsorientiert.',
    '- Analysiere zuerst die vorhandene Repo-Struktur und betroffene Dateien.',
    '- Erzeuge echte Änderungen im passenden Codepfad oder erkläre klar, warum ein Stop-Gate blockiert.',
    '- Nutze vorhandene Pattern Memory Hinweise, wenn sie passen.',
    '- Halte Sovereign Tool getrennt von WASD/Science-Portal Drift.',
    '- Nutze Runtime-Checks, Validierungen und Tests, soweit sinnvoll.',
    '- Keine Mock-, Stub- oder Facade-Live-Pfade.',
    '- Kein Auto-Merge. Ergebnis nur als prüfbarer Draft PR oder klarer Blocker.',
  ].join('\n');
}

function safeHttpsUrl(value: string | undefined): string | undefined {
  const clean = value?.trim();
  return clean && clean.startsWith('https://') ? clean : undefined;
}

function buildOutcomeHints(job: OpenHandsJobSnapshot | undefined): ChatOutcomeHint[] {
  if (!job || job.status === 'idle') return [];
  const hints: ChatOutcomeHint[] = [];
  const files = (job.changedFiles ?? []).filter((file) => typeof file === 'string' && file.trim()).map((file) => file.trim());
  const draftPrUrl = safeHttpsUrl(job.draftPrUrl);

  if (job.openHandsId?.trim()) {
    hints.push({ kind: 'runtime', text: `🐤 OpenHands Runtime-ID: ${job.openHandsId.trim()}` });
  }

  if (files.length > 0) {
    hints.push({ kind: 'files', text: `${files.length} Datei(en) geändert · Details im Files-Menü` });
  }

  if (draftPrUrl) {
    hints.push({ kind: 'draft-pr', text: 'Draft PR bereit · Öffnen', href: draftPrUrl });
  }

  if ((job.status === 'blocked' || job.status === 'failed') && job.lastError?.trim()) {
    hints.push({ kind: 'stopper', text: job.lastError.trim() });
  }

  if (job.status === 'completed' && files.length === 0 && !draftPrUrl) {
    hints.push({ kind: 'done', text: 'Küken hat fertig gepiepst · Keine Dateiänderung gemeldet' });
  }

  return hints;
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
  openhandsReady,
  openhandsJob,
  openhandsJobStatus,
  openhandsIsRunning,
  onStartOpenHands,
  onCancelOpenHands,
  predictiveSnapshot,
  patternStore,
  _activePane: initialPane = 'changes',
}: BuilderContainerProps) {
  const [wishText, setWishText] = useState(() => missionToWishText(mission));
  const [activePane, setActivePane] = useState<WorkbenchPane>(initialPane);
  const [thinkingFrameIndex, setThinkingFrameIndex] = useState(0);
  const [predictiveSuggestions, setPredictiveSuggestions] = useState<Suggestion[]>([]);
  const lastMissionSeenRef = useRef(mission);
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
  const executableOpenHandsMission = useMemo(() => {
    const visibleMission = collapseRepeatedAnalyzedMission(mission);
    return isAnalyzedMission(visibleMission) ? visibleMission : collapseRepeatedAnalyzedMission(analyzedMission);
  }, [analyzedMission, mission]);
  const runtimeThinkingActive = Boolean(openhandsIsRunning || repoBusy || runtimeBusy || isPublishing);
  const cuteThinkingLabel = useMemo(() => formatCuteThinkingLabel({
    index: thinkingFrameIndex,
    active: runtimeThinkingActive,
    status: openhandsJobStatus,
  }), [openhandsJobStatus, runtimeThinkingActive, thinkingFrameIndex]);
  const outcomeHints = useMemo(() => buildOutcomeHints(openhandsJob), [openhandsJob]);
  const agentDisabled = !repoReady || repoBusy || runtimeBusy || Boolean(openhandsIsRunning) || !openhandsReady || !onStartOpenHands;

  // Predictive context for runtime intelligence display
  const predictiveContext = useMemo(() => deriveChatPredictiveContext(
    predictiveSnapshot || null,
    patternStore || null,
    { repoReady, openhandsReady: !!openhandsReady, runtimeBusy }
  ), [predictiveSnapshot, patternStore, repoReady, openhandsReady, runtimeBusy]);

  // Derive predictive suggestions when input changes
  useEffect(() => {
    if (wishText.trim()) {
      const suggestions = derivePredictiveSuggestions(
        wishText,
        predictiveSnapshot || null,
        patternStore || null
      );
      setPredictiveSuggestions(suggestions);
    } else {
      setPredictiveSuggestions([]);
    }
  }, [wishText, predictiveSnapshot, patternStore]);

  useEffect(() => {
    if (!runtimeThinkingActive) {
      setThinkingFrameIndex(0);
      return undefined;
    }

    const handle = window.setInterval(() => {
      setThinkingFrameIndex((current) => current + 1);
    }, CUTE_THINKING_FRAME_MS);

    return () => window.clearInterval(handle);
  }, [runtimeThinkingActive]);

  useEffect(() => {
    if (mission === lastMissionSeenRef.current) return;
    lastMissionSeenRef.current = mission;
    setWishText(missionToWishText(mission));
  }, [mission]);

  const analyzeWish = () => {
    const cleanMission = collapseRepeatedAnalyzedMission(analyzedMission);
    lastMissionSeenRef.current = cleanMission;
    onMissionChange(cleanMission);
  };

  const startAgentFromChat = () => {
    const cleanMission = collapseRepeatedAnalyzedMission(executableOpenHandsMission);
    lastMissionSeenRef.current = cleanMission;
    onMissionChange(cleanMission);
    onStartOpenHands?.(cleanMission);
  };

  const handleComposerSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (agentDisabled) {
      analyzeWish();
      return;
    }
    startAgentFromChat();
  };

  const agentStatusLabel = openhandsReady ? cuteThinkingLabel : '🌙 Agent noch nicht verbunden';

  return (
    <section
      className={`${builderContainerContract.rootClass} sovereign-builder-compact mt-4 overflow-hidden rounded-3xl border border-cyan-400/25 bg-[#090c10] text-sm text-slate-200 shadow-2xl shadow-cyan-950/10`}
      data-role={builderContainerContract.dataRole}
      data-testid={builderContainerContract.testId}
      aria-label={builderContainerContract.ariaLabel}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-slate-800/80 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="text-2xl" aria-hidden="true">🐤🐣</div>

          <button
            type="button"
            className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-700 bg-slate-950 text-3xl leading-none text-slate-100"
            aria-label="Neue Chat Aufgabe"
            onClick={() => setWishText('')}
          >
            +
          </button>

          <details className="relative">
            <summary
              className="inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-full border border-slate-700 bg-slate-950 text-xl text-slate-100"
              aria-label="Sovereign Menü"
            >
              ☰
            </summary>
            <div className="absolute left-0 z-20 mt-2 w-64 rounded-2xl border border-slate-700 bg-slate-900 p-3 text-sm shadow-2xl">
              <p className="font-black text-slate-100">Sovereign Menüs</p>
              <p className="mt-1 text-xs text-slate-400">
                Repo, Files, Diff, Workflow, Repair, Pattern Memory, Remote Memory,
                Telemetry und Health bleiben als leise Inspektoren erreichbar.
              </p>
            </div>
          </details>
        </div>

        <div className="text-right text-xs">
          <p className="font-black uppercase tracking-[0.24em] text-cyan-200">No-Code Chat</p>
          <p className="mt-1 text-slate-400">
            {repoReady ? 'Repo verbunden' : 'Repo zuerst verbinden'} · {runtimeThinkingActive ? 'Running task' : 'Waiting for task'}
          </p>
        </div>
      </div>

      {/* Status Bar */}
      <div className="px-4 pt-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-300" aria-hidden="true" />
          <h2 className="text-lg font-black text-slate-50">Sovereign Chat</h2>
          <span className="rounded-full border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400">
            OpenHands Runtime
          </span>
          <span className="rounded-full border border-purple-400/30 bg-purple-500/10 px-2 py-1 text-xs text-purple-100" aria-live="polite">
            {agentStatusLabel}
          </span>
        </div>

        {/* Workbench Tabs */}
        <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Sovereign Arbeitsbereiche">
          {WORKBENCH_PANES.map((pane) => (
            <button
              key={pane.id}
              type="button"
              aria-pressed={activePane === pane.id}
              className={
                activePane === pane.id
                  ? 'rounded-full border border-cyan-300/50 bg-slate-800 px-3 py-2 text-sm font-bold text-slate-50'
                  : 'rounded-full border border-transparent bg-transparent px-3 py-2 text-sm font-bold text-slate-400'
              }
              onClick={() => setActivePane(pane.id)}
            >
              <span className="mr-1 text-slate-300">{pane.icon}</span>
              {pane.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">{paneHelpText(activePane)}</p>
      </div>

      {/* Chat Stream / Empty State */}
      <div className="min-h-[22rem] px-4 py-8" aria-label="Sovereign Chat Verlauf">
        {!wishText.trim() ? (
          <div className="mx-auto flex max-w-3xl flex-col items-center justify-center py-10 text-center">
            <div className="text-6xl" aria-hidden="true">🐥</div>
            <p className="mt-4 text-3xl font-black text-slate-50">Let's start building!</p>
            <p className="mt-3 max-w-xl text-sm text-slate-400">
              Schreib einfach, was du gebaut haben möchtest. Repo, Runtime, Patterns,
              Logs und Checks laufen im Hintergrund und melden nur echte Stopper.
            </p>

            {/* Quick Suggestions */}
            <div className="mt-6 grid w-full gap-3 sm:grid-cols-2" aria-label="Schnellvorschläge">
              {IDEA_OPTIONS.slice(0, 4).map((option) => (
                <button
                  key={option.label}
                  type="button"
                  className="rounded-2xl border border-slate-700 bg-transparent px-4 py-4 text-left text-sm font-bold text-slate-100 hover:border-cyan-400/60"
                  onClick={() => setWishText((current) => appendOption(current, option))}
                >
                  {option.label}
                </button>
              ))}
            </div>

            {/* Predictive Suggestions from Runtime Intelligence */}
            {predictiveSuggestions.length > 0 && (
              <div className="mt-4 border-t border-slate-800 pt-4" aria-label="Prädiktive Vorschläge">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs text-purple-400">🧠 Runtime Intelligence</span>
                  {predictiveContext.hasPatterns && (
                    <span className="rounded-full border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-200">
                      {patternStore?.patterns.length || 0} Patterns
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {predictiveSuggestions.map((suggestion) => (
                    <button
                      key={suggestion.id}
                      type="button"
                      onClick={() => setWishText((current) => appendOption(current, { label: suggestion.title, text: suggestion.description }))}
                      className="rounded-full border border-purple-500/30 bg-purple-500/10 px-3 py-1.5 text-xs text-purple-100 hover:border-purple-400/60"
                    >
                      {suggestion.title}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-6">
            {/* User Message */}
            <div className="ml-auto max-w-[86%] rounded-3xl rounded-tr-sm bg-slate-700/80 px-4 py-3 text-slate-50">
              <p className="whitespace-pre-wrap">{wishText}</p>
            </div>

            {/* System Response */}
            <div className="max-w-[92%] text-slate-100">
              <p className="whitespace-pre-wrap">
                {repoReady
                  ? 'Ich prüfe dein Repo, suche passende Runtime-/Pattern-Hinweise und starte nur echte Agentenarbeit.'
                  : repoReason}
              </p>

              {runtimeThinkingActive ? (
                <p className="mt-4 inline-flex rounded-full bg-slate-800 px-4 py-2 text-sm text-slate-200">
                  ••• {cuteThinkingLabel}
                </p>
              ) : null}

              {sovereignSummary ? <p className="mt-4 text-slate-300">{sovereignSummary}</p> : null}
              {state.disabledReason ? <p className="mt-3 text-amber-300">{state.disabledReason}</p> : null}

              {outcomeHints.length > 0 ? (
                <div className="mt-4 space-y-1 text-xs" aria-label="OpenHands Ergebnis-Hinweise" data-testid="sovereign-chat-outcome-hints">
                  {outcomeHints.map((hint) => (
                    <p key={`${hint.kind}:${hint.text}`} data-outcome-hint-kind={hint.kind}>
                      {hint.href ? (
                        <a className="underline underline-offset-4" href={hint.href} target="_blank" rel="noreferrer">
                          {hint.text}
                        </a>
                      ) : hint.text}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>

      {/* Sticky Composer */}
      <form className="sticky bottom-0 border-t border-slate-800/80 bg-[#090c10] p-4" onSubmit={handleComposerSubmit}>
        <div className="rounded-3xl border border-slate-700 bg-slate-800/95 p-3 shadow-2xl shadow-black/30">
          <div className="flex items-start gap-3">
            <span className="pt-3 text-2xl text-slate-300" aria-hidden="true">📎</span>

            <textarea
              id={SOVEREIGN_FORM_MISSION.id}
              name={SOVEREIGN_FORM_MISSION.id}
              data-role={SOVEREIGN_FORM_MISSION.dataRole}
              data-testid={SOVEREIGN_FORM_MISSION.testId}
              className="min-h-16 flex-1 resize-none border-0 bg-transparent p-2 text-base leading-6 text-slate-50 outline-none placeholder:text-slate-400"
              value={wishText}
              onChange={(event) => setWishText(event.target.value)}
              placeholder="What do you want to build?"
              aria-label={SOVEREIGN_FORM_MISSION.ariaLabel}
            />

            <button
              className="mt-1 inline-flex h-12 w-12 items-center justify-center rounded-full border border-slate-300/60 bg-slate-950 text-2xl text-slate-50 disabled:opacity-45"
              type="submit"
              disabled={agentDisabled}
              data-role={SOVEREIGN_ACTION_START_TASK.dataRole}
              data-testid={SOVEREIGN_ACTION_START_TASK.testId}
              aria-label="Agent starten"
              data-state={agentDisabled ? 'disabled' : 'idle'}
            >
              ↑
            </button>
          </div>

          {/* Tool Chips */}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-300">
            <span className="rounded-full px-2 py-1 font-bold">🛠 Tools</span>
            <span className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1">&lt;/&gt; Code</span>
            <span className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1">🐤 OpenHands</span>
            <span className="ml-auto rounded-full px-3 py-1 text-slate-300">
              {runtimeThinkingActive ? 'Running task' : 'Waiting for task'} ◷
            </span>
          </div>
        </div>

        {/* Repo Shortcuts */}
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1 text-xs" aria-label="Repository Kurzbefehle">
          <span className="shrink-0 rounded-full border border-slate-700 bg-slate-950 px-3 py-2">
            ⌘ {repoReady ? 'Repo verbunden' : 'Repo fehlt'}
          </span>
          <span className="shrink-0 rounded-full border border-slate-700 bg-slate-950 px-3 py-2">⑂ main</span>
          <span className="shrink-0 rounded-full border border-slate-700 bg-slate-950 px-3 py-2">↓ Pull</span>
          <span className="shrink-0 rounded-full border border-slate-700 bg-slate-950 px-3 py-2">↑ Push</span>
          <span className="shrink-0 rounded-full border border-slate-700 bg-slate-950 px-3 py-2">⑂ Pull Request</span>
        </div>

        {/* Analyze Button */}
        <div className="mt-3">
          {openhandsIsRunning ? (
            <button className={dangerButtonClassName} onClick={onCancelOpenHands} type="button">
              Agent stoppen
            </button>
          ) : (
            <button
              className={secondaryButtonClassName}
              type="button"
              onClick={analyzeWish}
              data-role={SOVEREIGN_ACTION_ANALYZE_MISSION.dataRole}
              data-testid={SOVEREIGN_ACTION_ANALYZE_MISSION.testId}
              aria-label={SOVEREIGN_ACTION_ANALYZE_MISSION.ariaLabel}
            >
              Auftrag vorbereiten
            </button>
          )}
        </div>
      </form>

      {/* Hidden Tools Inspector */}
      <details className="border-t border-slate-800 bg-slate-950/70 p-4">
        <summary className="cursor-pointer text-xs font-black uppercase tracking-wide text-slate-400">
          Werkzeuge, Diagnose und Draft PR
        </summary>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <button
            className={secondaryButtonClassName}
            onClick={onGenerateIdeas}
            disabled={generateDisabled}
            type="button"
            aria-label="Interne Paketprüfung starten"
          >
            Interne Prüfung
          </button>
          <button
            className={dangerButtonClassName}
            onClick={onGenerateErrorWorkflow}
            disabled={generateDisabled}
            type="button"
            data-role={SOVEREIGN_ACTION_REPAIR_LOG.dataRole}
            data-testid={SOVEREIGN_ACTION_REPAIR_LOG.testId}
            aria-label={SOVEREIGN_ACTION_REPAIR_LOG.ariaLabel}
          >
            Fehleranalyse
          </button>
          <button
            className={secondaryButtonClassName}
            onClick={onPublishDraftPr}
            disabled={publishDisabled}
            type="button"
            data-role={SOVEREIGN_ACTION_DRAFT_PR.dataRole}
            data-testid={SOVEREIGN_ACTION_DRAFT_PR.testId}
            aria-label={builderPublishLabel(isPublishing)}
          >
            {builderPublishLabel(isPublishing)}
          </button>
        </div>
      </details>
    </section>
  );
}
