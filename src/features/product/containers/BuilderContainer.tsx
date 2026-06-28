import React, {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
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
import type {
  OpenHandsEnterpriseConfig,
  OpenHandsJobSnapshot,
} from '../runtime/openhandsEnterpriseRuntime';

// ─────────────────────────────────────────────────────────────
// TYPES  (identical props to BuilderContainer — drop-in swap)
// ─────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────

const MAX_W = 393;
const CUTE_THINKING_FRAME_MS = 1100;
const builderContainerContract = getSovereignContainerContract('builder');

const C = {
  bg:        '#0e1116',
  surface:   '#161c24',
  border:    '#232d3a',
  borderHov: '#2e3d50',
  accent:    '#00d9b1',
  accentDim: '#00d9b122',
  orange:    '#f97316',
  text:      '#cdd9e5',
  textSub:   '#768390',
  textMuted: '#3d4f61',
  green:     '#34d399',
  sky:       '#22d3ee',
  amber:     '#fbbf24',
  violet:    '#a78bfa',
  rose:      '#fb7185',
  userBg:    '#1a2d45',
  asstBg:    '#161c24',
} as const;

const STATUS_COLOR: Record<AgentStatus, string> = {
  idle:     C.green,
  thinking: C.sky,
  editing:  C.amber,
  running:  C.violet,
  error:    C.rose,
};

const STATUS_LABEL: Record<AgentStatus, string> = {
  idle:     'bereit',
  thinking: 'denkt…',
  editing:  'editiert',
  running:  'läuft',
  error:    'fehler',
};

const TIER_COLOR: Record<RuntimeTier, string> = {
  ready:   C.green,
  active:  C.sky,
  blocked: C.rose,
};

const IDEA_OPTIONS: IdeaOption[] = [
  { label: '✨ Feature',    text: 'Schlage mir ein kleines, cooles Feature vor, prüfe zuerst das Repo und baue es nur als echten, sicheren Draft-PR-tauglichen Änderungspfad.' },
  { label: '🐛 Bug Fix',   text: 'Analysiere den aktuellen Fehlerstatus, finde die betroffenen Dateien und erzeuge einen minimalen echten Fix mit passenden Tests.' },
  { label: '📱 Android UX',text: 'Verbessere die Bedienbarkeit auf Android: Chat, Navigation, Statushinweise und klare Nutzerführung ohne neue Fensterflut.' },
  { label: '🔒 Runtime',   text: 'Prüfe den schwächsten Ablauf und ergänze Runtime-Checks, Validierungen und Tests ohne Mock-, Stub- oder Facade-Live-Pfade.' },
];

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────

function appendOption(current: string, option: IdeaOption): string {
  const clean = current.trim();
  if (!clean) return option.text;
  if (clean.includes(option.text)) return clean;
  return `${clean}\n${option.text}`;
}

function normalizeMissionText(value: string): string {
  return value
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function collapseRepeatedAnalyzedMission(value: string): string {
  let clean = normalizeMissionText(value).replace(
    /^Ideenfabrik Auftrag:\s*Ideenfabrik Auftrag:/i,
    'Ideenfabrik Auftrag:',
  );
  const marker = '\nRepository-Kontext:';
  const firstContext = clean.indexOf(marker);
  const secondContext =
    firstContext >= 0 ? clean.indexOf(marker, firstContext + marker.length) : -1;
  if (secondContext >= 0) clean = clean.slice(0, secondContext).trim();
  return clean;
}

function isAnalyzedMission(value: string): boolean {
  const clean = collapseRepeatedAnalyzedMission(value).toLowerCase();
  return (
    clean.startsWith('ideenfabrik auftrag:') &&
    clean.includes('repository-kontext:') &&
    clean.includes('umsetzung:')
  );
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
  const wish =
    missionToWishText(args.wish) ||
    'Verbessere das Sovereign Tool so, dass es für Nutzer klar bedienbar ist.';
  const repoState = args.repoReady
    ? 'Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.'
    : `Repo-Snapshot ist noch nicht bereit: ${args.repoReason}`;
  return [
    'Ideenfabrik Auftrag:', wish, '',
    'Repository-Kontext:', repoState, '',
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
  const files = (job.changedFiles ?? [])
    .filter((f) => typeof f === 'string' && f.trim())
    .map((f) => f.trim());
  const draftPrUrl = safeHttpsUrl(job.draftPrUrl);
  if (job.openHandsId?.trim())
    hints.push({ kind: 'runtime', text: `🐤 OpenHands ID: ${job.openHandsId.trim()}` });
  if (files.length > 0)
    hints.push({ kind: 'files', text: `${files.length} Datei(en) geändert · Details im Files-Menü` });
  if (draftPrUrl)
    hints.push({ kind: 'draft-pr', text: 'Draft PR bereit · Öffnen', href: draftPrUrl });
  if ((job.status === 'blocked' || job.status === 'failed') && job.lastError?.trim())
    hints.push({ kind: 'stopper', text: job.lastError.trim() });
  if (job.status === 'completed' && files.length === 0 && !draftPrUrl)
    hints.push({ kind: 'done', text: 'Küken hat fertig gepiepst · Keine Dateiänderung gemeldet' });
  return hints;
}

function deriveAgentStatus(args: {
  readonly repoBusy: boolean;
  readonly runtimeBusy: boolean;
  readonly isPublishing: boolean;
  readonly openhandsIsRunning?: boolean;
  readonly openhandsJob?: OpenHandsJobSnapshot;
  readonly localRepoLoading: boolean;
  readonly localRepoError: boolean;
}): AgentStatus {
  if (args.localRepoError || args.openhandsJob?.status === 'failed' || args.openhandsJob?.status === 'blocked') return 'error';
  if (args.isPublishing || args.openhandsJob?.status === 'running') return 'running';
  if ((args.openhandsJob?.changedFiles?.length ?? 0) > 0 || Boolean(args.openhandsJob?.draftPrUrl)) return 'editing';
  if (args.localRepoLoading || args.openhandsIsRunning || args.repoBusy || args.runtimeBusy) return 'thinking';
  return 'idle';
}

function fmtTime(ts: number): string {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function buildChatLines(args: {
  readonly wishText: string;
  readonly repoReady: boolean;
  readonly repoReason: string;
  readonly runtimeThinkingActive: boolean;
  readonly cuteThinkingLabel: string;
  readonly sovereignSummary: string;
  readonly disabledReason?: string;
  readonly openhandsJob?: OpenHandsJobSnapshot;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
  readonly chatRepoError: string | null;
}): ChatLine[] {
  const lines: ChatLine[] = [];
  const firstFile = splitFilePath(
    args.openhandsJob?.changedFiles?.[0] ?? args.chatRepoSnapshot?.lastFile,
  );
  const effectiveRepoReady = args.repoReady || Boolean(args.chatRepoSnapshot);

  lines.push({
    id: 'system:repo',
    role: 'system',
    text: effectiveRepoReady
      ? `Repo verbunden · ${args.chatRepoSnapshot ? summarizeDevChatRepoSnapshot(args.chatRepoSnapshot) : 'echte Runtime-Gates aktiv'}`
      : `Repo fehlt · ${args.repoReason}`,
  });

  if (args.chatRepoError)
    lines.push({ id: 'system:repo-error', role: 'system', text: `Repo-Ladefehler: ${args.chatRepoError}` });

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
      text: `Repo geladen: ${args.chatRepoSnapshot.name}\nBranch: ${args.chatRepoSnapshot.branch}\nStruktur: ${args.chatRepoSnapshot.dirs.join(' · ') || 'keine Top-Level-Ordner erkannt'}\n${args.chatRepoSnapshot.fileCount} Einträge.`,
      file: args.chatRepoSnapshot.lastFile,
      path: args.chatRepoSnapshot.lastPath,
    });
  }

  if (args.runtimeThinkingActive)
    lines.push({ id: 'thought:runtime', role: 'thought', text: args.cuteThinkingLabel });
  if (args.sovereignSummary.trim())
    lines.push({ id: 'assistant:summary', role: 'assistant', text: args.sovereignSummary.trim(), ...firstFile });
  if (args.disabledReason?.trim())
    lines.push({ id: 'system:blocked', role: 'system', text: args.disabledReason.trim() });

  return lines;
}

// ─────────────────────────────────────────────────────────────
// SUB-COMPONENTS
// ─────────────────────────────────────────────────────────────

function Ampel({ status }: { status: AgentStatus }) {
  const col = STATUS_COLOR[status];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      {(['idle', 'thinking', 'editing'] as AgentStatus[]).map((s) => (
        <span
          key={s}
          style={{
            display: 'inline-block',
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: status === s ? STATUS_COLOR[s] : `${STATUS_COLOR[s]}30`,
            boxShadow: status === s ? `0 0 6px ${STATUS_COLOR[s]}` : 'none',
            transition: 'all 0.3s',
          }}
        />
      ))}
      <span style={{ fontFamily: 'monospace', fontSize: 10, color: col, marginLeft: 2 }}>
        {STATUS_LABEL[status]}
      </span>
    </div>
  );
}

function TopBar({
  status, repoReady, chatRepoSnapshot, repoReason,
  onMenuOpen, onSourceClick, source,
}: {
  status: AgentStatus;
  repoReady: boolean;
  chatRepoSnapshot: DevChatRepoSnapshot | null;
  repoReason: string;
  onMenuOpen: () => void;
  onSourceClick: () => void;
  source: { label: string; tier: RuntimeTier };
}) {
  const repoLabel = chatRepoSnapshot
    ? `${chatRepoSnapshot.name}:${chatRepoSnapshot.branch}`
    : repoReady ? 'Repo ✓' : 'Repo fehlt';
  const repoColor = (repoReady || chatRepoSnapshot) ? C.green : C.amber;

  return (
    <div style={{
      height: 52,
      background: C.surface,
      borderBottom: `1px solid ${C.border}`,
      display: 'flex',
      alignItems: 'center',
      padding: '0 12px',
      gap: 10,
      flexShrink: 0,
    }}>
      <button
        type="button"
        onClick={onMenuOpen}
        aria-label="Menü"
        style={{
          width: 40,
          height: 40,
          borderRadius: 10,
          background: C.bg,
          border: `1px solid ${C.border}`,
          color: C.textSub,
          fontSize: 16,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >☰</button>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontFamily: 'monospace',
            fontSize: 13,
            fontWeight: 700,
            color: C.text,
            letterSpacing: -0.3,
          }}>Sovereign</span>
          <span style={{
            fontFamily: 'monospace',
            fontSize: 9,
            padding: '2px 6px',
            borderRadius: 10,
            background: `${C.accent}18`,
            color: C.accent,
            border: `1px solid ${C.accent}33`,
          }}>DevChat</span>
        </div>
        <div style={{
          fontFamily: 'monospace',
          fontSize: 9,
          color: repoColor,
          marginTop: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {repoLabel}
          {chatRepoSnapshot && (
            <span style={{ color: C.textMuted }}> · {chatRepoSnapshot.fileCount} files</span>
          )}
        </div>
      </div>

      <Ampel status={status} />

      <button
        type="button"
        onClick={onSourceClick}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '6px 10px',
          borderRadius: 8,
          background: C.bg,
          border: `1px solid ${C.border}`,
          color: TIER_COLOR[source.tier],
          fontFamily: 'monospace',
          fontSize: 9,
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >
        <span style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: TIER_COLOR[source.tier],
          boxShadow: `0 0 5px ${TIER_COLOR[source.tier]}`,
          display: 'inline-block',
        }} />
        <span style={{ display: 'none' }}>{source.label}</span>
        RT
      </button>
    </div>
  );
}

function FileBadge({ path, file }: { path?: string; file?: string }) {
  if (!file) return null;
  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      fontFamily: 'monospace',
      fontSize: 9,
      padding: '3px 8px',
      borderRadius: 6,
      background: 'rgba(251,191,36,0.1)',
      border: '1px solid rgba(251,191,36,0.25)',
      color: C.amber,
      marginBottom: 4,
      maxWidth: '100%',
      overflow: 'hidden',
    }}>
      <span style={{ color: C.textMuted }}>{path}</span>
      <span>{file}</span>
    </div>
  );
}

function ThoughtBubble({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const short = text.length > 72 ? `${text.slice(0, 72)}…` : text;
  return (
    <button
      type="button"
      onClick={() => setOpen((v) => !v)}
      style={{
        width: '100%',
        background: 'transparent',
        border: 'none',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: '4px 16px',
        cursor: 'pointer',
        textAlign: 'left',
      }}
    >
      <span style={{
        color: open ? C.accent : C.textMuted,
        marginTop: 2,
        flexShrink: 0,
        fontSize: 11,
        transition: 'color 0.2s',
      }}>✦</span>
      <span style={{
        fontFamily: 'monospace',
        fontSize: 10,
        fontStyle: 'italic',
        lineHeight: 1.6,
        color: open ? C.textSub : C.textMuted,
        transition: 'color 0.2s',
      }}>{open ? text : short}</span>
    </button>
  );
}

function Bubble({ msg, now }: { msg: ChatLine; now: number }) {
  const isUser = msg.role === 'user';

  if (msg.role === 'system') {
    return (
      <div style={{ padding: '4px 16px', textAlign: 'center' }}>
        <span style={{
          display: 'inline-block',
          fontFamily: 'monospace',
          fontSize: 10,
          padding: '3px 12px',
          borderRadius: 20,
          background: C.surface,
          border: `1px solid ${C.border}`,
          color: C.textMuted,
        }}>{msg.text}</span>
      </div>
    );
  }

  if (msg.role === 'thought') return <ThoughtBubble text={msg.text} />;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-end',
      gap: 8,
      padding: '2px 12px',
      flexDirection: isUser ? 'row-reverse' : 'row',
    }}>
      {!isUser && (
        <div style={{
          width: 30,
          height: 30,
          borderRadius: 10,
          flexShrink: 0,
          background: C.surface,
          border: `1px solid ${C.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 13,
          color: C.textSub,
          marginBottom: 2,
        }}>⬡</div>
      )}

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        maxWidth: '82%',
        alignItems: isUser ? 'flex-end' : 'flex-start',
        gap: 2,
      }}>
        <FileBadge path={msg.path} file={msg.file} />

        <div style={{
          padding: '11px 14px',
          background: isUser ? C.userBg : C.asstBg,
          borderRadius: isUser ? '18px 18px 4px 18px' : '4px 18px 18px 18px',
          border: `1px solid ${isUser ? '#243c5a' : C.border}`,
          color: C.text,
          fontSize: 14,
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
        }}>
          {msg.text}
        </div>

        <span style={{ fontFamily: 'monospace', fontSize: 9, color: C.textMuted }}>
          {fmtTime(now)}
        </span>
      </div>
    </div>
  );
}

function ThinkingDots() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px' }}>
      <div style={{
        width: 30,
        height: 30,
        borderRadius: 10,
        background: C.surface,
        border: `1px solid ${C.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 13,
        color: C.textSub,
      }}>⬡</div>
      <div style={{ display: 'flex', gap: 5, paddingLeft: 2 }}>
        {[0, 1, 2].map((i) => (
          <span key={i} style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: C.sky,
            display: 'inline-block',
            animation: `sdc-pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  );
}

function OutcomeHints({ hints }: { hints: ChatOutcomeHint[] }) {
  if (hints.length === 0) return null;
  return (
    <div style={{ padding: '0 12px 8px' }}>
      <div style={{
        borderRadius: 10,
        border: `1px solid ${C.border}`,
        background: C.surface,
        padding: '10px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}>
        {hints.map((h) => (
          <div
            key={`${h.kind}:${h.text}`}
            style={{ display: 'flex', alignItems: 'flex-start', gap: 6, fontSize: 12, color: C.textSub }}
          >
            <span style={{ color: C.border, marginTop: 2, flexShrink: 0 }}>›</span>
            {h.href ? (
              <a
                href={h.href}
                target="_blank"
                rel="noreferrer"
                style={{ color: C.sky, textDecoration: 'underline', textUnderlineOffset: 3 }}
              >
                {h.text}
              </a>
            ) : h.text}
          </div>
        ))}
      </div>
    </div>
  );
}

function WelcomeScreen({ onIdea }: { onIdea: (opt: IdeaOption) => void }) {
  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '32px 20px',
      textAlign: 'center',
    }}>
      <div style={{
        width: 72,
        height: 72,
        borderRadius: 20,
        background: `${C.accent}12`,
        border: `2px solid ${C.accent}40`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 32,
        marginBottom: 20,
      }}>🐥</div>

      <h2 style={{
        fontFamily: 'monospace',
        fontSize: 20,
        fontWeight: 800,
        color: C.text,
        marginBottom: 8,
        letterSpacing: -0.5,
      }}>Let&apos;s build!</h2>

      <p style={{
        fontSize: 13,
        color: C.textSub,
        lineHeight: 1.6,
        maxWidth: 300,
        marginBottom: 28,
      }}>
        Schreib dein Ziel oder füge eine GitHub-URL ein.
        Sovereign prüft Gates und handelt nur bei echten Stop-Punkten.
      </p>

      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 10,
        width: '100%',
        maxWidth: 340,
      }}>
        {IDEA_OPTIONS.map((opt) => (
          <button
            key={opt.label}
            type="button"
            onClick={() => onIdea(opt)}
            style={{
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: 14,
              padding: '14px 12px',
              fontFamily: 'monospace',
              fontSize: 11,
              color: C.text,
              fontWeight: 600,
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'border-color 0.15s, background 0.15s',
              lineHeight: 1.3,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = C.borderHov;
              (e.currentTarget as HTMLButtonElement).style.background = '#1c2630';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = C.border;
              (e.currentTarget as HTMLButtonElement).style.background = C.surface;
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function RuntimeSheet({
  sources, current, onClose,
}: {
  sources: Array<{ id: string; label: string; tier: RuntimeTier; description: string }>;
  current: { id: string };
  onClose: () => void;
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 100,
        background: 'rgba(14,17,22,0.85)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: C.surface,
          borderRadius: '20px 20px 0 0',
          border: `1px solid ${C.border}`,
          borderBottom: 'none',
          padding: '0 0 24px',
        }}
      >
        <div style={{
          width: 36,
          height: 4,
          borderRadius: 2,
          background: C.border,
          margin: '12px auto 16px',
        }} />
        <div style={{
          fontFamily: 'monospace',
          fontSize: 9,
          textAlign: 'center',
          color: C.textMuted,
          letterSpacing: 1.5,
          textTransform: 'uppercase',
          marginBottom: 12,
        }}>Runtime Quelle</div>

        {sources.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={onClose}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 20px',
              border: 'none',
              borderLeft: `3px solid ${s.id === current.id ? TIER_COLOR[s.tier] : 'transparent'}`,
              cursor: 'pointer',
              background: s.id === current.id ? `${TIER_COLOR[s.tier]}08` : 'transparent',
            } as React.CSSProperties}
          >
            <span style={{
              width: 9,
              height: 9,
              borderRadius: '50%',
              background: TIER_COLOR[s.tier],
              boxShadow: `0 0 6px ${TIER_COLOR[s.tier]}`,
              flexShrink: 0,
            }} />
            <span style={{ flex: 1, textAlign: 'left' }}>
              <span style={{ display: 'block', fontFamily: 'monospace', fontSize: 12, color: C.text }}>
                {s.label}
              </span>
              <span style={{ fontFamily: 'monospace', fontSize: 9, color: C.textMuted }}>
                {s.description}
              </span>
            </span>
            {s.id === current.id && (
              <span style={{ color: TIER_COLOR[s.tier], fontSize: 12 }}>✓</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

function SideDrawer({
  onClose, onGenerateIdeas, onGenerateErrorWorkflow,
  onPublishDraftPr, isPublishing, chatRepoSnapshot, onCancelOpenHands,
  openhandsIsRunning,
}: {
  onClose: () => void;
  onGenerateIdeas: () => void;
  onGenerateErrorWorkflow: () => void;
  onPublishDraftPr: () => void;
  isPublishing: boolean;
  chatRepoSnapshot: DevChatRepoSnapshot | null;
  onCancelOpenHands?: () => void;
  openhandsIsRunning?: boolean;
}) {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 90,
        display: 'flex',
      }}
    >
      <div
        onClick={onClose}
        style={{ flex: 1, background: 'rgba(14,17,22,0.7)', backdropFilter: 'blur(4px)' }}
      />

      <div style={{
        width: 'min(80vw, 300px)',
        background: C.surface,
        borderLeft: `1px solid ${C.border}`,
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '-8px 0 32px rgba(0,0,0,0.5)',
      }}>
        <div style={{
          padding: '16px 16px 12px',
          borderBottom: `1px solid ${C.border}`,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}>
          <div style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            background: `${C.accent}12`,
            border: `1px solid ${C.accent}33`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16,
          }}>⬡</div>
          <div>
            <div style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 700, color: C.text }}>
              Sovereign Studio
            </div>
            <div style={{ fontFamily: 'monospace', fontSize: 9, color: C.textMuted }}>
              NoCode Agent Runtime
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              marginLeft: 'auto',
              background: 'transparent',
              border: 'none',
              color: C.textMuted,
              fontSize: 16,
              cursor: 'pointer',
              padding: '4px',
              borderRadius: 6,
            }}
          >✕</button>
        </div>

        {chatRepoSnapshot && (
          <div style={{
            margin: '12px 12px 0',
            padding: '10px 12px',
            borderRadius: 10,
            background: `${C.green}08`,
            border: `1px solid ${C.green}22`,
          }}>
            <div style={{ fontFamily: 'monospace', fontSize: 10, fontWeight: 600, color: C.green }}>
              {chatRepoSnapshot.name}
            </div>
            <div style={{ fontFamily: 'monospace', fontSize: 9, color: C.textSub, marginTop: 2 }}>
              {chatRepoSnapshot.branch} · {chatRepoSnapshot.fileCount} files
            </div>
          </div>
        )}

        <div style={{
          margin: '10px 12px 0',
          padding: '10px 12px',
          borderRadius: 10,
          background: C.bg,
          border: `1px solid ${C.border}`,
        }}>
          <div style={{ fontFamily: 'monospace', fontSize: 9, color: C.textMuted, marginBottom: 4 }}>
            Cloudflare Workers
          </div>
          <div style={{
            fontFamily: 'monospace',
            fontSize: 8,
            color: C.textMuted,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {SOVEREIGN_WORKER_CHAT}
          </div>
          <div style={{
            fontFamily: 'monospace',
            fontSize: 8,
            color: C.textMuted,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {SOVEREIGN_WORKER_KV}
          </div>
        </div>

        <div style={{ flex: 1, padding: '12px 12px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button
            type="button"
            onClick={() => { onGenerateIdeas(); onClose(); }}
            data-role={SOVEREIGN_ACTION_ANALYZE_MISSION.dataRole}
            data-testid={SOVEREIGN_ACTION_ANALYZE_MISSION.testId}
            aria-label={SOVEREIGN_ACTION_ANALYZE_MISSION.ariaLabel}
            style={{
              width: '100%',
              padding: '12px 14px',
              borderRadius: 12,
              background: C.bg,
              border: `1px solid ${C.border}`,
              color: C.text,
              fontFamily: 'monospace',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              textAlign: 'left',
            }}
          >
            🔍 Interne Prüfung
          </button>

          <button
            type="button"
            onClick={() => { onGenerateErrorWorkflow(); onClose(); }}
            style={{
              width: '100%',
              padding: '12px 14px',
              borderRadius: 12,
              background: 'rgba(251,191,36,0.06)',
              border: `1px solid ${C.amber}33`,
              color: C.amber,
              fontFamily: 'monospace',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              textAlign: 'left',
            }}
          >
            ⚠ Fehleranalyse
          </button>

          {openhandsIsRunning && onCancelOpenHands && (
            <button
              type="button"
              onClick={() => { onCancelOpenHands(); onClose(); }}
              style={{
                width: '100%',
                padding: '12px 14px',
                borderRadius: 12,
                background: 'rgba(251,49,85,0.07)',
                border: '1px solid rgba(251,49,85,0.25)',
                color: C.rose,
                fontFamily: 'monospace',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              ✕ Agent stoppen
            </button>
          )}
        </div>

        <div style={{ padding: '12px' }}>
          <button
            type="button"
            onClick={() => { onPublishDraftPr(); onClose(); }}
            data-role={SOVEREIGN_ACTION_DRAFT_PR.dataRole}
            data-testid={SOVEREIGN_ACTION_DRAFT_PR.testId}
            aria-label={SOVEREIGN_ACTION_DRAFT_PR.ariaLabel}
            style={{
              width: '100%',
              padding: '14px',
              borderRadius: 14,
              background: C.orange,
              border: 'none',
              color: '#fff',
              fontFamily: 'monospace',
              fontSize: 13,
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: `0 4px 16px ${C.orange}40`,
            }}
          >
            {builderPublishLabel(isPublishing)}
          </button>
        </div>
      </div>
    </div>
  );
}

function Composer({
  value, onChange, onSubmit, disabled, loading, placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  loading: boolean;
  placeholder: string;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, []);

  return (
    <div style={{
      flexShrink: 0,
      padding: '10px 10px',
      paddingBottom: 'max(10px, env(safe-area-inset-bottom))',
      background: C.surface,
      borderTop: `1px solid ${C.border}`,
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: 8,
        background: C.bg,
        border: `1px solid ${C.border}`,
        borderRadius: 16,
        padding: '8px 8px 8px 14px',
        transition: 'border-color 0.15s',
      }}>
        <textarea
          ref={textareaRef}
          id={SOVEREIGN_FORM_MISSION.id}
          name={SOVEREIGN_FORM_MISSION.id}
          data-role={SOVEREIGN_FORM_MISSION.dataRole}
          data-testid={SOVEREIGN_FORM_MISSION.testId}
          aria-label={SOVEREIGN_FORM_MISSION.ariaLabel}
          value={value}
          rows={1}
          onChange={(e) => { onChange(e.target.value); resize(); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (!disabled && !loading) onSubmit();
            }
          }}
          placeholder={placeholder}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            fontFamily: 'system-ui, -apple-system, sans-serif',
            fontSize: 14,
            lineHeight: 1.5,
            color: C.text,
            resize: 'none',
            maxHeight: 120,
            minHeight: 24,
            overflowY: 'auto',
            '--placeholder-color': C.textMuted,
          } as React.CSSProperties}
        />

        <button
          type="button"
          onClick={onSubmit}
          disabled={disabled || loading}
          aria-label="Senden"
          data-role={SOVEREIGN_ACTION_START_TASK.dataRole}
          data-testid={SOVEREIGN_ACTION_START_TASK.testId}
          style={{
            width: 40,
            height: 40,
            borderRadius: 12,
            flexShrink: 0,
            background: disabled || loading ? C.surface : C.orange,
            border: 'none',
            color: '#fff',
            fontSize: 16,
            cursor: disabled || loading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'background 0.2s, box-shadow 0.2s',
            boxShadow: disabled || loading ? 'none' : `0 2px 12px ${C.orange}50`,
            opacity: disabled || loading ? 0.45 : 1,
          }}
        >
          {loading ? '…' : '↑'}
        </button>
      </div>

      <div style={{
        fontFamily: 'monospace',
        fontSize: 8,
        color: C.textMuted,
        marginTop: 5,
        paddingLeft: 14,
      }}>
        Agent starten · Enter senden · Shift+Enter Zeilenumbruch
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────

export function BuilderContainer({
  mission, repoReady, repoReason, repoBusy, runtimeBusy, isPublishing,
  sovereignSummary, sovereignPreview, onMissionChange, onGenerateIdeas,
  onGenerateErrorWorkflow, onPublishDraftPr,
  openhandsReady, openhandsConfig, openhandsJob, openhandsJobStatus,
  openhandsIsRunning, onStartOpenHands, onCancelOpenHands,
}: BuilderContainerProps) {

  const [wishText, setWishText] = useState(() => missionToWishText(mission));
  const [thinkingFrameIndex, setTFI] = useState(0);
  const [showRuntimeSheet, setShowRuntime] = useState(false);
  const [showSideMenu, setShowSide] = useState(false);
  const [showOpenHandsBriefing, setOHB] = useState(false);
  const [chatRepoSnapshot, setChatRepo] = useState<DevChatRepoSnapshot | null>(null);
  const [chatRepoError, setChatRepoError] = useState<string | null>(null);
  const [localRepoLoading, setRepoLoading] = useState(false);
  const lastMissionRef = useRef(mission);
  const scrollRef = useRef<HTMLDivElement>(null);
  const nowRef = useRef(Date.now());

  const state = deriveBuilderContainerState({
    repoReady: repoReady || Boolean(chatRepoSnapshot),
    repoBusy: repoBusy || localRepoLoading,
    runtimeBusy,
    isPublishing,
    mission,
    sovereignSummary,
    sovereignPreview,
  });

  const effectiveRepoReady = repoReady || Boolean(chatRepoSnapshot);
  const effectiveRepoReason = chatRepoSnapshot
    ? summarizeDevChatRepoSnapshot(chatRepoSnapshot)
    : repoReason;

  const analyzedMission = useMemo(
    () => buildAnalyzedMission({ wish: wishText, repoReady: effectiveRepoReady, repoReason: effectiveRepoReason }),
    [effectiveRepoReady, effectiveRepoReason, wishText],
  );

  const executableOpenHandsMission = useMemo(() => {
    const v = collapseRepeatedAnalyzedMission(mission);
    return isAnalyzedMission(v) ? v : collapseRepeatedAnalyzedMission(analyzedMission);
  }, [analyzedMission, mission]);

  const runtimeThinkingActive = Boolean(
    openhandsIsRunning || repoBusy || localRepoLoading || runtimeBusy || isPublishing,
  );

  const cuteThinkingLabel = useMemo(
    () => formatCuteThinkingLabel({ index: thinkingFrameIndex, active: runtimeThinkingActive, status: openhandsJobStatus }),
    [openhandsJobStatus, runtimeThinkingActive, thinkingFrameIndex],
  );

  const outcomeHints = useMemo(() => buildOutcomeHints(openhandsJob), [openhandsJob]);

  const agentDisabled = !effectiveRepoReady || repoBusy || localRepoLoading || runtimeBusy
    || Boolean(openhandsIsRunning) || !openhandsReady || !onStartOpenHands;

  const agentStatus = deriveAgentStatus({
    repoBusy,
    runtimeBusy,
    isPublishing,
    openhandsIsRunning,
    openhandsJob,
    localRepoLoading,
    localRepoError: Boolean(chatRepoError),
  });

  const sourceTier: RuntimeTier = openhandsReady
    ? (runtimeThinkingActive ? 'active' : 'ready') : 'blocked';

  const runtimeSource = {
    id: 'openhands-runtime',
    label: openhandsReady ? 'OpenHands' : 'OpenHands offline',
    tier: sourceTier,
    description: openhandsReady ? 'Echte Agent-Runtime verbunden' : 'Agent-Runtime nicht verbunden',
    available: Boolean(openhandsReady),
  };

  const runtimeSources = [
    runtimeSource,
    {
      id: 'worker-chat',
      label: 'Worker Chat',
      tier: 'ready' as RuntimeTier,
      description: SOVEREIGN_WORKER_CHAT,
      available: true,
    },
    {
      id: 'worker-kv',
      label: 'Worker KV',
      tier: 'ready' as RuntimeTier,
      description: SOVEREIGN_WORKER_KV,
      available: true,
    },
    {
      id: 'worker-models',
      label: `${DEV_CHAT_WORKER_MODELS.length} Modelle`,
      tier: 'ready' as RuntimeTier,
      description: DEV_CHAT_WORKER_MODELS.map((m) => m.label).join(' · '),
      available: true,
    },
    {
      id: 'repo-snapshot',
      label: effectiveRepoReady ? 'Repo Snapshot' : 'Repo fehlt',
      tier: (effectiveRepoReady ? 'ready' : 'blocked') as RuntimeTier,
      description: effectiveRepoReady ? effectiveRepoReason : repoReason,
      available: effectiveRepoReady,
    },
  ];

  const chatLines = useMemo(
    () => buildChatLines({
      wishText,
      repoReady: effectiveRepoReady,
      repoReason: effectiveRepoReason,
      runtimeThinkingActive,
      cuteThinkingLabel,
      sovereignSummary,
      disabledReason: state.disabledReason,
      openhandsJob,
      chatRepoSnapshot,
      chatRepoError,
    }),
    [
      chatRepoError,
      chatRepoSnapshot,
      cuteThinkingLabel,
      effectiveRepoReady,
      effectiveRepoReason,
      openhandsJob,
      runtimeThinkingActive,
      sovereignSummary,
      state.disabledReason,
      wishText,
    ],
  );

  useEffect(() => {
    if (!runtimeThinkingActive) {
      setTFI(0);
      return;
    }
    const h = window.setInterval(() => setTFI((c) => c + 1), CUTE_THINKING_FRAME_MS);
    return () => window.clearInterval(h);
  }, [runtimeThinkingActive]);

  useEffect(() => {
    if (mission === lastMissionRef.current) return;
    lastMissionRef.current = mission;
    setWishText(missionToWishText(mission));
  }, [mission]);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [chatLines.length, outcomeHints.length, runtimeThinkingActive]);

  const analyzeWish = () => {
    const clean = collapseRepeatedAnalyzedMission(analyzedMission);
    lastMissionRef.current = clean;
    onMissionChange(clean);
  };

  const startAgentFromChat = () => {
    const clean = collapseRepeatedAnalyzedMission(executableOpenHandsMission);
    lastMissionRef.current = clean;
    onMissionChange(clean);
    onStartOpenHands?.(clean);
  };

  const handleSubmit = async () => {
    const parsedRepo = parseDevChatGithubUrl(wishText);
    if (parsedRepo) {
      setRepoLoading(true);
      setChatRepoError(null);
      const result = await fetchDevChatRepoTree(parsedRepo);
      setRepoLoading(false);
      if (result.ok && result.snapshot) {
        setChatRepo(result.snapshot);
        const summary = summarizeDevChatRepoSnapshot(result.snapshot);
        lastMissionRef.current = summary;
        onMissionChange(`Repo laden via Chat:\n${summary}\n${result.snapshot.files.slice(0, 60).map((f) => f.path).join('\n')}`);
        return;
      }
      setChatRepoError(result.error ?? 'Repo konnte nicht geladen werden.');
      return;
    }
    if (agentDisabled) {
      analyzeWish();
      return;
    }
    startAgentFromChat();
  };

  const submitDisabled = localRepoLoading || (!parseDevChatGithubUrl(wishText) && (agentDisabled || !wishText.trim()));

  useEffect(() => {
    nowRef.current = Date.now();
  }, [chatLines.length]);

  return (
    <section
      className={builderContainerContract.rootClass}
      data-role={builderContainerContract.dataRole}
      data-testid={builderContainerContract.testId}
      data-layout="devchat-replit"
      aria-label={builderContainerContract.ariaLabel}
      style={{
        width: '100%',
        maxWidth: MAX_W,
        margin: '0 auto',
        height: '100dvh',
        display: 'flex',
        flexDirection: 'column',
        background: C.bg,
        color: C.text,
        fontFamily: 'system-ui, -apple-system, sans-serif',
        overflow: 'hidden',
        position: 'relative',
        WebkitTapHighlightColor: 'transparent',
      }}
    >
      <style>{`
        @keyframes sdc-pulse {
          0%,100%{opacity:1;transform:scale(1)}
          50%{opacity:.3;transform:scale(.8)}
        }
        textarea::placeholder { color: #3d4f61; }
        ::-webkit-scrollbar { width: 3px; height: 3px; }
        ::-webkit-scrollbar-thumb { background: #232d3a; border-radius: 2px; }
        ::-webkit-scrollbar-track { background: transparent; }
      `}</style>

      <TopBar
        status={agentStatus}
        repoReady={effectiveRepoReady}
        chatRepoSnapshot={chatRepoSnapshot}
        repoReason={effectiveRepoReason}
        onMenuOpen={() => setShowSide(true)}
        onSourceClick={() => setShowRuntime(true)}
        source={runtimeSource}
      />

      <div
        ref={scrollRef}
        data-testid="sovereign-chat-body-window"
        aria-label="Sovereign Chat Verlauf"
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          background: C.bg,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {!wishText.trim() && !chatRepoSnapshot ? (
          <WelcomeScreen onIdea={(opt) => setWishText((c) => appendOption(c, opt))} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '16px 0 8px' }}>
            {chatLines.map((line) => (
              <Bubble key={line.id} msg={line} now={nowRef.current} />
            ))}

            {agentStatus === 'thinking' && <ThinkingDots />}

            <OutcomeHints hints={outcomeHints} />

            <div style={{ height: 8 }} />
          </div>
        )}
      </div>

      <Composer
        value={wishText}
        onChange={setWishText}
        onSubmit={() => { void handleSubmit(); }}
        disabled={submitDisabled}
        loading={localRepoLoading}
        placeholder={
          chatRepoSnapshot
            ? `Frage zu ${chatRepoSnapshot.name}…`
            : 'GitHub URL oder Auftrag…'
        }
      />

      {showRuntimeSheet && (
        <RuntimeSheet
          sources={runtimeSources}
          current={runtimeSource}
          onClose={() => setShowRuntime(false)}
        />
      )}

      {showSideMenu && (
        <SideDrawer
          onClose={() => setShowSide(false)}
          onGenerateIdeas={onGenerateIdeas}
          onGenerateErrorWorkflow={onGenerateErrorWorkflow}
          onPublishDraftPr={onPublishDraftPr}
          isPublishing={isPublishing}
          chatRepoSnapshot={chatRepoSnapshot}
          onCancelOpenHands={onCancelOpenHands}
          openhandsIsRunning={openhandsIsRunning}
        />
      )}

      {showOpenHandsBriefing && openhandsConfig && (
        <div
          onClick={() => setOHB(false)}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 50,
            background: 'rgba(14,17,22,0.88)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%',
              maxWidth: 440,
              maxHeight: '90vh',
              overflowY: 'auto',
              borderRadius: 20,
              border: `1px solid ${C.border}`,
            }}
          >
            <OpenHandsOperatorBriefingPanel
              config={openhandsConfig}
              onClose={() => setOHB(false)}
              initiallyExpanded={true}
            />
          </div>
        </div>
      )}
    </section>
  );
}

export default BuilderContainer;
