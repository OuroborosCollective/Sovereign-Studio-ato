import React, { useEffect, useMemo, useRef, useState } from 'react';
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
import {
  deriveSovereignChatResultCards,
  type SovereignChatResultCard,
} from '../runtime/sovereignChatWorkbenchResults';
import type { OpenHandsJobSnapshot } from '../runtime/openhandsEnterpriseRuntime';

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
}

interface IdeaOption {
  readonly label: string;
  readonly text: string;
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

function cardToneClass(card: SovereignChatResultCard): string {
  if (card.kind === 'draft-pr') return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-50';
  if (card.kind === 'stopper') return 'border-rose-400/30 bg-rose-500/10 text-rose-50';
  if (card.kind === 'completed') return 'border-amber-300/30 bg-amber-500/10 text-amber-50';
  return 'border-cyan-400/25 bg-slate-950/70 text-slate-100';
}

function ResultCard({ card }: { readonly card: SovereignChatResultCard }): React.ReactElement {
  return (
    <div className={`rounded-2xl border p-3 text-sm ${cardToneClass(card)}`} data-result-card-kind={card.kind}>
      <p className="text-xs font-black uppercase tracking-wide opacity-80">{card.title}</p>
      <p className="mt-1 whitespace-pre-wrap">{card.message}</p>
      {card.items?.length ? (
        <ul className="mt-2 space-y-1 text-xs opacity-90">
          {card.items.map((item) => <li key={item} className="truncate">• {item}</li>)}
        </ul>
      ) : null}
      {card.actionUrl && card.actionLabel ? (
        <a
          className="mt-2 inline-flex rounded-full border border-current/30 px-3 py-1 text-xs font-black underline-offset-4 hover:underline"
          href={card.actionUrl}
          target="_blank"
          rel="noreferrer"
        >
          {card.actionLabel}
        </a>
      ) : null}
    </div>
  );
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
}: BuilderContainerProps) {
  const [wishText, setWishText] = useState(() => missionToWishText(mission));
  const [thinkingFrameIndex, setThinkingFrameIndex] = useState(0);
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
  const resultCards = useMemo(
    () => openhandsJob ? deriveSovereignChatResultCards(openhandsJob) : [],
    [openhandsJob],
  );
  const agentDisabled = !repoReady || repoBusy || runtimeBusy || Boolean(openhandsIsRunning) || !openhandsReady || !onStartOpenHands;

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

  const agentStatusLabel = openhandsReady ? cuteThinkingLabel : '🌙 Agent noch nicht verbunden';

  return (
    <section
      className={`${builderContainerContract.rootClass} sovereign-builder-compact mt-4 rounded-3xl border border-cyan-400/25 bg-slate-950/80 p-4 text-sm text-slate-200 shadow-2xl shadow-cyan-950/10`}
      data-role={builderContainerContract.dataRole}
      data-testid={builderContainerContract.testId}
      aria-label={builderContainerContract.ariaLabel}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-black uppercase tracking-[0.28em] text-cyan-200">No-Code Chat Workbench</p>
          <h2 className="mt-1 text-2xl font-black text-slate-50">Sovereign Agent</h2>
          <p className="mt-1 text-sm text-slate-400">Schreib wie in einem normalen Chat. Der Agent nutzt Repo, Runtime, Pattern Memory und OpenHands im Hintergrund.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className={repoReady ? 'rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-200' : 'rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-amber-200'}>
            {repoReady ? 'Repo verbunden' : 'Repo fehlt'}
          </span>
          <span className={openhandsReady ? 'rounded-full border border-purple-400/30 bg-purple-500/10 px-3 py-1 text-purple-200' : 'rounded-full border border-slate-600 bg-slate-900 px-3 py-1 text-slate-300'}>
            {agentStatusLabel}
          </span>
        </div>
      </div>

      <div className="mt-5 space-y-3" aria-label="Sovereign Chat Verlauf">
        <div className="max-w-[92%] rounded-3xl rounded-tl-sm border border-cyan-400/20 bg-cyan-500/10 p-4 text-cyan-50">
          <p className="text-xs font-black uppercase tracking-wide text-cyan-200">Sovereign</p>
          <p className="mt-2">Hey, ich bin bereit. Sag mir einfach, was ich an deinem Repo bauen, prüfen oder verbessern soll. Details wie Logs, Patterns und Runtime bleiben leise im Menü.</p>
          <p className="mt-3 inline-flex rounded-full border border-cyan-300/20 bg-slate-950/40 px-3 py-1 text-xs text-cyan-100" aria-live="polite">
            {agentStatusLabel}
          </p>
        </div>

        {wishText.trim() ? (
          <div className="ml-auto max-w-[92%] rounded-3xl rounded-tr-sm border border-slate-600 bg-slate-900/90 p-4 text-slate-100">
            <p className="text-xs font-black uppercase tracking-wide text-slate-400">Du</p>
            <p className="mt-2 whitespace-pre-wrap">{wishText}</p>
          </div>
        ) : null}

        <div className="max-w-[92%] rounded-3xl rounded-tl-sm border border-slate-700 bg-slate-900/70 p-4 text-slate-200">
          <p className="text-xs font-black uppercase tracking-wide text-slate-400">Systemhinweis</p>
          <p className="mt-2">{repoReason}</p>
          {state.disabledReason ? <p className="mt-2 text-amber-300">{state.disabledReason}</p> : null}
          {sovereignSummary ? <p className="mt-2 text-slate-300">{sovereignSummary}</p> : null}
          {resultCards.length > 0 ? (
            <div className="mt-3 grid gap-2" aria-label="OpenHands Ergebnis-Karten">
              {resultCards.map((card) => <ResultCard key={`${card.kind}:${card.title}`} card={card} />)}
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2" aria-label="Schnellvorschläge">
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
          className="mt-2 min-h-28 w-full rounded-3xl border border-slate-700 bg-slate-950 p-4 text-base leading-6 text-slate-100 outline-none focus:border-cyan-300/70"
          value={wishText}
          onChange={(event) => setWishText(event.target.value)}
          placeholder="Schreib einfach: Bau mir ein cooles Feature, fix den Fehler, mach die App schöner, prüfe Android, erstelle einen Draft PR..."
          aria-label={SOVEREIGN_FORM_MISSION.ariaLabel}
        />
      </label>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          className={primaryButtonClassName}
          onClick={startAgentFromChat}
          disabled={agentDisabled}
          type="button"
          data-role={SOVEREIGN_ACTION_START_TASK.dataRole}
          data-testid={SOVEREIGN_ACTION_START_TASK.testId}
          aria-label="Agent mit Chat-Auftrag starten"
          data-state={agentDisabled ? 'disabled' : 'idle'}
        >
          {runtimeThinkingActive ? cuteThinkingLabel : 'Agent starten'}
        </button>
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
            data-state={generateDisabled ? 'disabled' : 'idle'}
          >
            Auftrag vorbereiten
          </button>
        )}
      </div>

      <details className="mt-4 rounded-2xl border border-slate-800 bg-slate-950/70 p-3">
        <summary className="cursor-pointer text-xs font-black uppercase tracking-wide text-slate-400">Details, alte Builder-Werkzeuge und Draft PR</summary>
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

      <label className="mt-4 block">
        <span className="text-xs font-bold uppercase tracking-wide text-slate-400">Analysierter ausführbarer Auftrag</span>
        <textarea
          className="sovereign-builder-mission-output mt-2 min-h-24 w-full rounded-2xl border border-slate-700 bg-slate-900 p-3 text-sm leading-6"
          value={mission}
          onChange={(event) => onMissionChange(event.target.value)}
          placeholder="Hier steht der strukturierte Auftrag, den der Agent wirklich ausführen soll."
          aria-label="Builder mission"
        />
      </label>

      {state.hasPreview ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400">Files, Brain und Runtime-Preview</summary>
          <pre className="mt-2 max-h-96 overflow-auto rounded-xl bg-black/40 p-3 text-[11px] text-slate-300">{sovereignPreview}</pre>
        </details>
      ) : null}
    </section>
  );
}
