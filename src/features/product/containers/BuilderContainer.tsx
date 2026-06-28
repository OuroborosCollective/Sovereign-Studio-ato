import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  builderPublishLabel,
  deriveBuilderContainerState,
} from '../runtime/builderContainerRuntime';
import { getSovereignContainerContract } from '../runtime/sovereignContainerContracts';
import { SOVEREIGN_FORM_MISSION } from '../runtime/sovereignFormContracts';
import {
  SOVEREIGN_ACTION_ANALYZE_MISSION,
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

// ─── Public Props ──────────────────────────────────────────────────────────────
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

// ─── Internal Types ────────────────────────────────────────────────────────────
interface IdeaOption {
  readonly label: string;
  readonly text: string;
}

interface ChatOutcomeHint {
  readonly kind: 'runtime' | 'files' | 'draft-pr' | 'stopper' | 'done';
  readonly text: string;
  readonly href?: string;
}

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

// ─── Constants ─────────────────────────────────────────────────────────────────
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

// ─── Helpers ───────────────────────────────────────────────────────────────────
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
      text: `Repo im Chat geladen: ${args.chatRepoSnapshot.name}\nBranch: ${args.chatRepoSnapshot.branch}\nStruktur: ${args.chatRepoSnapshot.dirs.join(' · ') || 'keine Top-Level-Ordner erkannt'}\n${args.chatRepoSnapshot.fileCount} Einträge. Details bleiben im Menü abrufbar.`,
      file: args.chatRepoSnapshot.lastFile,
      path: args.chatRepoSnapshot.lastPath,
    });
  }

  if (args.runtimeThinkingActive) lines.push({ id: 'thought:runtime', role: 'thought', text: args.cuteThinkingLabel });
  if (args.sovereignSummary.trim()) lines.push({ id: 'assistant:summary', role: 'assistant', text: args.sovereignSummary.trim(), ...firstFile });
  if (args.disabledReason?.trim()) lines.push({ id: 'system:blocked', role: 'system', text: args.disabledReason.trim() });
  return lines;
}

// ─── Sub-Components ───────────────────────────────────────────────────────────
function StatusBar({
  status, repoReady, repoReason, source, lastFile, onSourceClick, chatRepoSnapshot,
}: {
  status: AgentStatus;
  repoReady: boolean;
  repoReason: string;
  source: RuntimeSource;
  lastFile?: string;
  onSourceClick: () => void;
  chatRepoSnapshot: DevChatRepoSnapshot | null;
}) {
  const color = STATUS_COLOR[status];
  const fileInfo = splitFilePath(lastFile ?? chatRepoSnapshot?.lastFile);
  const repoLabel = chatRepoSnapshot
    ? `${chatRepoSnapshot.name}:${chatRepoSnapshot.branch}`
    : repoReady ? 'Repo verbunden' : 'Repo fehlt';

  return (
    <div
      className="flex shrink-0 flex-col border-b border-[#252e3e] bg-[#0e1525]"
      data-testid="sovereign-devchat-statusbar"
    >
      <div className="flex items-center gap-2 px-3 py-2 md:px-4">
        <div
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-sm"
          style={{ background: `${color}18`, color, boxShadow: `0 0 0 1px ${color}30` }}
          aria-hidden="true"
        >
          ⬡
        </div>
        <span className="text-sm font-semibold text-[#cdd9e5]">Sovereign</span>

        <div
          className="flex items-center gap-1.5 rounded-md border border-[#252e3e] bg-[#161b2e] px-2 py-0.5"
          aria-label={`Agent Status ${STATUS_LABEL[status]}`}
        >
          {(['idle', 'thinking', 'editing'] as const).map((s) => (
            <span
              key={s}
              className="h-1.5 w-1.5 rounded-full transition-all"
              style={{
                background: status === s ? STATUS_COLOR[s] : `${STATUS_COLOR[s]}28`,
                boxShadow: status === s ? `0 0 6px ${STATUS_COLOR[s]}` : 'none',
              }}
            />
          ))}
          <span className="font-mono text-[10px]" style={{ color }}>{STATUS_LABEL[status]}</span>
        </div>

        <span className="flex-1" />

        <div className="hidden items-center gap-1 sm:flex">
          <span className={`font-mono text-[10px] ${repoReady || chatRepoSnapshot ? 'text-emerald-400' : 'text-amber-400'}`}>
            {repoLabel}
          </span>
          {chatRepoSnapshot ? (
            <span className="font-mono text-[10px] text-[#4b5563]">· {chatRepoSnapshot.fileCount} files</span>
          ) : (
            <span className="max-w-[14rem] truncate font-mono text-[10px] text-[#4b5563]">
              · {repoReady ? 'Runtime Snapshot' : repoReason}
            </span>
          )}
          {fileInfo.file ? (
            <span className="hidden font-mono text-[10px] text-[#4b5563] md:inline">
              · <span className="text-amber-300">{fileInfo.path}</span>{fileInfo.file}
            </span>
          ) : null}
        </div>

        <button
          type="button"
          onClick={onSourceClick}
          className="flex shrink-0 items-center gap-1.5 rounded-md border border-[#252e3e] bg-[#161b2e] px-2.5 py-1 font-mono text-[10px] transition hover:border-[#374556] active:bg-[#1c2333]"
          style={{ color: TIER_COLOR[source.tier] }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: TIER_COLOR[source.tier], boxShadow: `0 0 5px ${TIER_COLOR[source.tier]}` }}
          />
          <span className="hidden sm:inline">{source.label}</span>
          <span className="sm:hidden" aria-label={source.label}>RT</span>
        </button>
      </div>
    </div>
  );
}

function ThoughtBubble({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const short = text.length > 80 ? `${text.slice(0, 80)}…` : text;
  return (
    <button
      type="button"
      onClick={() => setExpanded((c) => !c)}
      className="flex w-full items-start gap-2 px-4 py-0.5 text-left"
      aria-expanded={expanded}
    >
      <span className={`mt-0.5 shrink-0 text-xs transition-colors ${expanded ? 'text-sky-400' : 'text-[#2a3441]'}`}>✦</span>
      <span className={`font-mono text-[10px] italic leading-relaxed transition-colors ${expanded ? 'text-[#768390]' : 'text-[#2a3441]'}`}>
        {expanded ? text : short}
      </span>
    </button>
  );
}

function Bubble({ msg }: { msg: ChatLine }) {
  const isUser = msg.role === 'user';
  const timestamp = fmtTime(Date.now());

  if (msg.role === 'system') {
    return (
      <div className="px-4 py-1 text-center">
        <span className="inline-block max-w-full rounded-full border border-[#252e3e] bg-[#161b2e] px-3 py-1 font-mono text-[10px] text-[#4b5563]">
          {msg.text}
        </span>
      </div>
    );
  }

  if (msg.role === 'thought') return <ThoughtBubble text={msg.text} />;

  return (
    <div className={`flex items-end gap-2 px-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {!isUser ? (
        <div className="mb-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[#252e3e] bg-[#161b2e] text-xs text-[#768390]">
          ⬡
        </div>
      ) : null}
      <div className={`flex max-w-[82%] flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        {msg.file ? (
          <div className="rounded-md border border-amber-400/20 bg-amber-500/10 px-2 py-0.5 font-mono text-[9px] text-amber-300">
            {msg.path}{msg.file}
          </div>
        ) : null}
        <div
          className={`whitespace-pre-wrap break-words px-3.5 py-2.5 text-[14px] leading-6 shadow-sm ${
            isUser
              ? 'rounded-[18px_18px_4px_18px] bg-[#243247] text-[#e1e4e8]'
              : 'rounded-[4px_18px_18px_18px] border border-[#252e3e] bg-[#161b2e] text-[#cdd9e5]'
          }`}
        >
          {msg.text}
        </div>
        <span className="font-mono text-[9px] text-[#4b5563]">{timestamp}</span>
      </div>
    </div>
  );
}

function RuntimeSourceSheet({ sources, current, onClose }: { sources: RuntimeSource[]; current: RuntimeSource; onClose: () => void }) {
  return (
    <div className="absolute inset-0 z-[100] flex flex-col justify-end bg-[#0e1525]/80" style={{ backdropFilter: 'blur(6px)' }} onClick={onClose}>
      <div className="rounded-t-2xl border border-[#252e3e] bg-[#0e1525] px-0 pb-5 pt-4" onClick={(event) => event.stopPropagation()}>
        <div className="mb-3 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-[#4b5563]">Runtime Quelle</div>
        {sources.map((source) => (
          <button
            key={source.id}
            type="button"
            className={`flex w-full items-center gap-3 border-l-2 px-5 py-3 text-left transition ${source.id === current.id ? 'bg-[#161b2e]' : 'bg-transparent hover:bg-[#161b2e]/60'}`}
            style={{ borderLeftColor: source.id === current.id ? TIER_COLOR[source.tier] : 'transparent' }}
            onClick={onClose}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: TIER_COLOR[source.tier], boxShadow: `0 0 6px ${TIER_COLOR[source.tier]}` }} />
            <span className="min-w-0 flex-1">
              <span className="block font-mono text-xs text-[#cdd9e5]">{source.label}</span>
              <span className="block truncate text-[10px] text-[#4b5563]">{source.description}</span>
            </span>
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
      <div className="flex-1 bg-[#0e1525]/70" style={{ backdropFilter: 'blur(4px)' }} onClick={onClose} />
      <div className="flex w-[min(86vw,22rem)] flex-col border-l border-[#252e3e] bg-[#0e1525] shadow-2xl">
        <div className="border-b border-[#252e3e] px-4 py-3">
          <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-[#4b5563]">Sovereign Studio</div>
          <div className="mt-1 text-sm font-semibold text-[#cdd9e5]">Details & Aktionen</div>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {SIDE_MENU_ITEMS.map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={onClose}
              className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-[#161b2e]"
            >
              <span className="text-sm text-[#4b5563]">{item.icon}</span>
              <span className="font-mono text-xs text-[#768390]">{item.label}</span>
            </button>
          ))}

          {chatRepoSnapshot ? (
            <div className="mx-3 mt-2 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-[11px] text-emerald-100">
              <p className="font-semibold">Chat Repo</p>
              <p>{chatRepoSnapshot.name} · {chatRepoSnapshot.branch}</p>
              <p className="text-emerald-300/70">{chatRepoSnapshot.fileCount} files</p>
            </div>
          ) : null}

          <div className="mx-3 mt-2 rounded-xl border border-[#252e3e] bg-[#161b2e] p-3 text-[10px] text-[#4b5563]">
            <p className="font-semibold text-[#768390]">Cloudflare</p>
            <p className="truncate">{SOVEREIGN_WORKER_CHAT}</p>
            <p className="truncate">{SOVEREIGN_WORKER_KV}</p>
          </div>
        </div>

        <div className="space-y-2 border-t border-[#252e3e] p-3">
          <button
            type="button"
            className="w-full rounded-xl border border-[#252e3e] px-3 py-2.5 text-left text-xs text-[#cdd9e5] transition hover:bg-[#161b2e]"
            onClick={() => { onGenerateIdeas(); onClose(); }}
            data-role={SOVEREIGN_ACTION_ANALYZE_MISSION.dataRole}
            data-testid={SOVEREIGN_ACTION_ANALYZE_MISSION.testId}
            aria-label={SOVEREIGN_ACTION_ANALYZE_MISSION.ariaLabel}
          >
            Interne Prüfung
          </button>
          <button
            type="button"
            className="w-full rounded-xl border border-amber-500/40 px-3 py-2.5 text-left text-xs text-amber-100 transition hover:bg-amber-500/5"
            onClick={() => { onGenerateErrorWorkflow(); onClose(); }}
          >
            Fehleranalyse
          </button>
          <button
            type="button"
            className="w-full rounded-xl border border-[#f97316]/40 bg-[#f97316]/5 px-3 py-2.5 text-left text-xs font-medium text-[#f97316] transition hover:bg-[#f97316]/10"
            onClick={() => { onPublishDraftPr(); onClose(); }}
          >
            {builderPublishLabel(isPublishing)}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────────
export function BuilderContainer({
  mission, repoReady, repoReason, repoBusy, runtimeBusy, isPublishing,
  sovereignSummary, sovereignPreview, onMissionChange, onGenerateIdeas,
  onGenerateErrorWorkflow, onPublishDraftPr, openhandsReady, openhandsConfig,
  openhandsJob, openhandsJobStatus, openhandsIsRunning, onStartOpenHands, onCancelOpenHands,
}: BuilderContainerProps) {
  const [wishText, setWishText] = useState(() => missionToWishText(mission));
  const [thinkingFrameIndex, setThinkingFrameIndex] = useState(0);
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
  const runtimeSources: RuntimeSource[] = [
    runtimeSource,
    { id: 'worker-chat', label: 'Worker Chat', tier: 'ready', available: true, description: SOVEREIGN_WORKER_CHAT },
    { id: 'worker-kv', label: 'Worker KV', tier: 'ready', available: true, description: SOVEREIGN_WORKER_KV },
    { id: 'worker-models', label: `${DEV_CHAT_WORKER_MODELS.length} Worker Modelle`, tier: 'ready', available: true, description: DEV_CHAT_WORKER_MODELS.map((model) => model.label).join(' · ') },
    { id: 'repo-snapshot', label: effectiveRepoReady ? 'Repo Snapshot' : 'Repo fehlt', tier: effectiveRepoReady ? 'ready' : 'blocked', available: effectiveRepoReady, description: effectiveRepoReady ? effectiveRepoReason : repoReason },
  ];
  const chatLines = useMemo(() => buildChatLines({ wishText, repoReady: effectiveRepoReady, repoReason: effectiveRepoReason, runtimeThinkingActive, cuteThinkingLabel, sovereignSummary, disabledReason: state.disabledReason, openhandsJob, chatRepoSnapshot, chatRepoError }), [chatRepoError, chatRepoSnapshot, cuteThinkingLabel, effectiveRepoReady, effectiveRepoReason, openhandsJob, runtimeThinkingActive, sovereignSummary, state.disabledReason, wishText]);

  useEffect(() => {
    if (!runtimeThinkingActive) {
      setThinkingFrameIndex(0);
      return undefined;
    }
    const handle = window.setInterval(() => setThinkingFrameIndex((current) => current + 1), CUTE_THINKING_FRAME_MS);
    return () => window.clearInterval(handle);
  }, [runtimeThinkingActive]);

  useEffect(() => {
    if (mission === lastMissionSeenRef.current) return;
    lastMissionSeenRef.current = mission;
    setWishText(missionToWishText(mission));
  }, [mission]);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [chatLines.length, outcomeHints.length, runtimeThinkingActive]);

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

  return (
    <section
      className={`${builderContainerContract.rootClass} relative mt-3 flex h-[calc(100dvh-8rem)] min-h-[34rem] overflow-hidden rounded-2xl border border-[#252e3e] bg-[#0e1525] text-sm text-[#cdd9e5] shadow-2xl shadow-black/30`}
      data-role={builderContainerContract.dataRole}
      data-testid={builderContainerContract.testId}
      data-layout="devchat-runtime-shell"
      aria-label={builderContainerContract.ariaLabel}
    >
      <style>{`
        @keyframes sovereignDevChatPulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.35;transform:scale(.85)} }
        .scrollbar-none::-webkit-scrollbar { display:none; }
        .scrollbar-thin::-webkit-scrollbar { width:3px; height:3px; }
        .scrollbar-thin::-webkit-scrollbar-track { background:transparent; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background:#252e3e; border-radius:2px; }
      `}</style>

      <div className="flex min-w-0 flex-1 flex-col">
        <StatusBar
          status={agentStatus}
          repoReady={effectiveRepoReady}
          repoReason={effectiveRepoReason}
          source={runtimeSource}
          lastFile={openhandsJob?.changedFiles?.[0]}
          onSourceClick={() => setShowRuntimeSheet(true)}
          chatRepoSnapshot={chatRepoSnapshot}
        />

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-[#1a2233] px-4 py-3">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-300" aria-hidden="true" />
            <h2 className="text-lg font-black text-[#e1e4e8]">Sovereign Chat</h2>
            <span className="rounded-full border border-[#252e3e] bg-[#161b2e] px-2 py-0.5 text-xs text-[#768390]">
              OpenHands Runtime
            </span>
          </div>

          <div
            ref={scrollRef}
            className="scrollbar-thin min-h-0 flex-1 overflow-y-auto bg-[#0b101c] px-0 py-4"
            aria-label="Sovereign Chat Verlauf"
            data-testid="sovereign-chat-body-window"
          >
            {!wishText.trim() && !chatRepoSnapshot ? (
              <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-5 py-10 text-center">
                <div className="text-6xl" aria-hidden="true">🐥</div>
                <p className="mt-4 text-3xl font-black text-[#e1e4e8]">Let&apos;s start building!</p>
                <p className="mt-3 max-w-xl text-sm leading-6 text-[#768390]">
                  Schreib dein Ziel oder füge eine GitHub-URL ein. Sovereign lädt Kontext, prüft Gates und führt dich nur bei echten Stop-Punkten.
                </p>
                <div className="mt-6 grid w-full gap-3 sm:grid-cols-2" aria-label="Schnellvorschläge">
                  {IDEA_OPTIONS.slice(0, 4).map((option) => (
                    <button
                      key={option.label}
                      type="button"
                      className="rounded-2xl border border-[#252e3e] bg-[#161b2e] px-4 py-4 text-left text-sm font-semibold text-[#cdd9e5] transition hover:border-[#f97316]/60 hover:bg-[#1c2333]"
                      onClick={() => setWishText((current) => appendOption(current, option))}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-3 pb-2">
                {chatLines.map((line) => <Bubble key={line.id} msg={line} />)}

                {agentStatus === 'thinking' ? (
                  <div className="flex items-center gap-2 px-4">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#252e3e] bg-[#161b2e] text-xs text-[#768390]">⬡</div>
                    <div className="flex gap-1">
                      {[0, 1, 2].map((dot) => (
                        <span
                          key={dot}
                          className="h-1.5 w-1.5 rounded-full bg-sky-300"
                          style={{ animation: `sovereignDevChatPulse 1.2s ease-in-out ${dot * 0.2}s infinite` }}
                        />
                      ))}
                    </div>
                  </div>
                ) : null}

                {outcomeHints.length > 0 ? (
                  <div className="px-4" aria-label="OpenHands Ergebnis-Hinweise" data-testid="sovereign-chat-outcome-hints">
                    <div className="space-y-1.5 rounded-xl border border-[#252e3e] bg-[#161b2e] p-3">
                      {outcomeHints.map((hint) => (
                        <p key={`${hint.kind}:${hint.text}`} className="flex items-start gap-2 text-xs text-[#768390]" data-outcome-hint-kind={hint.kind}>
                          <span className="mt-0.5 shrink-0 text-[#252e3e]">›</span>
                          {hint.href ? (
                            <a className="text-sky-300 underline underline-offset-4 hover:text-sky-200" href={hint.href} target="_blank" rel="noreferrer">
                              {hint.text}
                            </a>
                          ) : hint.text}
                        </p>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          <div className="shrink-0 border-t border-[#252e3e] bg-[#0e1525] px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            <form onSubmit={(event) => { void handleComposerSubmit(event); }} data-composer-width="100%">
              <div className="flex items-end gap-2 rounded-xl border border-[#252e3e] bg-[#161b2e] p-2 transition-colors focus-within:border-[#374556]">
                <button
                  type="button"
                  onClick={() => setShowSideMenu(true)}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#252e3e] bg-[#1c2333] text-[#768390] transition hover:border-[#374556] hover:text-[#cdd9e5] active:bg-[#232d3f]"
                  aria-label="Sovereign Menü öffnen"
                >
                  ☰
                </button>

                <textarea
                  id={SOVEREIGN_FORM_MISSION.id}
                  name={SOVEREIGN_FORM_MISSION.id}
                  data-role={SOVEREIGN_FORM_MISSION.dataRole}
                  data-testid={SOVEREIGN_FORM_MISSION.testId}
                  className="max-h-32 min-h-10 flex-1 resize-none overflow-y-auto bg-transparent px-1 py-1.5 text-[14px] leading-6 text-[#cdd9e5] outline-none placeholder:text-[#4b5563]"
                  value={wishText}
                  onChange={(event) => setWishText(event.target.value)}
                  onInput={(event) => {
                    const target = event.currentTarget;
                    target.style.height = 'auto';
                    target.style.height = `${Math.min(target.scrollHeight, 128)}px`;
                  }}
                  placeholder={chatRepoSnapshot ? `Frage zu ${chatRepoSnapshot.name}…` : 'GitHub URL oder Nachricht…'}
                  aria-label={SOVEREIGN_FORM_MISSION.ariaLabel}
                  rows={1}
                />

                <button
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-base font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-30"
                  style={{
                    background: localRepoLoading || (!parseDevChatGithubUrl(wishText) && (agentDisabled || !wishText.trim()))
                      ? '#1c2333'
                      : '#f97316',
                  }}
                  type="submit"
                  disabled={localRepoLoading || (!parseDevChatGithubUrl(wishText) && (agentDisabled || !wishText.trim()))}
                  data-role={SOVEREIGN_ACTION_START_TASK.dataRole}
                  data-testid={SOVEREIGN_ACTION_START_TASK.testId}
                  aria-label="Agent starten"
                  data-state={agentDisabled ? 'disabled' : 'idle'}
                >
                  {localRepoLoading ? '…' : '↑'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>

      {showRuntimeSheet ? <RuntimeSourceSheet sources={runtimeSources} current={runtimeSource} onClose={() => setShowRuntimeSheet(false)} /> : null}

      {showSideMenu ? (
        <SideMenu
          onClose={() => setShowSideMenu(false)}
          onGenerateIdeas={onGenerateIdeas}
          onGenerateErrorWorkflow={onGenerateErrorWorkflow}
          onPublishDraftPr={onPublishDraftPr}
          isPublishing={isPublishing}
          chatRepoSnapshot={chatRepoSnapshot}
        />
      ) : null}

      {showOpenHandsBriefing && openhandsConfig ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#0e1525]/85 p-4"
          style={{ backdropFilter: 'blur(6px)' }}
          onClick={() => setShowOpenHandsBriefing(false)}
        >
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-[#252e3e]" onClick={(e) => e.stopPropagation()}>
            <OpenHandsOperatorBriefingPanel config={openhandsConfig} onClose={() => setShowOpenHandsBriefing(false)} initiallyExpanded={true} />
          </div>
        </div>
      ) : null}
    </section>
  );
}
