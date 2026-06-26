import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  builderPublishLabel,
  deriveBuilderContainerState,
} from '../runtime/builderContainerRuntime';
import { getSovereignContainerContract } from '../runtime/sovereignContainerContracts';
import { SOVEREIGN_FORM_MISSION } from '../runtime/sovereignFormContracts';
import {
  SOVEREIGN_ACTION_DRAFT_PR,
  SOVEREIGN_ACTION_REPAIR_LOG,
  SOVEREIGN_ACTION_START_TASK,
} from '../runtime/sovereignActionContracts';
import { formatCuteThinkingLabel } from '../runtime/cuteThinkingStatus';
import {
  DEV_CHAT_WORKER_MODELS,
  SOVEREIGN_WORKER_CHAT,
  SOVEREIGN_WORKER_KV,
  fetchDevChatRepoTree,
  parseDevChatGithubUrl,
  summarizeDevChatRepoSnapshot,
  type DevChatRepoSnapshot,
} from '../runtime/devChatWorkerBridge';
import { OpenHandsOperatorBriefingPanel } from '../components/OpenHandsOperatorBriefingPanel';
import type { OpenHandsEnterpriseConfig, OpenHandsJobSnapshot } from '../runtime/openhandsEnterpriseRuntime';

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
  openhandsConfig?: OpenHandsEnterpriseConfig;
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

interface ChatOutcomeHint {
  readonly kind: 'runtime' | 'files' | 'draft-pr' | 'stopper' | 'done';
  readonly text: string;
  readonly href?: string;
}

type WorkbenchPane = 'planner' | 'changes' | 'code' | 'terminal' | 'browser';
type AgentStatus = 'idle' | 'thinking' | 'editing' | 'running' | 'error';
type ChatRole = 'system' | 'thought' | 'user' | 'assistant';
type RuntimeTier = 'ready' | 'active' | 'blocked';

interface ChatLine {
  readonly id: string;
  readonly role: ChatRole;
  readonly text: string;
  readonly file?: string;
  readonly path?: string;
}

interface RuntimeSource {
  readonly id: string;
  readonly label: string;
  readonly tier: RuntimeTier;
  readonly description: string;
  readonly available: boolean;
}

const WORKBENCH_PANES = [
  { id: 'planner', label: 'Planner', icon: '☷' },
  { id: 'changes', label: 'Changes', icon: '☑' },
  { id: 'code', label: 'Code', icon: '</>' },
  { id: 'terminal', label: 'Terminal', icon: '▻' },
  { id: 'browser', label: 'Browser', icon: '◎' },
] as const;

const SIDE_MENU_ITEMS = [
  { icon: '◈', label: 'Repo laden' },
  { icon: '⬡', label: 'Branch wählen' },
  { icon: '⚡', label: 'AutoSwitch' },
  { icon: '◎', label: 'Session' },
  { icon: '▣', label: 'Logs' },
  { icon: '↺', label: 'Restore' },
  { icon: '⇄', label: 'Sync' },
  { icon: '⚙', label: 'Einstellungen' },
] as const;

const CUTE_THINKING_FRAME_MS = 1100;
const builderContainerContract = getSovereignContainerContract('builder');

const STATUS_COLOR: Record<AgentStatus, string> = {
  idle: '#34d399',
  thinking: '#22d3ee',
  editing: '#fbbf24',
  running: '#a78bfa',
  error: '#fb7185',
};

const STATUS_LABEL: Record<AgentStatus, string> = {
  idle: 'bereit',
  thinking: 'denkt…',
  editing: 'editiert',
  running: 'läuft',
  error: 'fehler',
};

const TIER_COLOR: Record<RuntimeTier, string> = {
  ready: '#34d399',
  active: '#22d3ee',
  blocked: '#fb7185',
};

const IDEA_OPTIONS: IdeaOption[] = [
  { label: 'Cooles Feature', text: 'Schlage mir ein kleines, cooles Feature vor, prüfe zuerst das Repo und baue es nur als echten, sicheren Draft-PR-tauglichen Änderungspfad.' },
  { label: 'Fehler fixen', text: 'Analysiere den aktuellen Fehlerstatus, finde die betroffenen Dateien und erzeuge einen minimalen echten Fix mit passenden Tests.' },
  { label: 'Android UX', text: 'Verbessere die Bedienbarkeit auf Android: Chat, Navigation, Statushinweise und klare Nutzerführung ohne neue Fensterflut.' },
  { label: 'Runtime härten', text: 'Prüfe den schwächsten Ablauf und ergänze Runtime-Checks, Validierungen und Tests ohne Mock-, Stub- oder Facade-Live-Pfade.' },
  { label: 'README erklären', text: 'Verbessere README oder Dokumentation so, dass normale Nutzer verstehen, was das Tool kann und wie man es benutzt.' },
];

function paneHelpText(pane: WorkbenchPane): string {
  if (pane === 'planner') return 'Planung bleibt im Chat: Auftrag verstehen, Repo prüfen, Stopper erklären.';
  if (pane === 'changes') return 'Änderungen erscheinen als ruhige Hinweise. Details bleiben im Files/Diff-Menü.';
  if (pane === 'code') return 'Code-Kontext wird von der Runtime genutzt; die UI erzeugt keinen Code selbst.';
  if (pane === 'terminal') return 'Terminal und Logs sind nur lesende Diagnoseflächen, nicht die Hauptbedienung.';
  return 'Browser/Preview bleibt optionaler Inspektor, nicht der Hauptablauf.';
}

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

function buildAnalyzedMission(args: { readonly wish: string; readonly repoReady: boolean; readonly repoReason: string }): string {
  const existingMission = collapseRepeatedAnalyzedMission(args.wish);
  if (isAnalyzedMission(existingMission)) return existingMission;
  const wish = missionToWishText(args.wish) || 'Verbessere das Sovereign Tool so, dass es für Nutzer klar bedienbar ist.';
  const repoState = args.repoReady ? 'Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.' : `Repo-Snapshot ist noch nicht bereit: ${args.repoReason}`;

  return [
    'Ideenfabrik Auftrag:', wish, '', 'Repository-Kontext:', repoState, '', 'Umsetzung:',
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

function splitFilePath(filePath: string | undefined): { path?: string; file?: string } {
  const clean = filePath?.trim();
  if (!clean) return {};
  const slash = clean.lastIndexOf('/');
  if (slash < 0) return { file: clean };
  return { path: `${clean.slice(0, slash + 1)}`, file: clean.slice(slash + 1) };
}

function buildOutcomeHints(job: OpenHandsJobSnapshot | undefined): ChatOutcomeHint[] {
  if (!job || job.status === 'idle') return [];
  const hints: ChatOutcomeHint[] = [];
  const files = (job.changedFiles ?? []).filter((file) => typeof file === 'string' && file.trim()).map((file) => file.trim());
  const draftPrUrl = safeHttpsUrl(job.draftPrUrl);
  if (job.openHandsId?.trim()) hints.push({ kind: 'runtime', text: `🐤 OpenHands Runtime-ID: ${job.openHandsId.trim()}` });
  if (files.length > 0) hints.push({ kind: 'files', text: `${files.length} Datei(en) geändert · Details im Files-Menü` });
  if (draftPrUrl) hints.push({ kind: 'draft-pr', text: 'Draft PR bereit · Öffnen', href: draftPrUrl });
  if ((job.status === 'blocked' || job.status === 'failed') && job.lastError?.trim()) hints.push({ kind: 'stopper', text: job.lastError.trim() });
  if (job.status === 'completed' && files.length === 0 && !draftPrUrl) hints.push({ kind: 'done', text: 'Küken hat fertig gepiepst · Keine Dateiänderung gemeldet' });
  return hints;
}

function deriveAgentStatus(args: { readonly repoBusy: boolean; readonly runtimeBusy: boolean; readonly isPublishing: boolean; readonly openhandsIsRunning?: boolean; readonly openhandsJob?: OpenHandsJobSnapshot; readonly localRepoLoading: boolean; readonly localRepoError: boolean }): AgentStatus {
  if (args.localRepoError || args.openhandsJob?.status === 'failed' || args.openhandsJob?.status === 'blocked') return 'error';
  if (args.isPublishing || args.openhandsJob?.status === 'running') return 'running';
  if ((args.openhandsJob?.changedFiles?.length ?? 0) > 0 || Boolean(args.openhandsJob?.draftPrUrl)) return 'editing';
  if (args.localRepoLoading || args.openhandsIsRunning || args.repoBusy || args.runtimeBusy) return 'thinking';
  return 'idle';
}

function fmtTime(ts: number): string {
  const date = new Date(ts);
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function buildChatLines(args: { readonly wishText: string; readonly repoReady: boolean; readonly repoReason: string; readonly runtimeThinkingActive: boolean; readonly cuteThinkingLabel: string; readonly sovereignSummary: string; readonly disabledReason?: string; readonly openhandsJob?: OpenHandsJobSnapshot; readonly chatRepoSnapshot: DevChatRepoSnapshot | null; readonly chatRepoError: string | null }): ChatLine[] {
  const lines: ChatLine[] = [];
  const firstFile = splitFilePath(args.openhandsJob?.changedFiles?.[0] ?? args.chatRepoSnapshot?.lastFile);
  const effectiveRepoReady = args.repoReady || Boolean(args.chatRepoSnapshot);

  lines.push({
    id: 'system:repo',
    role: 'system',
    text: effectiveRepoReady
      ? `Repo-Snapshot verbunden · ${args.chatRepoSnapshot ? summarizeDevChatRepoSnapshot(args.chatRepoSnapshot) : 'echte Runtime-Gates aktiv'}`
      : `Repo fehlt · ${args.repoReason}`,
  });

  if (args.chatRepoError) lines.push({ id: 'system:repo-error', role: 'system', text: `Repo-Ladefehler: ${args.chatRepoError}` });

  if (args.wishText.trim()) {
    lines.push({ id: 'user:wish', role: 'user', text: args.wishText.trim() });
    lines.push({
      id: 'assistant:repo',
      role: 'assistant',
      text: effectiveRepoReady
        ? 'Ich nutze den geladenen Repo-Kontext und leite die nächste echte Aktion über Sovereign/OpenHands-Gates weiter.'
        : args.repoReason,
    });
  }

  if (args.chatRepoSnapshot) {
    lines.push({
      id: 'assistant:repo-loaded',
      role: 'assistant',
      text: `Repo im Chat geladen: ${args.chatRepoSnapshot.name}\nBranch: ${args.chatRepoSnapshot.branch}\nStruktur: ${args.chatRepoSnapshot.dirs.join(' · ') || 'keine Top-Level-Ordner erkannt'}\n${args.chatRepoSnapshot.fileCount} Einträge. Das Seitenmenü kennt diesen Repo-Kontext jetzt.`,
      file: args.chatRepoSnapshot.lastFile,
      path: args.chatRepoSnapshot.lastPath,
    });
  }

  if (args.runtimeThinkingActive) lines.push({ id: 'thought:runtime', role: 'thought', text: args.cuteThinkingLabel });
  if (args.sovereignSummary.trim()) lines.push({ id: 'assistant:summary', role: 'assistant', text: args.sovereignSummary.trim(), ...firstFile });
  if (args.disabledReason?.trim()) lines.push({ id: 'system:blocked', role: 'system', text: args.disabledReason.trim() });
  return lines;
}

function StatusBar({ status, repoReady, repoReason, source, lastFile, onSourceClick, chatRepoSnapshot }: { status: AgentStatus; repoReady: boolean; repoReason: string; source: RuntimeSource; lastFile?: string; onSourceClick: () => void; chatRepoSnapshot: DevChatRepoSnapshot | null }) {
  const color = STATUS_COLOR[status];
  const fileInfo = splitFilePath(lastFile ?? chatRepoSnapshot?.lastFile);
  const repoLabel = chatRepoSnapshot ? `${chatRepoSnapshot.name} · ${chatRepoSnapshot.branch}` : repoReady ? 'Repo verbunden' : 'Repo fehlt';

  return (
    <div className="flex flex-shrink-0 flex-col gap-1 border-b border-slate-800 bg-[#0d1117] px-4 py-2" data-testid="sovereign-devchat-statusbar">
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1" aria-label={`Agent Status ${STATUS_LABEL[status]}`}>
          {(['idle', 'thinking', 'editing'] as const).map((item) => (
            <span key={item} className="h-2 w-2 rounded-full transition-all" style={{ background: status === item ? STATUS_COLOR[item] : `${STATUS_COLOR[item]}28`, boxShadow: status === item ? `0 0 7px ${STATUS_COLOR[item]}` : 'none' }} />
          ))}
        </div>
        <span className="font-mono text-[10px]" style={{ color }}>{STATUS_LABEL[status]}</span>
        <span className="flex-1" />
        <button type="button" onClick={onSourceClick} className="inline-flex items-center gap-1 rounded border border-slate-700 bg-transparent px-2 py-1 font-mono text-[9px]" style={{ color: TIER_COLOR[source.tier] }}>
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: TIER_COLOR[source.tier] }} />
          {source.label}
        </button>
      </div>
      <div className="flex items-center gap-1 overflow-hidden font-mono text-[9px] text-slate-500">
        <span className={repoReady || chatRepoSnapshot ? 'text-cyan-300' : 'text-amber-300'}>{repoLabel}</span>
        <span>·</span>
        <span className="truncate">{chatRepoSnapshot ? `${chatRepoSnapshot.fileCount} files` : repoReady ? 'Runtime Snapshot' : repoReason}</span>
        {fileInfo.file ? <span className="truncate">· <span className="text-amber-300">{fileInfo.path}</span>{fileInfo.file}</span> : null}
      </div>
    </div>
  );
}

function ThoughtBubble({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const short = text.length > 80 ? `${text.slice(0, 80)}…` : text;
  return (
    <button type="button" onClick={() => setExpanded((current) => !current)} className="flex items-start gap-2 px-4 text-left" aria-expanded={expanded}>
      <span className={`mt-0.5 flex-shrink-0 text-xs ${expanded ? 'text-cyan-300' : 'text-slate-500'}`}>✦</span>
      <span className={`font-mono text-[10px] italic leading-6 ${expanded ? 'text-slate-300' : 'text-slate-500'}`}>{expanded ? text : short}</span>
    </button>
  );
}

function Bubble({ msg }: { msg: ChatLine }) {
  const isUser = msg.role === 'user';
  const timestamp = fmtTime(Date.now());
  if (msg.role === 'system') return <div className="py-1 text-center"><span className="rounded-full border border-slate-800 bg-slate-900 px-3 py-1 font-mono text-[9.5px] text-slate-500">{msg.text}</span></div>;
  if (msg.role === 'thought') return <ThoughtBubble text={msg.text} />;
  return (
    <div className={`flex items-end gap-2 px-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {!isUser ? <div className="mb-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-xs">⬡</div> : null}
      <div className={`flex max-w-[82%] flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        {msg.file ? <div className="rounded border border-amber-400/25 bg-amber-500/10 px-2 py-0.5 font-mono text-[9px] text-amber-300">{msg.path}{msg.file}</div> : null}
        <div className={`whitespace-pre-wrap break-words border px-3 py-2 text-[13.5px] leading-6 text-slate-100 ${isUser ? 'rounded-[14px_14px_4px_14px] border-slate-700 bg-slate-800' : 'rounded-[4px_14px_14px_14px] border-slate-800 bg-slate-900'}`}>{msg.text}</div>
        <span className="font-mono text-[9px] text-slate-500">{timestamp}</span>
      </div>
    </div>
  );
}

function RuntimeSourceSheet({ sources, current, onClose }: { sources: RuntimeSource[]; current: RuntimeSource; onClose: () => void }) {
  return (
    <div className="absolute inset-0 z-[100] flex flex-col justify-end bg-black/70" onClick={onClose}>
      <div className="rounded-t-2xl border border-slate-800 bg-[#0d1117] px-0 pb-5 pt-4" onClick={(event) => event.stopPropagation()}>
        <div className="mb-3 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">Runtime Quelle</div>
        {sources.map((source) => (
          <button key={source.id} type="button" className={`flex w-full items-center gap-3 border-l-2 px-5 py-3 text-left ${source.id === current.id ? 'bg-slate-900' : 'bg-transparent'}`} style={{ borderLeftColor: source.id === current.id ? TIER_COLOR[source.tier] : 'transparent' }} onClick={onClose}>
            <span className="h-2 w-2 rounded-full" style={{ background: TIER_COLOR[source.tier] }} />
            <span className="min-w-0 flex-1"><span className="block font-mono text-xs text-slate-100">{source.label}</span><span className="block truncate text-[10px] text-slate-500">{source.description}</span></span>
            {source.id === current.id ? <span style={{ color: TIER_COLOR[source.tier] }}>✓</span> : null}
          </button>
        ))}
      </div>
    </div>
  );
}

function SideMenu({ onClose, onGenerateIdeas, onGenerateErrorWorkflow, onPublishDraftPr, isPublishing, chatRepoSnapshot }: { onClose: () => void; onGenerateIdeas: () => void; onGenerateErrorWorkflow: () => void; onPublishDraftPr: () => void; isPublishing: boolean; chatRepoSnapshot: DevChatRepoSnapshot | null }) {
  return (
    <div className="absolute inset-0 z-[90] flex" data-testid="sovereign-devchat-side-menu">
      <div className="flex-1 bg-black/60" onClick={onClose} />
      <div className="flex w-[min(10vw,9rem)] min-w-[8.5rem] flex-col border-l border-slate-800 bg-[#0d1117] py-4 max-lg:w-[220px]">
        <div className="mb-2 border-b border-slate-800 px-4 pb-3 font-mono text-[9px] uppercase tracking-[0.2em] text-slate-500">Sovereign Studio</div>
        {SIDE_MENU_ITEMS.map((item) => <button key={item.label} type="button" onClick={onClose} className="flex items-center gap-3 bg-transparent px-4 py-3 text-left"><span className="text-sm text-slate-500">{item.icon}</span><span className="font-mono text-xs text-slate-400">{item.label}</span></button>)}
        {chatRepoSnapshot ? <div className="mx-3 mt-2 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3 text-[10px] text-cyan-100"><p className="font-bold">Chat Repo</p><p>{chatRepoSnapshot.name} · {chatRepoSnapshot.branch}</p><p>{chatRepoSnapshot.fileCount} files</p></div> : null}
        <div className="mx-3 mt-2 rounded-xl border border-slate-800 bg-slate-950/80 p-3 text-[10px] text-slate-400"><p className="font-bold text-slate-200">Cloudflare</p><p className="truncate">{SOVEREIGN_WORKER_CHAT}</p><p className="truncate">{SOVEREIGN_WORKER_KV}</p></div>
        <div className="mt-auto space-y-2 border-t border-slate-800 px-3 pt-3"><button type="button" className="w-full rounded-xl border border-slate-700 px-3 py-2 text-left text-xs text-slate-200" onClick={() => { onGenerateIdeas(); onClose(); }}>Interne Prüfung</button><button type="button" className="w-full rounded-xl border border-amber-500/40 px-3 py-2 text-left text-xs text-amber-100" onClick={() => { onGenerateErrorWorkflow(); onClose(); }}>Fehleranalyse</button><button type="button" className="w-full rounded-xl border border-cyan-500/40 px-3 py-2 text-left text-xs text-cyan-100" onClick={() => { onPublishDraftPr(); onClose(); }}>{builderPublishLabel(isPublishing)}</button></div>
      </div>
    </div>
  );
}

export function BuilderContainer({ mission, repoReady, repoReason, repoBusy, runtimeBusy, isPublishing, sovereignSummary, sovereignPreview, onMissionChange, onGenerateIdeas, onGenerateErrorWorkflow, onPublishDraftPr, openhandsReady, openhandsConfig, openhandsJob, openhandsJobStatus, openhandsIsRunning, onStartOpenHands, onCancelOpenHands }: BuilderContainerProps) {
  const [wishText, setWishText] = useState(() => missionToWishText(mission));
  const [thinkingFrameIndex, setThinkingFrameIndex] = useState(0);
  const [activePane, setActivePane] = useState<WorkbenchPane>('changes');
  const [showRuntimeSheet, setShowRuntimeSheet] = useState(false);
  const [showSideMenu, setShowSideMenu] = useState(false);
  const [showOpenHandsBriefing, setShowOpenHandsBriefing] = useState(false);
  const [chatRepoSnapshot, setChatRepoSnapshot] = useState<DevChatRepoSnapshot | null>(null);
  const [chatRepoError, setChatRepoError] = useState<string | null>(null);
  const [localRepoLoading, setLocalRepoLoading] = useState(false);
  const lastMissionSeenRef = useRef(mission);
  const scrollRef = useRef<HTMLDivElement>(null);
  const state = deriveBuilderContainerState({ repoReady: repoReady || Boolean(chatRepoSnapshot), repoBusy: repoBusy || localRepoLoading, runtimeBusy, isPublishing, mission, sovereignSummary, sovereignPreview });
  const effectiveRepoReady = repoReady || Boolean(chatRepoSnapshot);
  const effectiveRepoReason = chatRepoSnapshot ? summarizeDevChatRepoSnapshot(chatRepoSnapshot) : repoReason;
  const analyzedMission = useMemo(() => buildAnalyzedMission({ wish: wishText, repoReady: effectiveRepoReady, repoReason: effectiveRepoReason }), [effectiveRepoReady, effectiveRepoReason, wishText]);
  const executableOpenHandsMission = useMemo(() => { const visibleMission = collapseRepeatedAnalyzedMission(mission); return isAnalyzedMission(visibleMission) ? visibleMission : collapseRepeatedAnalyzedMission(analyzedMission); }, [analyzedMission, mission]);
  const runtimeThinkingActive = Boolean(openhandsIsRunning || repoBusy || localRepoLoading || runtimeBusy || isPublishing);
  const cuteThinkingLabel = useMemo(() => formatCuteThinkingLabel({ index: thinkingFrameIndex, active: runtimeThinkingActive, status: openhandsJobStatus }), [openhandsJobStatus, runtimeThinkingActive, thinkingFrameIndex]);
  const outcomeHints = useMemo(() => buildOutcomeHints(openhandsJob), [openhandsJob]);
  const agentDisabled = !effectiveRepoReady || repoBusy || localRepoLoading || runtimeBusy || Boolean(openhandsIsRunning) || !openhandsReady || !onStartOpenHands;
  const agentStatus = deriveAgentStatus({ repoBusy, runtimeBusy, isPublishing, openhandsIsRunning, openhandsJob, localRepoLoading, localRepoError: Boolean(chatRepoError) });
  const sourceTier: RuntimeTier = openhandsReady ? (runtimeThinkingActive ? 'active' : 'ready') : 'blocked';
  const runtimeSource: RuntimeSource = { id: 'openhands-runtime', label: openhandsReady ? 'OpenHands' : 'OpenHands offline', tier: sourceTier, available: Boolean(openhandsReady), description: openhandsReady ? 'Echte Agent-Runtime verbunden' : 'Agent-Runtime noch nicht verbunden' };
  const runtimeSources: RuntimeSource[] = [runtimeSource, { id: 'worker-chat', label: 'Worker Chat', tier: 'ready', available: true, description: SOVEREIGN_WORKER_CHAT }, { id: 'worker-kv', label: 'Worker KV', tier: 'ready', available: true, description: SOVEREIGN_WORKER_KV }, { id: 'worker-models', label: `${DEV_CHAT_WORKER_MODELS.length} Worker Modelle`, tier: 'ready', available: true, description: DEV_CHAT_WORKER_MODELS.map((model) => model.label).join(' · ') }, { id: 'repo-snapshot', label: effectiveRepoReady ? 'Repo Snapshot' : 'Repo fehlt', tier: effectiveRepoReady ? 'ready' : 'blocked', available: effectiveRepoReady, description: effectiveRepoReady ? effectiveRepoReason : repoReason }];
  const chatLines = useMemo(() => buildChatLines({ wishText, repoReady: effectiveRepoReady, repoReason: effectiveRepoReason, runtimeThinkingActive, cuteThinkingLabel, sovereignSummary, disabledReason: state.disabledReason, openhandsJob, chatRepoSnapshot, chatRepoError }), [chatRepoError, chatRepoSnapshot, cuteThinkingLabel, effectiveRepoReady, effectiveRepoReason, openhandsJob, runtimeThinkingActive, sovereignSummary, state.disabledReason, wishText]);

  useEffect(() => { if (!runtimeThinkingActive) { setThinkingFrameIndex(0); return undefined; } const handle = window.setInterval(() => setThinkingFrameIndex((current) => current + 1), CUTE_THINKING_FRAME_MS); return () => window.clearInterval(handle); }, [runtimeThinkingActive]);
  useEffect(() => { if (mission === lastMissionSeenRef.current) return; lastMissionSeenRef.current = mission; setWishText(missionToWishText(mission)); }, [mission]);
  useEffect(() => { if (!scrollRef.current) return; scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [chatLines.length, outcomeHints.length, runtimeThinkingActive]);

  const analyzeWish = () => { const cleanMission = collapseRepeatedAnalyzedMission(analyzedMission); lastMissionSeenRef.current = cleanMission; onMissionChange(cleanMission); };
  const startAgentFromChat = () => { const cleanMission = collapseRepeatedAnalyzedMission(executableOpenHandsMission); lastMissionSeenRef.current = cleanMission; onMissionChange(cleanMission); onStartOpenHands?.(cleanMission); };
  const handleComposerSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedRepo = parseDevChatGithubUrl(wishText);
    if (parsedRepo) {
      setLocalRepoLoading(true);
      setChatRepoError(null);
      const result = await fetchDevChatRepoTree(parsedRepo);
      setLocalRepoLoading(false);
      if (result.ok && result.snapshot) {
        setChatRepoSnapshot(result.snapshot);
        setShowSideMenu(true);
        const summary = summarizeDevChatRepoSnapshot(result.snapshot);
        lastMissionSeenRef.current = summary;
        onMissionChange(`Repo laden via Chat:\n${summary}\n${result.snapshot.files.slice(0, 60).map((file) => file.path).join('\n')}`);
        return;
      }
      setChatRepoError(result.error ?? 'Repo konnte nicht geladen werden.');
      return;
    }
    if (agentDisabled) { analyzeWish(); return; }
    startAgentFromChat();
  };

  const centerColumnClass = 'mx-auto flex h-full min-h-0 w-full max-w-full flex-col lg:w-[55vw] lg:max-w-[55vw]';
  const composerClass = 'mx-auto w-full lg:w-[80%] lg:max-w-[44vw]';

  return (
    <section className={`${builderContainerContract.rootClass} sovereign-builder-compact relative mt-4 overflow-hidden rounded-3xl border border-cyan-400/25 bg-black text-sm text-slate-200 shadow-2xl shadow-cyan-950/10`} data-role={builderContainerContract.dataRole} data-testid={builderContainerContract.testId} data-layout="devchat-runtime-shell" aria-label={builderContainerContract.ariaLabel}>
      <style>{`@keyframes sovereignDevChatPulse { 0%,100%{opacity:1} 50%{opacity:.25} }`}</style>
      <StatusBar status={agentStatus} repoReady={effectiveRepoReady} repoReason={effectiveRepoReason} source={runtimeSource} lastFile={openhandsJob?.changedFiles?.[0]} onSourceClick={() => setShowRuntimeSheet(true)} chatRepoSnapshot={chatRepoSnapshot} />
      <div className="grid min-h-[72vh] grid-cols-1 gap-4 px-4 py-4 lg:grid-cols-[minmax(8rem,1fr)_minmax(0,55vw)_minmax(8rem,1fr)]" data-layout-zone="devchat-with-side-menus">
        <aside className="hidden min-w-0 flex-col gap-2 lg:flex" aria-label="Linkes Sovereign Seitenmenü">{SIDE_MENU_ITEMS.slice(0, 6).map((item) => <button key={item.label} type="button" onClick={() => setShowSideMenu(true)} className="rounded-full border border-slate-800 bg-slate-950/80 px-3 py-2 text-left text-xs font-bold text-slate-400"><span className="mr-2 text-slate-500">{item.icon}</span>{item.label}</button>)}</aside>
        <div className="min-w-0"><div className={centerColumnClass} data-chat-body-width="55%"><div className="mb-2 px-1"><div className="flex flex-wrap items-center gap-2 text-sm"><span className="h-2.5 w-2.5 rounded-full bg-emerald-300" aria-hidden="true" /><h2 className="text-lg font-black text-slate-50">Sovereign Chat</h2><span className="rounded-full border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-400">OpenHands Runtime</span></div><div className="mt-3 flex flex-wrap items-center gap-2 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Sovereign Arbeitsbereiche">{WORKBENCH_PANES.map((pane) => <button key={pane.id} type="button" aria-pressed={activePane === pane.id} className={activePane === pane.id ? 'flex-shrink-0 rounded-full border border-cyan-300/50 bg-slate-900 px-3 py-2 text-sm font-bold text-slate-50' : 'flex-shrink-0 rounded-full border border-transparent bg-transparent px-3 py-2 text-sm font-bold text-slate-500'} onClick={() => setActivePane(pane.id)}><span className="mr-1 text-slate-400">{pane.icon}</span>{pane.label}</button>)}</div><p className="mt-2 text-xs text-slate-600">{paneHelpText(activePane)}</p></div>
          <div ref={scrollRef} className="min-h-[min(55vh,42rem)] max-h-[min(55vh,42rem)] flex-1 overflow-y-auto rounded-3xl border border-slate-900 bg-black px-0 py-4" aria-label="Sovereign Chat Verlauf" data-testid="sovereign-chat-body-window">{!wishText.trim() && !chatRepoSnapshot ? <div className="mx-auto flex max-w-3xl flex-col items-center justify-center px-4 py-10 text-center"><div className="text-6xl" aria-hidden="true">🐥</div><p className="mt-4 text-3xl font-black text-slate-50">Let&apos;s start building!</p><p className="mt-3 max-w-xl text-sm text-slate-500">GitHub URL einfügen, um Repo direkt aus dem Chat zu laden. Danach landen Status und Struktur im Menü.</p><div className="mt-6 grid w-full gap-3 sm:grid-cols-2" aria-label="Schnellvorschläge">{IDEA_OPTIONS.slice(0, 4).map((option) => <button key={option.label} type="button" className="rounded-2xl border border-slate-800 bg-transparent px-4 py-4 text-left text-sm font-bold text-slate-100 hover:border-cyan-400/60" onClick={() => setWishText((current) => appendOption(current, option))}>{option.label}</button>)}</div></div> : <div className="flex flex-col gap-3 pb-2">{chatLines.map((line) => <Bubble key={line.id} msg={line} />)}{agentStatus === 'thinking' ? <div className="flex items-center gap-2 px-4"><div className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-xs">⬡</div><div className="flex gap-1">{[0, 1, 2].map((dot) => <span key={dot} className="h-1.5 w-1.5 rounded-full bg-cyan-300" style={{ animation: `sovereignDevChatPulse 1.2s ease-in-out ${dot * 0.2}s infinite` }} />)}</div></div> : null}{outcomeHints.length > 0 ? <div className="px-4 text-xs" aria-label="OpenHands Ergebnis-Hinweise" data-testid="sovereign-chat-outcome-hints"><div className="space-y-1 border-l border-slate-800 pl-3 text-slate-500">{outcomeHints.map((hint) => <p key={`${hint.kind}:${hint.text}`} data-outcome-hint-kind={hint.kind}>{hint.href ? <a className="text-cyan-200 underline underline-offset-4" href={hint.href} target="_blank" rel="noreferrer">{hint.text}</a> : hint.text}</p>)}</div></div> : null}</div>}</div>
          <form className="mt-3 flex-shrink-0 pb-[max(1rem,env(safe-area-inset-bottom))]" onSubmit={(event) => { void handleComposerSubmit(event); }} data-composer-width="80%"><div className={composerClass}><div className="flex items-end gap-2 border-t border-slate-900 bg-[#0d1117] p-3 sm:rounded-2xl sm:border"><button type="button" onClick={() => setShowSideMenu(true)} className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-slate-700 bg-slate-900 text-slate-500" aria-label="Sovereign Menü öffnen">☰</button><textarea id={SOVEREIGN_FORM_MISSION.id} name={SOVEREIGN_FORM_MISSION.id} data-role={SOVEREIGN_FORM_MISSION.dataRole} data-testid={SOVEREIGN_FORM_MISSION.testId} className="max-h-32 min-h-10 flex-1 resize-none overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-base leading-6 text-slate-50 outline-none placeholder:text-slate-500" value={wishText} onChange={(event) => setWishText(event.target.value)} onInput={(event) => { const target = event.currentTarget; target.style.height = 'auto'; target.style.height = `${Math.min(target.scrollHeight, 128)}px`; }} placeholder={chatRepoSnapshot ? `Frage zu ${chatRepoSnapshot.name}…` : 'GitHub URL oder Nachricht…'} aria-label={SOVEREIGN_FORM_MISSION.ariaLabel} rows={1} /><button className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-cyan-300/40 bg-cyan-400 text-lg text-slate-950 transition disabled:border-slate-800 disabled:bg-slate-900 disabled:text-slate-500" type="submit" disabled={localRepoLoading || (!parseDevChatGithubUrl(wishText) && (agentDisabled || !wishText.trim()))} data-role={SOVEREIGN_ACTION_START_TASK.dataRole} data-testid={SOVEREIGN_ACTION_START_TASK.testId} aria-label="Agent starten" data-state={agentDisabled ? 'disabled' : 'idle'}>{localRepoLoading ? '…' : '↑'}</button></div></div></form></div></div>
        <aside className="hidden min-w-0 flex-col gap-2 xl:flex" aria-label="Rechtes Sovereign Diagnosemenü">{['Health', 'Runtime', 'Telemetry', 'Findings'].map((item) => <button key={item} type="button" onClick={() => setShowSideMenu(true)} className="rounded-full border border-slate-800 bg-slate-950/80 px-3 py-2 text-left text-xs font-bold text-slate-400">{item}</button>)}<details className="mt-2 rounded-2xl border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-300"><summary className="cursor-pointer font-black text-slate-100">Diagnose</summary><div className="mt-3 space-y-2"><button type="button" className="block w-full rounded-xl border border-slate-700 px-3 py-2 text-left" onClick={onGenerateIdeas}>Interne Prüfung</button><button type="button" className="block w-full rounded-xl border border-amber-500/40 px-3 py-2 text-left text-amber-100" onClick={onGenerateErrorWorkflow} data-role={SOVEREIGN_ACTION_REPAIR_LOG.dataRole} data-testid={SOVEREIGN_ACTION_REPAIR_LOG.testId}>Fehleranalyse</button><button type="button" className="block w-full rounded-xl border border-cyan-500/40 px-3 py-2 text-left text-cyan-100" onClick={onPublishDraftPr} data-role={SOVEREIGN_ACTION_DRAFT_PR.dataRole} data-testid={SOVEREIGN_ACTION_DRAFT_PR.testId}>{builderPublishLabel(isPublishing)}</button>{openhandsIsRunning ? <button type="button" className="block w-full rounded-xl border border-red-500/40 px-3 py-2 text-left text-red-100" onClick={onCancelOpenHands}>Agent stoppen</button> : null}</div></details><button type="button" className="mt-2 w-full rounded-xl border border-purple-500/40 bg-slate-950/80 px-3 py-2 text-left text-xs font-bold text-purple-300 transition hover:bg-slate-900" onClick={() => setShowOpenHandsBriefing(true)}>🤖 Briefing</button>{sovereignPreview ? <details className="rounded-2xl border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-300"><summary className="cursor-pointer font-black text-slate-100">Preview</summary><pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap text-[10px] text-slate-500">{sovereignPreview}</pre></details> : null}</aside>
      </div>
      {showRuntimeSheet ? <RuntimeSourceSheet sources={runtimeSources} current={runtimeSource} onClose={() => setShowRuntimeSheet(false)} /> : null}
      {showSideMenu ? <SideMenu onClose={() => setShowSideMenu(false)} onGenerateIdeas={onGenerateIdeas} onGenerateErrorWorkflow={onGenerateErrorWorkflow} onPublishDraftPr={onPublishDraftPr} isPublishing={isPublishing} chatRepoSnapshot={chatRepoSnapshot} /> : null}
      {showOpenHandsBriefing && openhandsConfig ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" onClick={() => setShowOpenHandsBriefing(false)}>
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <OpenHandsOperatorBriefingPanel config={openhandsConfig} onClose={() => setShowOpenHandsBriefing(false)} initiallyExpanded={true} />
          </div>
        </div>
      ) : null}
    </section>
  );
}
