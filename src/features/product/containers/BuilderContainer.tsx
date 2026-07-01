import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  builderPublishLabel,
  deriveBuilderContainerState,
} from "../runtime/builderContainerRuntime";
import { getSovereignContainerContract } from "../runtime/sovereignContainerContracts";
import { SOVEREIGN_FORM_MISSION } from "../runtime/sovereignFormContracts";
import {
  SOVEREIGN_ACTION_ANALYZE_MISSION,
  SOVEREIGN_ACTION_DRAFT_PR,
  SOVEREIGN_ACTION_REPAIR_LOG,
  SOVEREIGN_ACTION_START_TASK,
} from "../runtime/sovereignActionContracts";
import { formatCuteWorkStateLabel } from "../runtime/cuteThinkingStatus";
import {
  DEV_CHAT_WORKER_MODELS,
  SOVEREIGN_WORKER_CHAT,
  SOVEREIGN_WORKER_KV,
  explainDevChatWorkerDiagnostic,
  fetchDevChatRepoTree,
  fetchDevChatWorkerHealth,
  fetchDevChatWorkerReply,
  parseDevChatGithubUrl,
  streamDevChatWorkerReply,
  summarizeDevChatRepoSnapshot,
  type DevChatRepoSnapshot,
  type DevChatWorkerDiagnostic,
  type DevChatWorkerHealthResult,
  type DevChatWorkerMessage,
} from "../runtime/devChatWorkerBridge";
import { OpenHandsOperatorBriefingPanel } from "../components/OpenHandsOperatorBriefingPanel";
import {
  WorkerBlockerCard,
  WorkerDegradedBanner,
} from "../components/WorkerBlockerCard";
import { DraftPrCard } from "../components/DraftPrCard";
import { ChatMarkdown } from "../components/ChatMarkdown";
import { PacedChatText } from "../components/PacedChatText";
import { GitHubAccessCard } from "../components/GitHubAccessCard";
import { OpenHandsJobTruthCard } from "../components/OpenHandsJobTruthCard";
import { RepoTreeExplorer } from "../components/RepoTreeExplorer";
import { SlashCommandMenu } from "../components/SlashCommandMenu";
import {
  exportChatHistory,
  shareChatExport,
} from "../runtime/chatExportRuntime";
import {
  SOVEREIGN_SLASH_COMMANDS,
  matchingSlashCommands,
  parseSlashCommand,
  shouldShowSlashMenu,
  type SlashCommandDefinition,
} from "../runtime/slashCommandRuntime";
import { createRepoFilePrompt } from "../runtime/repoTreeExplorerRuntime";
import {
  copyAndroidBubbleText,
  createAndroidFollowUpDraft,
  detectAndroidQuickRepoUrl,
  triggerAndroidHaptic,
} from "../runtime/androidQuickInteractionRuntime";
import {
  deriveRuntimeInspectorSignals,
  buildPatInspectorStateFromStore,
  type RuntimeInspectorSignal,
  type BudInspectorState,
} from "../runtime/runtimeInspectorPanelRuntime";
import {
  createPatternMemoryStore,
  type PatternMemoryStore,
} from "../runtime/patternMemoryRuntime";
import type { LlmRouteSelectionResult } from "../runtime/llmRouteBudgetRuntime";
import type {
  OpenHandsEnterpriseConfig,
  OpenHandsJobSnapshot,
} from "../runtime/openhandsEnterpriseRuntime";
import {
  createGitHubAccessSnapshot,
  requestGitHubAccess,
  startGitHubAccessValidation,
  failGitHubAccessValidation,
  validateGitHubTokenFormat,
  canPerformGitHubWrite,
  type GitHubAccessSnapshot,
} from "../runtime/githubAccessRuntime";
import { evaluateInputPolicy } from "../runtime/secureInputGuard";
import { checkChatClaim } from "../runtime/chatClaimGuard";
import {
  createIdleSnapshot,
  transitionIntentDetected,
  transitionExecutorStarting,
  transitionExecutorRunning,
  transitionBranchCreated,
  transitionCommitCreated,
  transitionDraftPrReady,
  transitionBlocked,
  transitionFailed,
  type AgentWorkSnapshot,
} from "../runtime/agentWorkRuntime";
import { AgentWorkTimeline } from "../components/AgentWorkTimeline";
import { AgentResultCard } from "../components/AgentResultCard";
import { SovereignToolLauncher, type ToolId } from "../components/SovereignToolLauncher";
import { usePatternMemoryStore } from "../hooks/usePatternMemoryStore";

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
  readonly kind: "runtime" | "files" | "draft-pr" | "stopper" | "done";
  readonly text: string;
  readonly href?: string;
}

type AgentStatus = "idle" | "thinking" | "editing" | "running" | "error";
type ChatRole = "system" | "thought" | "user" | "assistant";
type RuntimeTier = "ready" | "active" | "blocked";
// AppControl additions
type ModuleId =
  "chat" | "init" | "router" | "pattern" | "sync" | "orchestr" | "logger" | "budget";
type SignalType = "idle" | "active" | "processing" | "warning" | "error";
type AnimPhase =
  "idle" | "spinup" | "working" | "completing" | "done" | "error";
type CondStatus = "pass" | "fail" | "wait";

interface ChatLine {
  readonly id: string;
  readonly role: ChatRole;
  readonly text: string;
  readonly file?: string;
  readonly path?: string;
  readonly createdAt?: number;
}

interface RuntimeSource {
  readonly id: string;
  readonly label: string;
  readonly tier: RuntimeTier;
  readonly description: string;
  readonly available: boolean;
}

interface ModuleCfg {
  id: ModuleId;
  short: string;
  icon: string;
  color: string;
}

interface ModuleCond {
  label: string;
  status: CondStatus;
}

interface WorkerRuntimeBlocker {
  readonly message: string;
  readonly diagnostic: DevChatWorkerDiagnostic;
  readonly health?: DevChatWorkerHealthResult;
  readonly createdAt: number;
}

// ─────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────

const MAX_W = 393;
const CUTE_THINKING_FRAME_MS = 1100;
const CUTE_IDLE_FRAME_MS = 1450;
const WORKSTATE_TYPE_FRAME_MS = 35;
const WORKSTATE_TYPE_STEP = 2;
const builderContainerContract = getSovereignContainerContract("builder");

// Original colour palette from BuilderContainer v3 — untouched
const C = {
  bg: "#0e1116",
  surface: "#161c24",
  border: "#232d3a",
  borderHov: "#2e3d50",
  accent: "#00d9b1",
  accentDim: "#00d9b122",
  orange: "#f97316",
  text: "#cdd9e5",
  textSub: "#768390",
  textMuted: "#3d4f61",
  green: "#34d399",
  sky: "#22d3ee",
  amber: "#fbbf24",
  violet: "#a78bfa",
  rose: "#fb7185",
  userBg: "#1a2d45",
  asstBg: "#161c24",
} as const;

const STATUS_COLOR: Record<AgentStatus, string> = {
  idle: C.green,
  thinking: C.sky,
  editing: C.amber,
  running: C.violet,
  error: C.rose,
};
const STATUS_LABEL: Record<AgentStatus, string> = {
  idle: "bereit",
  thinking: "denkt…",
  editing: "editiert",
  running: "läuft",
  error: "fehler",
};
const TIER_COLOR: Record<RuntimeTier, string> = {
  ready: C.green,
  active: C.sky,
  blocked: C.rose,
};

// AppControl module definitions
const MODULES: ModuleCfg[] = [
  { id: "chat", short: "CHAT", icon: "⬡", color: C.sky },
  { id: "init", short: "INT", icon: "⬡", color: C.green },
  { id: "router", short: "ROU", icon: "⟳", color: C.sky },
  { id: "pattern", short: "PAT", icon: "◈", color: C.violet },
  { id: "sync", short: "SYN", icon: "⇄", color: C.accent },
  { id: "orchestr", short: "ORC", icon: "⚡", color: C.amber },
  { id: "logger", short: "LOG", icon: "▣", color: C.rose },
  { id: "budget", short: "BUD", icon: "◎", color: C.green },
];

const INIT_CONDITIONS: Partial<Record<ModuleId, ModuleCond[]>> = {
  init: [
    { label: "Module loaded", status: "pass" },
    { label: "Config valid", status: "pass" },
  ],
  router: [
    { label: "Signal ACTIVE", status: "pass" },
    { label: "No override", status: "pass" },
    { label: "Tab completed", status: "wait" },
  ],
  pattern: [
    { label: "Seq ≥ 2", status: "pass" },
    { label: "Confidence ≥ 0.80", status: "fail" },
    { label: "Store > 0", status: "wait" },
  ],
  sync: [
    { label: "Signal ACTIVE", status: "pass" },
    { label: "Inactivity > 3s", status: "wait" },
    { label: "Override clear", status: "pass" },
  ],
  orchestr: [
    { label: "All tabs ready", status: "wait" },
    { label: "AutoSwitch ON", status: "pass" },
    { label: "Pattern matched", status: "fail" },
  ],
  logger: [
    { label: "Logger active", status: "pass" },
    { label: "Buffer not full", status: "pass" },
  ],
  budget: [
    { label: "Route active", status: "wait" },
    { label: "Budget available", status: "pass" },
    { label: "Ledger synced", status: "pass" },
  ],
};

const IDEA_OPTIONS: IdeaOption[] = [
  {
    label: "✨ Feature",
    text: "Schlage mir ein kleines, cooles Feature vor, prüfe zuerst das Repo und baue es nur als echten, sicheren Draft-PR-tauglichen Änderungspfad.",
  },
  {
    label: "🐛 Bug Fix",
    text: "Analysiere den aktuellen Fehlerstatus, finde die betroffenen Dateien und erzeuge einen minimalen echten Fix mit passenden Tests.",
  },
  {
    label: "📱 Android UX",
    text: "Verbessere die Bedienbarkeit auf Android: Chat, Navigation, Statushinweise und klare Nutzerführung ohne neue Fensterflut.",
  },
  {
    label: "🔒 Runtime",
    text: "Prüfe den schwächsten Ablauf und ergänze Runtime-Checks, Validierungen und Tests ohne Mock-, Stub- oder Facade-Live-Pfade.",
  },
];

// ─────────────────────────────────────────────────────────────
// HELPERS  (verbatim from BuilderContainer v3)
// ─────────────────────────────────────────────────────────────

function appendOption(current: string, option: IdeaOption): string {
  const clean = current.trim();
  if (!clean) return option.text;
  if (clean.includes(option.text)) return clean;
  return `${clean}\n${option.text}`;
}

function normalizeMissionText(value: string): string {
  return value
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function collapseRepeatedAnalyzedMission(value: string): string {
  let clean = normalizeMissionText(value).replace(
    /^Ideenfabrik Auftrag:\s*Ideenfabrik Auftrag:/i,
    "Ideenfabrik Auftrag:",
  );
  const marker = "\nRepository-Kontext:";
  const firstContext = clean.indexOf(marker);
  const secondContext =
    firstContext >= 0
      ? clean.indexOf(marker, firstContext + marker.length)
      : -1;
  if (secondContext >= 0) clean = clean.slice(0, secondContext).trim();
  return clean;
}

function isAnalyzedMission(value: string): boolean {
  const clean = collapseRepeatedAnalyzedMission(value).toLowerCase();
  return (
    clean.startsWith("ideenfabrik auftrag:") &&
    clean.includes("repository-kontext:") &&
    clean.includes("umsetzung:")
  );
}

function missionToWishText(value: string): string {
  const clean = collapseRepeatedAnalyzedMission(value);
  if (!clean) return "";
  if (!isAnalyzedMission(clean))
    return clean.replace(/^Ideenfabrik Auftrag:\s*/i, "").trim();
  const withoutHeader = clean.replace(/^Ideenfabrik Auftrag:\s*/i, "").trim();
  const contextIndex = withoutHeader.indexOf("\nRepository-Kontext:");
  return (
    contextIndex >= 0 ? withoutHeader.slice(0, contextIndex) : withoutHeader
  ).trim();
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
    "Verbessere das Sovereign Tool so, dass es für Nutzer klar bedienbar ist.";
  const repoState = args.repoReady
    ? "Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden."
    : `Repo-Snapshot ist noch nicht bereit: ${args.repoReason}`;
  return [
    "Ideenfabrik Auftrag:",
    wish,
    "",
    "Repository-Kontext:",
    repoState,
    "",
    "Umsetzung:",
    "- Antworte wie ein hilfreicher No-Code-Freund: kurz, freundlich und handlungsorientiert.",
    "- Analysiere zuerst die vorhandene Repo-Struktur und betroffene Dateien.",
    "- Erzeuge echte Änderungen im passenden Codepfad oder erkläre klar, warum ein Stop-Gate blockiert.",
    "- Nutze vorhandene Pattern Memory Hinweise, wenn sie passen.",
    "- Halte Sovereign Tool getrennt von WASD/Science-Portal Drift.",
    "- Nutze Runtime-Checks, Validierungen und Tests, soweit sinnvoll.",
    "- Keine Mock-, Stub- oder Facade-Live-Pfade.",
    "- Kein Auto-Merge. Ergebnis nur als prüfbarer Draft PR oder klarer Blocker.",
  ].join("\n");
}

function safeHttpsUrl(value: string | undefined): string | undefined {
  const clean = value?.trim();
  return clean && clean.startsWith("https://") ? clean : undefined;
}

function splitFilePath(filePath: string | undefined): {
  path?: string;
  file?: string;
} {
  const clean = filePath?.trim();
  if (!clean) return {};
  const slash = clean.lastIndexOf("/");
  if (slash < 0) return { file: clean };
  return { path: `${clean.slice(0, slash + 1)}`, file: clean.slice(slash + 1) };
}

function buildOutcomeHints(
  job: OpenHandsJobSnapshot | undefined,
): ChatOutcomeHint[] {
  if (!job || job.status === "idle") return [];
  const hints: ChatOutcomeHint[] = [];
  const files = (job.changedFiles ?? [])
    .filter((f) => typeof f === "string" && f.trim())
    .map((f) => f.trim());
  const draftPrUrl = safeHttpsUrl(job.draftPrUrl);
  if (job.openHandsId?.trim())
    hints.push({
      kind: "runtime",
      text: `🐤 OpenHands ID: ${job.openHandsId.trim()}`,
    });
  if (files.length > 0)
    hints.push({
      kind: "files",
      text: `${files.length} Datei(en) geändert · Details im Files-Menü`,
    });
  if (draftPrUrl)
    hints.push({
      kind: "draft-pr",
      text: "Draft PR bereit · Öffnen",
      href: draftPrUrl,
    });
  if (
    (job.status === "blocked" || job.status === "failed") &&
    job.lastError?.trim()
  )
    hints.push({ kind: "stopper", text: job.lastError.trim() });
  if (job.status === "completed" && files.length === 0 && !draftPrUrl)
    hints.push({
      kind: "done",
      text: "Küken hat fertig gepiepst · Keine Dateiänderung gemeldet",
    });
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
  if (
    args.localRepoError ||
    args.openhandsJob?.status === "failed" ||
    args.openhandsJob?.status === "blocked"
  )
    return "error";
  if (args.isPublishing || args.openhandsJob?.status === "running")
    return "running";
  if (
    (args.openhandsJob?.changedFiles?.length ?? 0) > 0 ||
    Boolean(args.openhandsJob?.draftPrUrl)
  )
    return "editing";
  if (
    args.localRepoLoading ||
    args.openhandsIsRunning ||
    args.repoBusy ||
    args.runtimeBusy
  )
    return "thinking";
  return "idle";
}

function fmtTime(ts: number): string {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function buildChatLines(args: {
  readonly repoReady: boolean;
  readonly repoReason: string;
  readonly runtimeThinkingActive: boolean;
  readonly cuteThinkingLabel: string;
  readonly sovereignSummary: string;
  readonly disabledReason?: string;
  readonly openhandsJob?: OpenHandsJobSnapshot;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
  readonly chatRepoError: string | null;
  readonly chatHistory: readonly ChatLine[];
}): ChatLine[] {
  const lines: ChatLine[] = [];
  const firstFile = splitFilePath(
    args.openhandsJob?.changedFiles?.[0] ?? args.chatRepoSnapshot?.lastFile,
  );
  const effectiveRepoReady = args.repoReady || Boolean(args.chatRepoSnapshot);

  lines.push({
    id: "system:repo",
    role: "system",
    text: effectiveRepoReady
      ? `Repo verbunden · ${args.chatRepoSnapshot ? summarizeDevChatRepoSnapshot(args.chatRepoSnapshot) : "echte Runtime-Gates aktiv"}`
      : `Repo fehlt · ${args.repoReason}`,
  });

  if (args.chatRepoError)
    lines.push({
      id: "system:repo-error",
      role: "system",
      text: `Repo-Ladefehler: ${args.chatRepoError}`,
    });
  if (args.sovereignSummary.trim())
    lines.push({
      id: "assistant:summary",
      role: "assistant",
      text: args.sovereignSummary.trim(),
      ...firstFile,
    });

  lines.push(...args.chatHistory);

  if (
    args.cuteThinkingLabel.trim() &&
    (args.runtimeThinkingActive ||
      args.chatHistory.length > 0 ||
      args.chatRepoSnapshot ||
      args.disabledReason?.trim())
  ) {
    lines.push({
      id: "thought:runtime",
      role: "thought",
      text: args.cuteThinkingLabel,
    });
  }

  if (args.disabledReason?.trim())
    lines.push({
      id: "system:blocked",
      role: "system",
      text: args.disabledReason.trim(),
    });
  return lines;
}

function createChatLineId(
  prefix: ChatRole | "repo" | "worker",
  index: number,
): string {
  return `${prefix}:${Date.now()}:${index}`;
}

// Intent detection from workerIntentDetector module
import {
  isOpenHandsExecutionIntent,
  isWorkerRetryIntent,
  isWorkerDiagnosticQuestion,
} from "../runtime/workerIntentDetector";

function buildWorkerSystemPrompt(args: {
  readonly repoReady: boolean;
  readonly repoReason: string;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
}): string {
  const repoContext = args.chatRepoSnapshot
    ? [
        `Repo: ${args.chatRepoSnapshot.owner}/${args.chatRepoSnapshot.repo}`,
        `Branch: ${args.chatRepoSnapshot.branch}`,
        `Dateien: ${args.chatRepoSnapshot.fileCount}`,
        `Top-Level: ${args.chatRepoSnapshot.dirs.join(" · ") || "keine Top-Level-Ordner erkannt"}`,
        `Letzter relevanter Pfad: ${[args.chatRepoSnapshot.lastPath, args.chatRepoSnapshot.lastFile].filter(Boolean).join("") || "nicht erkannt"}`,
      ].join("\n")
    : args.repoReady
      ? `Repo-Kontext: ${args.repoReason}`
      : `Repo-Kontext fehlt: ${args.repoReason}`;

  return [
    "Du bist Sovereign Worker Chat, die Standard-LLM-Route des Sovereign Tools.",
    "Antworte kurz, freundlich, konkret und ohne erfundene Erfolge.",
    "Keine Mock-, Stub- oder Facade-Live-Pfade behaupten.",
    "Wenn Code-Ausführung oder Draft-PR nötig ist, erkläre klar, dass OpenHands der Executor ist.",
    repoContext,
  ].join("\n");
}

function buildWorkerMessages(args: {
  readonly submittedText: string;
  readonly chatHistory: readonly ChatLine[];
  readonly repoReady: boolean;
  readonly repoReason: string;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
}): DevChatWorkerMessage[] {
  const recentMessages = args.chatHistory
    .filter((line) => line.role === "user" || line.role === "assistant")
    .slice(-8)
    .map((line): DevChatWorkerMessage => ({
      role: line.role === "user" ? "user" : "assistant",
      content: line.text,
    }));

  return [
    { role: "system", content: buildWorkerSystemPrompt(args) },
    ...recentMessages,
    { role: "user", content: args.submittedText },
  ];
}

function buildWorkerBlockerAnswer(args: {
  readonly blocker: WorkerRuntimeBlocker;
  readonly repoReady: boolean;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
  readonly openhandsReady?: boolean;
}): string {
  const { diagnostic, health } = args.blocker;
  const repoLine = args.chatRepoSnapshot
    ? `Repo-Kontext bleibt geladen: ${args.chatRepoSnapshot.owner}/${args.chatRepoSnapshot.repo} · ${args.chatRepoSnapshot.branch} · ${args.chatRepoSnapshot.fileCount} files.`
    : args.repoReady
      ? "Repo-Kontext ist weiterhin bereit."
      : "Repo-Kontext fehlt noch.";
  const healthLine = health
    ? `Health: ${health.status ?? "n/a"} · secret=${health.secretConfigured === undefined ? "unbekannt" : health.secretConfigured ? "ok" : "fehlt"} · upstream=${health.upstreamConfigured === undefined ? "unbekannt" : health.upstreamConfigured ? "ok" : "fehlt"} · model=${health.model ?? diagnostic.model}.`
    : "Health: noch nicht geprüft.";
  const codeLine = diagnostic.canClientFix
    ? "Einschätzung: Der Fehler ist wahrscheinlich durch unseren App-Request oder die Route im Code korrigierbar."
    : "Einschätzung: Der letzte Fehler liegt wahrscheinlich in Worker-Konfiguration, Worker-Runtime oder Upstream-Provider und muss über Cloudflare/Bridge-Diagnose geprüft werden.";

  return [
    "Ich wiederhole den kaputten Worker-Call nicht blind.",
    explainDevChatWorkerDiagnostic(diagnostic),
    healthLine,
    repoLine,
    args.openhandsReady
      ? "OpenHands Executor ist nur für echte Code-/Draft-PR-Aufträge zuständig und wurde für diese Chatfrage nicht gestartet."
      : "OpenHands Executor ist nicht bereit; normale Chatfragen bleiben Worker-Route.",
    codeLine,
  ].join("\n");
}

function composerRouteHint(args: {
  readonly draft: string;
  readonly workerBlocked: boolean;
  readonly agentDisabled: boolean;
}): string {
  const clean = args.draft.trim();
  if (!clean)
    return "Worker Chat senden · Repo-URL laden · OpenHands nur bei Code-Auftrag";
  const quickRepo = detectAndroidQuickRepoUrl(clean);
  if (quickRepo.recognized) return quickRepo.hint;
  if (parseDevChatGithubUrl(clean)) return "Repo laden · Runtime Snapshot";
  if (isOpenHandsExecutionIntent(clean))
    return args.agentDisabled
      ? "OpenHands blockiert · Worker erklärt zuerst"
      : "OpenHands Executor starten";
  if (args.workerBlocked && !isWorkerRetryIntent(clean))
    return "Worker blockiert · lokale Diagnose statt blindem Retry";
  if (args.workerBlocked && isWorkerRetryIntent(clean))
    return "Worker Retry · Diagnose wird aktualisiert";
  return "Worker Chat senden · Enter senden · Shift+Enter Zeilenumbruch";
}

function confidenceLabel(value: number): string {
  if (value >= 0.65) return "stable";
  if (value >= 0.35) return "watch";
  return "low";
}

function phaseFromSignalAndConditions(
  signal: SignalType,
  conds: readonly ModuleCond[],
): AnimPhase {
  if (
    signal === "error" ||
    conds.some((condition) => condition.status === "fail")
  )
    return "error";
  if (signal === "processing") return "working";
  if (conds.some((condition) => condition.status === "wait"))
    return signal === "idle" ? "idle" : "working";
  if (signal === "warning") return "working";
  if (signal === "active") return "done";
  return "idle";
}

// ─────────────────────────────────────────────────────────────
// PAL ROUTER  (inline — uses DEV_CHAT_WORKER_MODELS from bridge)
// ─────────────────────────────────────────────────────────────

interface PALDecision {
  tier: "fast" | "smart" | "power";
  modelId: string;
  modelLabel: string;
  score: number;
  costFactor: number;
}
const ARCH_KW = [
  "architektur",
  "architecture",
  "refactor",
  "redesign",
  "migration",
  "pattern",
  "dependency",
  "abstraction",
  "interface",
  "contract",
];
const PLAN_KW = [
  "plan",
  "planung",
  "roadmap",
  "strategie",
  "feature",
  "implement",
  "konzept",
  "vorschlag",
  "analyse",
  "überblick",
];
const QUICK_KW = [
  "kurz",
  "quick",
  "schnell",
  "simple",
  "einfach",
  "was ist",
  "what is",
  "define",
  "erkläre",
  "explain",
  "tipp",
];
const THINK_KW = [
  "denk nach",
  "think",
  "tiefgründig",
  "trade-off",
  "kompromiss",
  "komplexität",
  "algorithmus",
  "optimiere",
];

function palRoute(
  message: string,
  histDepth: number,
  fileCount: number,
  prior: PALDecision[],
): PALDecision {
  const lower = message.toLowerCase();
  let score = 0;
  const len = message.length;
  if (len >= 300) score += 15;
  else if (len >= 150) score += 10;
  else if (len >= 60) score += 5;
  score += Math.min(((message.match(/```/g) ?? []).length / 2) * 5, 15);
  if (fileCount > 0) score += 10;
  if (ARCH_KW.some((k) => lower.includes(k))) score += 20;
  if (THINK_KW.some((k) => lower.includes(k))) score += 18;
  if (PLAN_KW.some((k) => lower.includes(k))) score += 12;
  if (QUICK_KW.some((k) => lower.includes(k))) score -= 15;
  if (histDepth > 10) score += 5;
  score = Math.max(0, Math.min(100, score));
  const powerCount = prior.filter((d) => d.tier === "power").length;
  const tier: "fast" | "smart" | "power" =
    score <= 33
      ? "fast"
      : score <= 66
        ? "smart"
        : powerCount >= 10
          ? "smart"
          : "power";
  const tierModelMap: Record<string, string[]> = {
    fast: ["llama-3-8b", "gemma-7b"],
    smart: ["qwen-14b", "llama-3.1-8b"],
    power: ["deepseek-r1", "mistral-7b"],
  };
  const matched =
    DEV_CHAT_WORKER_MODELS.find((m) => tierModelMap[tier].includes(m.id)) ??
    DEV_CHAT_WORKER_MODELS[0];
  const costMap = { fast: 1, smart: 10, power: 30 };
  return {
    tier,
    modelId: matched?.id ?? "llama-3-8b",
    modelLabel: matched?.label ?? "Llama 3 8B",
    score,
    costFactor: costMap[tier],
  };
}

function sameRecord<T extends string>(
  a: Record<string, T>,
  b: Record<string, T>,
): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if (a[key] !== b[key]) return false;
  }
  return true;
}

function sameConditions(
  a: Partial<Record<ModuleId, ModuleCond[]>>,
  b: Partial<Record<ModuleId, ModuleCond[]>>,
): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

// ── Issue #446: Derive BUD inspector state from real palDecisions
const BUD_ROUTE_MAP = {
  fast:  { id: "fast",  label: "Fast",  budgetByPlan: { session: Infinity }, priority: 1 },
  smart: { id: "smart", label: "Smart", budgetByPlan: { session: Infinity }, priority: 2 },
  power: { id: "power", label: "Power", budgetByPlan: { session: Infinity }, priority: 3 },
} as const;

function deriveBudStateFromPalDecisions(
  palDecisions: Array<{ tier: "fast" | "smart" | "power" }>,
): BudInspectorState {
  const fastCount  = palDecisions.filter((d) => d.tier === "fast").length;
  const smartCount = palDecisions.filter((d) => d.tier === "smart").length;
  const powerCount = palDecisions.filter((d) => d.tier === "power").length;

  const parts: string[] = [];
  if (fastCount  > 0) parts.push(`Fast: ${fastCount}`);
  if (smartCount > 0) parts.push(`Smart: ${smartCount}`);
  if (powerCount > 0) parts.push(`Power: ${powerCount}`);
  const budgetSummary =
    parts.length > 0 ? parts.join(" · ") : "Keine Routings in dieser Sitzung.";

  if (palDecisions.length === 0) {
    return { selectionResult: null, budgetSummary };
  }

  const lastTier = palDecisions[palDecisions.length - 1].tier;
  const selectedRoute = BUD_ROUTE_MAP[lastTier];
  const selectionResult: LlmRouteSelectionResult = {
    status: "available",
    selectedRoute,
    reason: `Route "${selectedRoute.label}" zuletzt genutzt.`,
    exhaustedRouteIds: [],
  };
  return { selectionResult, budgetSummary };
}

function buildRuntimeConfidence(args: {
  readonly effectiveRepoReady: boolean;
  readonly openhandsReady?: boolean;
  readonly runtimeThinkingActive: boolean;
  readonly blocked: boolean;
  readonly palDecisions: number;
  readonly outcomeHints: number;
}): number {
  let score = 0.12;
  if (args.effectiveRepoReady) score += 0.22;
  if (args.openhandsReady) score += 0.2;
  if (args.runtimeThinkingActive) score += 0.12;
  if (args.palDecisions > 0) score += 0.12;
  if (args.outcomeHints > 0) score += 0.1;
  if (args.blocked) score -= 0.18;
  return Math.max(0, Math.min(1, score));
}

// ─────────────────────────────────────────────────────────────
// SUB-COMPONENTS
// ─────────────────────────────────────────────────────────────

// Ampel (verbatim from v3)
function Ampel({ status }: { status: AgentStatus }) {
  const col = STATUS_COLOR[status];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      {(["idle", "thinking", "editing"] as AgentStatus[]).map((s) => (
        <span
          key={s}
          style={{
            display: "inline-block",
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: status === s ? STATUS_COLOR[s] : `${STATUS_COLOR[s]}30`,
            boxShadow: status === s ? `0 0 6px ${STATUS_COLOR[s]}` : "none",
            transition: "all 0.3s",
          }}
        />
      ))}
      <span
        style={{
          fontFamily: "monospace",
          fontSize: 10,
          color: col,
          marginLeft: 2,
        }}
      >
        {STATUS_LABEL[status]}
      </span>
    </div>
  );
}

// Module lamps row — AppControl addition
function ModuleLamps({
  modules,
  signals,
  activeTab,
  onTabClick,
}: {
  modules: ModuleCfg[];
  signals: Record<string, SignalType>;
  activeTab: string;
  onTabClick: (id: string) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        borderTop: `1px solid ${C.border}`,
        overflowX: "auto",
      }}
    >
      {modules
        .filter((m) => m.id !== "chat")
        .map((m) => {
          const sig = signals[m.id] ?? "idle";
          const active = sig !== "idle";
          const isTab = activeTab === m.id;
          return (
            <button
              key={m.id}
              type="button"
              onClick={() => onTabClick(m.id)}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 3,
                padding: "4px 8px",
                background: isTab ? `${m.color}10` : "transparent",
                border: "none",
                borderRight: `1px solid ${C.border}`,
                borderTop: isTab
                  ? `2px solid ${m.color}`
                  : "2px solid transparent",
                cursor: "pointer",
                flexShrink: 0,
                minWidth: 44,
                marginTop: isTab ? 0 : 2,
              }}
              aria-label={m.id}
            >
              <span
                style={{
                  display: "inline-block",
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: active ? m.color : `${m.color}28`,
                  boxShadow: active ? `0 0 4px ${m.color}` : "none",
                  transition: "all 0.3s",
                  animation:
                    sig === "processing"
                      ? "sdc-pulse 1s ease-in-out infinite"
                      : "none",
                }}
              />
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 7.5,
                  color: isTab ? m.color : C.textMuted,
                  transition: "color 0.15s",
                }}
              >
                {m.short}
              </span>
            </button>
          );
        })}
    </div>
  );
}

// TopBar — v3 verbatim + module lamps + panel toggle + PAL badge
function TopBar({
  status,
  repoReady,
  chatRepoSnapshot,
  repoReason,
  onMenuOpen,
  onRepoClick,
  onSourceClick,
  source,
  modules,
  signals,
  activeTab,
  onTabClick,
  panelOpen,
  onPanelToggle,
  palTier,
  palSavings,
}: {
  status: AgentStatus;
  repoReady: boolean;
  chatRepoSnapshot: DevChatRepoSnapshot | null;
  repoReason: string;
  onMenuOpen: () => void;
  onRepoClick: () => void;
  onSourceClick: () => void;
  source: { label: string; tier: RuntimeTier };
  modules: ModuleCfg[];
  signals: Record<string, SignalType>;
  activeTab: string;
  onTabClick: (id: string) => void;
  panelOpen: boolean;
  onPanelToggle: () => void;
  palTier: string | null;
  palSavings: number | null;
}) {
  const repoLabel = chatRepoSnapshot
    ? `${chatRepoSnapshot.name}:${chatRepoSnapshot.branch}`
    : repoReady
      ? "Repo ✓"
      : "Repo fehlt";
  const repoColor = repoReady || chatRepoSnapshot ? C.green : C.amber;

  return (
    <div
      style={{
        background: C.surface,
        borderBottom: `1px solid ${C.border}`,
        flexShrink: 0,
      }}
    >
      {/* Main top row — verbatim v3 */}
      <div
        style={{
          height: 52,
          display: "flex",
          alignItems: "center",
          padding: "0 12px",
          gap: 10,
        }}
      >
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
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            flexShrink: 0,
          }}
        >
          ☰
        </button>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                fontFamily: "monospace",
                fontSize: 13,
                fontWeight: 700,
                color: C.text,
                letterSpacing: -0.3,
              }}
            >
              Sovereign
            </span>
            <span
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                padding: "2px 6px",
                borderRadius: 10,
                background: `${C.accent}18`,
                color: C.accent,
                border: `1px solid ${C.accent}33`,
              }}
            >
              DevChat
            </span>
            {/* PAL badge */}
            {palTier && (
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 8,
                  padding: "2px 5px",
                  borderRadius: 6,
                  background: `${palTier === "fast" ? C.green : palTier === "smart" ? C.sky : C.violet}18`,
                  color:
                    palTier === "fast"
                      ? C.green
                      : palTier === "smart"
                        ? C.sky
                        : C.violet,
                  border: `1px solid ${palTier === "fast" ? C.green : palTier === "smart" ? C.sky : C.violet}33`,
                }}
              >
                {palTier.toUpperCase()}
                {palSavings !== null ? " · sparsam" : ""}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onRepoClick}
            disabled={!chatRepoSnapshot}
            aria-label={chatRepoSnapshot ? "Repo Inspector öffnen" : undefined}
            style={{
              display: "block",
              width: "100%",
              padding: 0,
              marginTop: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              background: "transparent",
              border: "none",
              color: repoColor,
              cursor: chatRepoSnapshot ? "pointer" : "default",
              fontFamily: "monospace",
              fontSize: 9,
              textAlign: "left",
            }}
          >
            {repoLabel}
            {chatRepoSnapshot && (
              <span style={{ color: C.textMuted }}>
                {" "}
                · {chatRepoSnapshot.fileCount} files
              </span>
            )}
          </button>
        </div>

        <Ampel status={status} />

        <button
          type="button"
          onClick={onSourceClick}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            padding: "6px 10px",
            borderRadius: 8,
            background: C.bg,
            border: `1px solid ${C.border}`,
            color: TIER_COLOR[source.tier],
            fontFamily: "monospace",
            fontSize: 9,
            cursor: "pointer",
            flexShrink: 0,
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: TIER_COLOR[source.tier],
              boxShadow: `0 0 5px ${TIER_COLOR[source.tier]}`,
              display: "inline-block",
            }}
          />
          RT
        </button>

        {/* Panel toggle */}
        <button
          type="button"
          onClick={onPanelToggle}
          style={{
            background: "transparent",
            border: "none",
            color: C.textMuted,
            fontSize: 12,
            cursor: "pointer",
            padding: "4px",
            borderRadius: 6,
          }}
        >
          {panelOpen ? "▴" : "▾"}
        </button>
      </div>

      {/* Module lamps row */}
      <ModuleLamps
        modules={modules}
        signals={signals}
        activeTab={activeTab}
        onTabClick={onTabClick}
      />
    </div>
  );
}

// Collapsible status/log panel
function StatusPanel({
  open,
  logs,
  signals,
  modules,
  onClearLogs,
}: {
  open: boolean;
  logs: Array<{ ts: string; level: string; msg: string; tabId: string }>;
  signals: Record<string, SignalType>;
  modules: ModuleCfg[];
  onClearLogs?: () => void;
}) {
  const [tab, setTab] = useState<"logs" | "signals">("logs");
  if (!open) return null;

  const levelColor: Record<string, string> = {
    info: C.sky,
    signal: C.green,
    warn: C.amber,
    error: C.rose,
    debug: C.textMuted,
  };

  return (
    <div
      style={{
        background: C.surface,
        borderBottom: `1px solid ${C.border}`,
        flexShrink: 0,
      }}
    >
      {/* Sub-tab selector */}
      <div style={{ display: "flex", borderBottom: `1px solid ${C.border}` }}>
        {(["logs", "signals"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            style={{
              flex: 1,
              height: 28,
              background: "transparent",
              border: "none",
              borderBottom: `2px solid ${tab === t ? C.green : "transparent"}`,
              color: tab === t ? C.text : C.textMuted,
              fontFamily: "monospace",
              fontSize: 9.5,
              cursor: "pointer",
              transition: "color 0.15s",
            }}
          >
            {t.toUpperCase()}
          </button>
        ))}
        {/* Clear logs button */}
        {tab === "logs" && logs.length > 0 && (
          <button
            type="button"
            onClick={onClearLogs}
            title="Logs löschen"
            style={{
              position: "absolute",
              right: 8,
              height: 28,
              padding: "0 8px",
              background: "transparent",
              border: "none",
              color: C.textMuted,
              fontSize: 9,
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        )}
      </div>
      {/* Pane */}
      <div
        style={{
          height: 88,
          overflowY: "auto",
          padding: "4px 10px",
          position: "relative",
        }}
      >
        {tab === "logs" &&
          [...logs]
            .reverse()
            .slice(0, 25)
            .map((e, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  gap: 6,
                  fontFamily: "monospace",
                  fontSize: 9.5,
                  lineHeight: 1.65,
                }}
              >
                <span style={{ color: C.textMuted, flexShrink: 0 }}>
                  {e.ts}
                </span>
                <span
                  style={{
                    color: levelColor[e.level] ?? C.textMuted,
                    width: 44,
                    flexShrink: 0,
                    textAlign: "right",
                  }}
                >
                  {e.level.toUpperCase()}
                </span>
                <span style={{ color: C.textSub }}>{e.msg}</span>
              </div>
            ))}
        {tab === "signals" &&
          modules
            .filter((m) => m.id !== "chat")
            .map((m) => {
              const sig = signals[m.id] ?? "idle";
              return (
                <div
                  key={m.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "3px 0",
                    borderBottom: `1px solid ${C.border}`,
                  }}
                >
                  <span
                    style={{
                      display: "inline-block",
                      width: 7,
                      height: 7,
                      borderRadius: "50%",
                      background: sig !== "idle" ? m.color : `${m.color}28`,
                    }}
                  />
                  <span
                    style={{
                      fontFamily: "monospace",
                      fontSize: 9.5,
                      color: m.color,
                      width: 56,
                    }}
                  >
                    {m.id.toUpperCase()}
                  </span>
                  <span
                    style={{
                      fontFamily: "monospace",
                      fontSize: 9.5,
                      color: C.textSub,
                      flex: 1,
                    }}
                  >
                    {sig}
                  </span>
                </div>
              );
            })}
      </div>
    </div>
  );
}

// FileBadge (verbatim v3 + Issue #430 repo inspector affordance)
function FileBadge({
  path,
  file,
  onOpenFile,
}: {
  path?: string;
  file?: string;
  onOpenFile?: (path: string) => void;
}) {
  if (!file) return null;
  const fullPath = `${path ?? ""}${file}`;
  return (
    <button
      type="button"
      onClick={() => onOpenFile?.(fullPath)}
      disabled={!onOpenFile}
      aria-label={`Repo Datei öffnen: ${fullPath}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontFamily: "monospace",
        fontSize: 9,
        padding: "3px 8px",
        borderRadius: 6,
        background: "rgba(251,191,36,0.1)",
        border: "1px solid rgba(251,191,36,0.25)",
        color: C.amber,
        marginBottom: 4,
        maxWidth: "100%",
        overflow: "hidden",
        cursor: onOpenFile ? "pointer" : "default",
      }}
    >
      <span style={{ color: C.textMuted }}>{path}</span>
      <span>{file}</span>
    </button>
  );
}

function useTypedWorkStateText(text: string): string {
  const [visibleChars, setVisibleChars] = useState(text.length);

  useEffect(() => {
    setVisibleChars(Math.min(WORKSTATE_TYPE_STEP, text.length));
    if (!text.length) return undefined;

    const handle = window.setInterval(() => {
      setVisibleChars((current) => {
        if (current >= text.length) return current;
        return Math.min(text.length, current + WORKSTATE_TYPE_STEP);
      });
    }, WORKSTATE_TYPE_FRAME_MS);

    return () => window.clearInterval(handle);
  }, [text]);

  return text.slice(0, visibleChars);
}

// ThoughtBubble: typed runtime workstate text. It displays derived runtime state only.
function ThoughtBubble({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const typedText = useTypedWorkStateText(text);
  const displayText =
    open || typedText.length <= 96 ? typedText : `${typedText.slice(0, 96)}…`;
  return (
    <button
      type="button"
      onClick={() => setOpen((v) => !v)}
      aria-live="polite"
      style={{
        width: "100%",
        background: "transparent",
        border: "none",
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        padding: "4px 16px",
        cursor: "pointer",
        textAlign: "left",
      }}
    >
      <span
        style={{
          fontFamily: "monospace",
          fontSize: 12,
          color: open ? C.sky : C.border,
          marginTop: 1,
          flexShrink: 0,
          transition: "color 0.2s",
        }}
      >
        ✦
      </span>
      <span
        style={{
          fontFamily: "monospace",
          fontSize: 10,
          fontStyle: "italic",
          lineHeight: 1.6,
          color: open ? C.textSub : C.textMuted,
          transition: "color 0.2s",
        }}
      >
        {displayText}
        <span
          aria-hidden="true"
          style={{
            color: C.sky,
            animation: "sdc-typing-caret 0.9s steps(2, start) infinite",
          }}
        >
          ▍
        </span>
      </span>
    </button>
  );
}

// Bubble (verbatim v3 + Issue #427 markdown + Issue #429 long-press)
function Bubble({
  msg,
  now,
  onLongPress,
  onOpenFile,
}: {
  msg: ChatLine;
  now: number;
  onLongPress?: (text: string) => void;
  onOpenFile?: (path: string) => void;
}) {
  const isUser = msg.role === "user";
  const [showMenu, setShowMenu] = useState(false);

  // ── Issue #429: Haptic feedback helper using runtime
  const triggerHaptic = useCallback(
    (type: "light" | "medium" | "heavy" = "light") => {
      triggerAndroidHaptic(typeof navigator === "undefined" ? undefined : navigator, type);
    },
    [],
  );

  if (msg.role === "system")
    return (
      <div style={{ padding: "4px 16px", textAlign: "center" }}>
        <span
          style={{
            display: "inline-block",
            fontFamily: "monospace",
            fontSize: 10,
            padding: "3px 12px",
            borderRadius: 20,
            background: C.surface,
            border: `1px solid ${C.border}`,
            color: C.textMuted,
          }}
        >
          {msg.text}
        </span>
      </div>
    );
  if (msg.role === "thought") return <ThoughtBubble text={msg.text} />;

  // ── Issue #429: Long-press for copy/follow-up using runtime helpers
  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setShowMenu(true);
    triggerHaptic("light");
  };

  const handleCopy = async () => {
    await copyAndroidBubbleText(msg.text, typeof navigator === "undefined" ? undefined : navigator);
    setShowMenu(false);
    triggerHaptic("light");
  };

  const handleFollowUp = () => {
    const draft = createAndroidFollowUpDraft(msg.text);
    if (draft) onLongPress?.(draft);
    setShowMenu(false);
    triggerHaptic("light");
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-end",
        gap: 8,
        padding: "2px 12px",
        flexDirection: isUser ? "row-reverse" : "row",
      }}
      onContextMenu={handleContextMenu}
    >
      {!isUser && (
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 10,
            flexShrink: 0,
            background: C.surface,
            border: `1px solid ${C.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 13,
            color: C.textSub,
            marginBottom: 2,
          }}
        >
          ⬡
        </div>
      )}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          maxWidth: "82%",
          alignItems: isUser ? "flex-end" : "flex-start",
          gap: 2,
        }}
      >
        <FileBadge path={msg.path} file={msg.file} onOpenFile={onOpenFile} />
        <div style={{ position: "relative" }}>
          {/* ── Issue #427: Markdown rendering for assistant bubbles */}
          <div
            style={{
              padding: "11px 14px",
              background: isUser ? C.userBg : C.asstBg,
              borderRadius: isUser
                ? "18px 18px 4px 18px"
                : "4px 18px 18px 18px",
              border: `1px solid ${isUser ? "#243c5a" : C.border}`,
              color: C.text,
              fontSize: 14,
              lineHeight: 1.6,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              boxShadow: "0 1px 4px rgba(0,0,0,0.3)",
            }}
          >
            {isUser ? msg.text : <PacedChatText content={msg.text} />}
          </div>
          {/* ── Issue #429: Long-press menu */}
          {showMenu && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                left: isUser ? "auto" : 0,
                right: isUser ? 0 : "auto",
                marginTop: 4,
                background: C.surface,
                border: `1px solid ${C.border}`,
                borderRadius: 8,
                padding: 4,
                zIndex: 10,
                minWidth: 120,
              }}
              onClick={() => setShowMenu(false)}
            >
              <button
                type="button"
                onClick={handleCopy}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: "transparent",
                  border: "none",
                  color: C.text,
                  fontSize: 13,
                  cursor: "pointer",
                  textAlign: "left",
                  borderRadius: 6,
                }}
              >
                📋 Kopieren
              </button>
              <button
                type="button"
                onClick={handleFollowUp}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: "transparent",
                  border: "none",
                  color: C.sky,
                  fontSize: 13,
                  cursor: "pointer",
                  textAlign: "left",
                  borderRadius: 6,
                }}
              >
                💬 Zitieren
              </button>
            </div>
          )}
        </div>
        <span
          style={{ fontFamily: "monospace", fontSize: 9, color: C.textMuted }}
        >
          {fmtTime(msg.createdAt || now)}
        </span>
      </div>
    </div>
  );
}

// ThinkingDots (verbatim v3)
function ThinkingDots() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 16px",
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          borderRadius: 10,
          background: C.surface,
          border: `1px solid ${C.border}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 13,
          color: C.textSub,
        }}
      >
        ⬡
      </div>
      <div style={{ display: "flex", gap: 5, paddingLeft: 2 }}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: C.sky,
              display: "inline-block",
              animation: `sdc-pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

// OutcomeHints (verbatim v3)
function OutcomeHints({ hints }: { hints: ChatOutcomeHint[] }) {
  if (hints.length === 0) return null;
  return (
    <div style={{ padding: "0 12px 8px" }}>
      <div
        style={{
          borderRadius: 10,
          border: `1px solid ${C.border}`,
          background: C.surface,
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 6,
        }}
      >
        {hints.map((h) => (
          <div
            key={`${h.kind}:${h.text}`}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 6,
              fontSize: 12,
              color: C.textSub,
            }}
          >
            <span style={{ color: C.border, marginTop: 2, flexShrink: 0 }}>
              ›
            </span>
            {h.href ? (
              <a
                href={h.href}
                target="_blank"
                rel="noreferrer"
                style={{
                  color: C.sky,
                  textDecoration: "underline",
                  textUnderlineOffset: 3,
                }}
              >
                {h.text}
              </a>
            ) : (
              h.text
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// WelcomeScreen (verbatim v3)
function WelcomeScreen({ onIdea }: { onIdea: (opt: IdeaOption) => void }) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "32px 20px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          width: 72,
          height: 72,
          borderRadius: 20,
          background: `${C.accent}12`,
          border: `2px solid ${C.accent}40`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 32,
          marginBottom: 20,
        }}
      >
        🐥
      </div>
      <h2
        style={{
          fontFamily: "monospace",
          fontSize: 20,
          fontWeight: 800,
          color: C.text,
          marginBottom: 8,
          letterSpacing: -0.5,
        }}
      >
        Let&apos;s build!
      </h2>
      <p
        style={{
          fontSize: 13,
          color: C.textSub,
          lineHeight: 1.6,
          maxWidth: 300,
          marginBottom: 28,
        }}
      >
        Schreib dein Ziel oder füge eine GitHub-URL ein. Sovereign prüft Gates
        und handelt nur bei echten Stop-Punkten.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 10,
          width: "100%",
          maxWidth: 340,
        }}
      >
        {IDEA_OPTIONS.map((opt) => (
          <button
            key={opt.label}
            type="button"
            onClick={() => onIdea(opt)}
            style={{
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: 14,
              padding: "14px 12px",
              fontFamily: "monospace",
              fontSize: 11,
              color: C.text,
              fontWeight: 600,
              cursor: "pointer",
              textAlign: "left",
              transition: "border-color 0.15s, background 0.15s",
              lineHeight: 1.3,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor =
                C.borderHov;
              (e.currentTarget as HTMLButtonElement).style.background =
                "#1c2630";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor =
                C.border;
              (e.currentTarget as HTMLButtonElement).style.background =
                C.surface;
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ModuleScreen — AppControl detail view for non-chat tabs
function ModuleScreen({
  mod,
  signals,
  phases,
  conditions,
  confidence,
  sequence,
  inspectorSignals,
  onSignalClick,
}: {
  mod: ModuleCfg;
  signals: Record<string, SignalType>;
  phases: Record<string, AnimPhase>;
  conditions: Partial<Record<ModuleId, ModuleCond[]>>;
  confidence: number;
  sequence: Array<{ tabId: string; auto: boolean }>;
  inspectorSignals: RuntimeInspectorSignal[];
  onSignalClick: (prompt: string) => void;
}) {
  const sig = (signals[mod.id] ?? "idle") as SignalType;
  const phase = (phases[mod.id] ?? "idle") as AnimPhase;
  const conds = conditions[mod.id as ModuleId] ?? [];
  const phaseColor: Record<AnimPhase, string> = {
    idle: C.textMuted,
    spinup: C.sky,
    working: mod.color,
    completing: C.amber,
    done: C.green,
    error: C.rose,
  };
  const phaseSub: Record<AnimPhase, string> = {
    idle: "—",
    spinup: "initializing…",
    working: "waiting / running",
    completing: "wrapping up…",
    done: "✓ complete",
    error: "✗ failed",
  };

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: 12, padding: 14 }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 10,
            background: `${mod.color}18`,
            border: `1px solid ${mod.color}44`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 17,
            color: mod.color,
          }}
        >
          {mod.icon}
        </div>
        <div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 13,
              fontWeight: 700,
              color: C.text,
            }}
          >
            {mod.id.toUpperCase()}
          </div>
          <div
            style={{ fontFamily: "monospace", fontSize: 9, color: C.textMuted }}
          >
            {mod.id} · {sig}
          </div>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 10,
              color: phaseColor[phase],
            }}
          >
            {phase}
          </div>
          <div
            style={{ fontFamily: "monospace", fontSize: 9, color: C.textMuted }}
          >
            {phaseSub[phase]}
          </div>
        </div>
      </div>

      {/* 3-stat grid */}
      <div
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}
      >
        {[
          { label: "Signal", value: sig.toUpperCase(), color: C.textSub },
          {
            label: "Phase",
            value: phase.toUpperCase(),
            color: phaseColor[phase],
          },
          {
            label: "Diag",
            value: confidenceLabel(confidence),
            color: mod.color,
          },
        ].map(({ label, value, color }) => (
          <div
            key={label}
            style={{
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: 10,
              padding: "8px 10px",
            }}
          >
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 8,
                color: C.textMuted,
                letterSpacing: 1,
                textTransform: "uppercase",
                marginBottom: 4,
              }}
            >
              {label}
            </div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 11,
                fontWeight: 700,
                color,
              }}
            >
              {value}
            </div>
            <div
              style={{
                marginTop: 5,
                fontFamily: "monospace",
                fontSize: 8,
                color: C.textMuted,
              }}
            >
              runtime state
            </div>
          </div>
        ))}
      </div>

      {/* Conditions */}
      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 10,
          padding: "10px 12px",
        }}
      >
        <div
          style={{
            fontFamily: "monospace",
            fontSize: 8,
            color: C.textMuted,
            letterSpacing: 1,
            textTransform: "uppercase",
            marginBottom: 8,
          }}
        >
          Condition Chain
        </div>
        {conds.map((c, i) => {
          const cfg = {
            pass: { icon: "✓", color: C.green, bg: "rgba(52,211,153,0.08)" },
            fail: { icon: "✗", color: C.rose, bg: "rgba(251,113,133,0.08)" },
            wait: { icon: "⏳", color: C.amber, bg: "rgba(251,191,36,0.08)" },
          }[c.status];
          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderRadius: 8,
                background: cfg.bg,
                border: `1px solid ${cfg.color}22`,
                marginBottom: 4,
              }}
            >
              <span
                style={{
                  color: cfg.color,
                  fontSize: 11,
                  width: 14,
                  textAlign: "center",
                }}
              >
                {cfg.icon}
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 10.5,
                  color: C.textSub,
                  flex: 1,
                }}
              >
                {c.label}
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 9,
                  padding: "2px 6px",
                  borderRadius: 4,
                  color: cfg.color,
                  border: `1px solid ${cfg.color}44`,
                }}
              >
                {c.status.toUpperCase()}
              </span>
            </div>
          );
        })}
      </div>

      {/* Sequence */}
      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 10,
          padding: "10px 12px",
        }}
      >
        <div
          style={{
            fontFamily: "monospace",
            fontSize: 8,
            color: C.textMuted,
            letterSpacing: 1,
            textTransform: "uppercase",
            marginBottom: 8,
          }}
        >
          Sequence
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            overflowX: "auto",
          }}
        >
          {sequence.slice(-7).map((s, i, arr) => {
            const m = MODULES.find((x) => x.id === s.tabId);
            const col = m?.color ?? C.textMuted;
            return (
              <React.Fragment key={i}>
                <div
                  style={{
                    position: "relative",
                    flexShrink: 0,
                    padding: "3px 7px",
                    borderRadius: 4,
                    fontFamily: "monospace",
                    fontSize: 9,
                    color: col,
                    border: `1px solid ${col}44`,
                    background: `${col}10`,
                  }}
                >
                  {s.tabId.slice(0, 3).toUpperCase()}
                  {s.auto && (
                    <span
                      style={{
                        position: "absolute",
                        top: -5,
                        right: -4,
                        fontSize: 7,
                        background: col,
                        color: "#000",
                        borderRadius: 2,
                        padding: "0 2px",
                      }}
                    >
                      A
                    </span>
                  )}
                </div>
                {i < arr.length - 1 && (
                  <span style={{ color: C.border, fontSize: 10 }}>›</span>
                )}
              </React.Fragment>
            );
          })}
          {sequence.length === 0 && (
            <span
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: C.textMuted,
              }}
            >
              no events
            </span>
          )}
        </div>
      </div>

      {/* ── Issue #433: Runtime Inspector Signals */}
      {inspectorSignals.length > 0 && (
        <div
          style={{
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 10,
            padding: "10px 12px",
          }}
        >
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 8,
              color: C.textMuted,
              letterSpacing: 1,
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Inspector Signale
          </div>
          {inspectorSignals.map((signal) => (
            <button
              key={signal.id}
              type="button"
              onClick={() => onSignalClick(signal.prompt)}
              style={{
                width: "100%",
                display: "flex",
                flexDirection: "column",
                gap: 2,
                padding: "8px 10px",
                marginBottom: 6,
                background: `${mod.color}10`,
                border: `1px solid ${mod.color}33`,
                borderRadius: 8,
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 10,
                  color: mod.color,
                  fontWeight: 600,
                }}
              >
                {signal.label}
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 9,
                  color: C.textSub,
                }}
              >
                {signal.detail}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// RuntimeSheet (verbatim v3)
function RuntimeSheet({
  sources,
  current,
  onClose,
}: {
  sources: Array<{
    id: string;
    label: string;
    tier: RuntimeTier;
    description: string;
  }>;
  current: { id: string };
  onClose: () => void;
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 100,
        background: "rgba(14,17,22,0.85)",
        backdropFilter: "blur(8px)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: C.surface,
          borderRadius: "20px 20px 0 0",
          border: `1px solid ${C.border}`,
          borderBottom: "none",
          padding: "0 0 24px",
        }}
      >
        <div
          style={{
            width: 36,
            height: 4,
            borderRadius: 2,
            background: C.border,
            margin: "12px auto 16px",
          }}
        />
        <div
          style={{
            fontFamily: "monospace",
            fontSize: 9,
            textAlign: "center",
            color: C.textMuted,
            letterSpacing: 1.5,
            textTransform: "uppercase",
            marginBottom: 12,
          }}
        >
          Runtime Quelle
        </div>
        {sources.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={onClose}
            style={
              {
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "12px 20px",
                border: "none",
                borderLeft: `3px solid ${s.id === current.id ? TIER_COLOR[s.tier] : "transparent"}`,
                cursor: "pointer",
                background:
                  s.id === current.id
                    ? `${TIER_COLOR[s.tier]}08`
                    : "transparent",
              } as React.CSSProperties
            }
          >
            <span
              style={{
                width: 9,
                height: 9,
                borderRadius: "50%",
                background: TIER_COLOR[s.tier],
                boxShadow: `0 0 6px ${TIER_COLOR[s.tier]}`,
                flexShrink: 0,
              }}
            />
            <span style={{ flex: 1, textAlign: "left" }}>
              <span
                style={{
                  display: "block",
                  fontFamily: "monospace",
                  fontSize: 12,
                  color: C.text,
                }}
              >
                {s.label}
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 9,
                  color: C.textMuted,
                }}
              >
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

// SideDrawer (verbatim v3 + PAL stats block)
function SideDrawer({
  onClose,
  onGenerateIdeas,
  onGenerateErrorWorkflow,
  onPublishDraftPr,
  isPublishing,
  chatRepoSnapshot,
  onCancelOpenHands,
  openhandsIsRunning,
  palStats,
  chatHistory,
  onExportChat,
}: {
  onClose: () => void;
  onGenerateIdeas: () => void;
  onGenerateErrorWorkflow: () => void;
  onPublishDraftPr: () => void;
  isPublishing: boolean;
  chatRepoSnapshot: DevChatRepoSnapshot | null;
  onCancelOpenHands?: () => void;
  openhandsIsRunning?: boolean;
  palStats: { total: number; savings: number } | null;
  chatHistory: ChatLine[];
  onExportChat?: () => void;
}) {
  return (
    <div
      style={{ position: "absolute", inset: 0, zIndex: 90, display: "flex" }}
    >
      <div
        onClick={onClose}
        style={{
          flex: 1,
          background: "rgba(14,17,22,0.7)",
          backdropFilter: "blur(4px)",
        }}
      />
      <div
        style={{
          width: "min(80vw, 300px)",
          background: C.surface,
          borderLeft: `1px solid ${C.border}`,
          display: "flex",
          flexDirection: "column",
          boxShadow: "-8px 0 32px rgba(0,0,0,0.5)",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 16px 12px",
            borderBottom: `1px solid ${C.border}`,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: 10,
              background: `${C.accent}12`,
              border: `1px solid ${C.accent}33`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 16,
            }}
          >
            ⬡
          </div>
          <div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 11,
                fontWeight: 700,
                color: C.text,
              }}
            >
              Sovereign Studio
            </div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: C.textMuted,
              }}
            >
              NoCode Agent Runtime
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              marginLeft: "auto",
              background: "transparent",
              border: "none",
              color: C.textMuted,
              fontSize: 16,
              cursor: "pointer",
              padding: "4px",
              borderRadius: 6,
            }}
          >
            ✕
          </button>
        </div>

        {/* Repo info */}
        {chatRepoSnapshot && (
          <div
            style={{
              margin: "12px 12px 0",
              padding: "10px 12px",
              borderRadius: 10,
              background: `${C.green}08`,
              border: `1px solid ${C.green}22`,
            }}
          >
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 10,
                fontWeight: 600,
                color: C.green,
              }}
            >
              {chatRepoSnapshot.name}
            </div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: C.textSub,
                marginTop: 2,
              }}
            >
              {chatRepoSnapshot.branch} · {chatRepoSnapshot.fileCount} files
            </div>
          </div>
        )}

        {/* PAL stats */}
        {palStats && (
          <div
            style={{
              margin: "8px 12px 0",
              padding: "10px 12px",
              borderRadius: 10,
              background: C.bg,
              border: `1px solid ${C.border}`,
            }}
          >
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: C.textMuted,
                marginBottom: 4,
              }}
            >
              PAL Router
            </div>
            <div
              style={{ fontFamily: "monospace", fontSize: 10, color: C.green }}
            >
              sparsame Route aktiv
            </div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: C.textMuted,
              }}
            >
              {palStats.total} Calls · {DEV_CHAT_WORKER_MODELS.length} Modelle
              verfügbar
            </div>
          </div>
        )}

        {/* Cloudflare info (verbatim v3) */}
        <div
          style={{
            margin: "8px 12px 0",
            padding: "10px 12px",
            borderRadius: 10,
            background: C.bg,
            border: `1px solid ${C.border}`,
          }}
        >
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 9,
              color: C.textMuted,
              marginBottom: 4,
            }}
          >
            Cloudflare Workers
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 8,
              color: C.textMuted,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {SOVEREIGN_WORKER_CHAT}
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 8,
              color: C.textMuted,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {SOVEREIGN_WORKER_KV}
          </div>
        </div>

        {/* Actions */}
        <div
          style={{
            flex: 1,
            padding: "12px 12px 0",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          {/* ── Issue #432: Chat export button */}
          {onExportChat && (
            <button
              type="button"
              onClick={() => {
                onExportChat();
                onClose();
              }}
              style={{
                width: "100%",
                padding: "12px 14px",
                borderRadius: 12,
                background: `${C.sky}10`,
                border: `1px solid ${C.sky}30`,
                color: C.sky,
                fontFamily: "monospace",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                textAlign: "left",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span>📤</span> Chat teilen
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              onGenerateIdeas();
              onClose();
            }}
            data-role={SOVEREIGN_ACTION_ANALYZE_MISSION.dataRole}
            data-testid={SOVEREIGN_ACTION_ANALYZE_MISSION.testId}
            aria-label={SOVEREIGN_ACTION_ANALYZE_MISSION.ariaLabel}
            style={{
              width: "100%",
              padding: "12px 14px",
              borderRadius: 12,
              background: C.bg,
              border: `1px solid ${C.border}`,
              color: C.text,
              fontFamily: "monospace",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            🔍 Interne Prüfung
          </button>
          <button
            type="button"
            onClick={() => {
              onGenerateErrorWorkflow();
              onClose();
            }}
            style={{
              width: "100%",
              padding: "12px 14px",
              borderRadius: 12,
              background: "rgba(251,191,36,0.06)",
              border: `1px solid ${C.amber}33`,
              color: C.amber,
              fontFamily: "monospace",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            ⚠ Fehleranalyse
          </button>
          {openhandsIsRunning && onCancelOpenHands && (
            <button
              type="button"
              onClick={() => {
                onCancelOpenHands();
                onClose();
              }}
              style={{
                width: "100%",
                padding: "12px 14px",
                borderRadius: 12,
                background: "rgba(251,49,85,0.07)",
                border: "1px solid rgba(251,49,85,0.25)",
                color: C.rose,
                fontFamily: "monospace",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              ✕ Agent stoppen
            </button>
          )}
        </div>
        <div style={{ padding: "12px" }}>
          <button
            type="button"
            onClick={() => {
              onPublishDraftPr();
              onClose();
            }}
            data-role={SOVEREIGN_ACTION_DRAFT_PR.dataRole}
            data-testid={SOVEREIGN_ACTION_DRAFT_PR.testId}
            aria-label={SOVEREIGN_ACTION_DRAFT_PR.ariaLabel}
            style={{
              width: "100%",
              padding: "14px",
              borderRadius: 14,
              background: C.orange,
              border: "none",
              color: "#fff",
              fontFamily: "monospace",
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
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

// Composer (verbatim v3)
function Composer({
  value,
  onChange,
  onSubmit,
  onKeyDown,
  disabled,
  loading,
  placeholder,
  routeHint,
  slashMenu,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => boolean;
  disabled: boolean;
  loading: boolean;
  placeholder: string;
  routeHint: string;
  slashMenu?: React.ReactNode;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, []);

  return (
    <div
      style={{
        flexShrink: 0,
        padding: "10px 10px",
        paddingBottom: "max(10px, env(safe-area-inset-bottom))",
        background: C.surface,
        borderTop: `1px solid ${C.border}`,
      }}
    >
      {slashMenu ? <div style={{ marginBottom: 8 }}>{slashMenu}</div> : null}
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: 8,
          background: C.bg,
          border: `1px solid ${C.border}`,
          borderRadius: 16,
          padding: "8px 8px 8px 14px",
          transition: "border-color 0.15s",
        }}
      >
        <textarea
          ref={textareaRef}
          id={SOVEREIGN_FORM_MISSION.id}
          name={SOVEREIGN_FORM_MISSION.id}
          data-role={SOVEREIGN_FORM_MISSION.dataRole}
          data-testid={SOVEREIGN_FORM_MISSION.testId}
          aria-label={SOVEREIGN_FORM_MISSION.ariaLabel}
          value={value}
          rows={1}
          onChange={(e) => {
            onChange(e.target.value);
            resize();
          }}
          onKeyDown={(e) => {
            if (onKeyDown?.(e)) return;
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!disabled && !loading) onSubmit();
            }
          }}
          placeholder={placeholder}
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            fontFamily: "system-ui, -apple-system, sans-serif",
            fontSize: 14,
            lineHeight: 1.5,
            color: C.text,
            resize: "none",
            maxHeight: 120,
            minHeight: 24,
            overflowY: "auto",
          }}
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
            border: "none",
            color: "#fff",
            fontSize: 16,
            cursor: disabled || loading ? "not-allowed" : "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "background 0.2s, box-shadow 0.2s",
            boxShadow:
              disabled || loading ? "none" : `0 2px 12px ${C.orange}50`,
            opacity: disabled || loading ? 0.45 : 1,
          }}
        >
          {loading ? "…" : "↑"}
        </button>
      </div>
      <div
        style={{
          fontFamily: "monospace",
          fontSize: 8,
          color: C.textMuted,
          marginTop: 5,
          paddingLeft: 14,
        }}
      >
        {routeHint}
      </div>
    </div>
  );
}

// Bottom tab bar
function BottomTabBar({
  modules,
  activeTab,
  signals,
  onTabClick,
}: {
  modules: ModuleCfg[];
  activeTab: string;
  signals: Record<string, SignalType>;
  onTabClick: (id: string) => void;
}) {
  return (
    <nav
      style={{
        height: 56,
        background: C.bg,
        borderTop: `1px solid ${C.border}`,
        display: "grid",
        gridTemplateColumns: `repeat(${modules.length}, 1fr)`,
        flexShrink: 0,
      }}
      aria-label="Sovereign Studio Tabs"
    >
      {modules.map((tab) => {
        const active = tab.id === activeTab;
        const sig = (signals[tab.id] ?? "idle") as SignalType;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onTabClick(tab.id)}
            aria-current={active ? "page" : undefined}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 3,
              background: active ? `${tab.color}08` : "transparent",
              border: "none",
              borderTop: `2px solid ${active ? tab.color : "transparent"}`,
              cursor: "pointer",
              padding: "4px 2px",
              minWidth: 0,
            }}
          >
            <span
              style={{
                position: "relative",
                fontSize: 15,
                color: active ? tab.color : C.textMuted,
                transition: "color 0.15s",
              }}
            >
              {tab.icon}
              {sig !== "idle" && tab.id !== "chat" && (
                <span
                  style={{
                    position: "absolute",
                    top: -2,
                    right: -4,
                    display: "inline-block",
                    width: 5,
                    height: 5,
                    borderRadius: "50%",
                    background:
                      sig === "error"
                        ? C.rose
                        : sig === "warning"
                          ? C.amber
                          : tab.color,
                    animation:
                      sig === "processing"
                        ? "sdc-pulse 1s ease-in-out infinite"
                        : "none",
                  }}
                />
              )}
            </span>
            <span
              style={{
                fontFamily: "monospace",
                fontSize: 7.5,
                color: active ? tab.color : C.textMuted,
                transition: "color 0.15s",
                letterSpacing: 0.3,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: "100%",
              }}
            >
              {tab.short}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

// ─────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────

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
  openhandsConfig,
  openhandsJob,
  openhandsJobStatus,
  openhandsIsRunning,
  onStartOpenHands,
  onCancelOpenHands,
}: BuilderContainerProps) {
  // ── Original v3 state (verbatim)
  const [patternMemoryStore, setPatternMemoryStore] = useState<PatternMemoryStore>(() => createPatternMemoryStore());
  const [wishText, setWishText] = useState(() => missionToWishText(mission));
  const [thinkingFrameIndex, setTFI] = useState(0);
  const [showRuntimeSheet, setShowRuntime] = useState(false);
  const [showSideMenu, setShowSide] = useState(false);
  const [showRepoExplorer, setShowRepoExplorer] = useState(false);
  const [showOpenHandsBriefing, setOHB] = useState(false);
  const [chatRepoSnapshot, setChatRepo] = useState<DevChatRepoSnapshot | null>(
    null,
  );
  const [chatRepoError, setChatRepoError] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatLine[]>([]);
  const [chatResponseBusy, setChatResponseBusy] = useState(false);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [workerBlocker, setWorkerBlocker] =
    useState<WorkerRuntimeBlocker | null>(null);
  const [localRepoLoading, setRepoLoading] = useState(false);
  const lastMissionRef = useRef(mission);
  const ignoreNextMissionSyncRef = useRef(false);
  const chatLineIndexRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const nowRef = useRef(Date.now());

  // ── AppControl state (additions)
  const [activeTab, setActiveTab] = useState<string>("chat");
  const [sequence, setSequence] = useState<
    Array<{ tabId: string; auto: boolean }>
  >([]);
  const [signals, setSignals] = useState<Record<string, SignalType>>(
    Object.fromEntries(MODULES.map((m) => [m.id, "idle" as SignalType])),
  );
  const [phases, setPhases] = useState<Record<string, AnimPhase>>(
    Object.fromEntries(MODULES.map((m) => [m.id, "idle" as AnimPhase])),
  );
  const [conditions, setConditions] =
    useState<Partial<Record<ModuleId, ModuleCond[]>>>(INIT_CONDITIONS);
  const [confidence, setConfidence] = useState(0.12);
  const [panelOpen, setPanelOpen] = useState(false);
  const [palDecisions, setPalDecisions] = useState<PALDecision[]>([]);
  const [statusLogs, setStatusLogs] = useState<
    Array<{ ts: string; level: string; msg: string; tabId: string }>
  >([]);

  // ── Issue #425: Auto-scroll lock and jump badge
  const [userScrolledAway, setUserScrolledAway] = useState(false);
  const [unseenCount, setUnseenCount] = useState(0);

  // ── Issue #443: GitHub Access State
  const [githubAccessState, setGitHubAccessState] = useState<GitHubAccessSnapshot>(
    createGitHubAccessSnapshot(),
  );
  const githubWriteAllowed = canPerformGitHubWrite(githubAccessState);

  // ── Issue #445: AgentWorkTimeline state
  const [agentWorkSnapshot, setAgentWorkSnapshot] = useState<AgentWorkSnapshot>(
    () => createIdleSnapshot(`sovereign-${Date.now()}`),
  );

  // ── Issue #445: Sync AgentWorkSnapshot from openhandsJob transitions
  useEffect(() => {
    if (!openhandsJob) return;
    const repo = chatRepoSnapshot
      ? `${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo}`
      : null;
    setAgentWorkSnapshot((prev) => {
      let snap = prev;
      if (openhandsJob.status === 'queued' || openhandsJob.status === 'running') {
        if (snap.state === 'idle') {
          snap = transitionIntentDetected(
            snap,
            repo ?? 'unknown/repo',
            chatRepoSnapshot?.branch ?? 'main',
          );
        }
        if (snap.state === 'intent_detected') {
          snap = transitionExecutorStarting(snap, 'openhands');
        }
        if (snap.state === 'executor_starting' && openhandsJob.jobId) {
          snap = transitionExecutorRunning(snap, openhandsJob.jobId);
        }
      }
      if (openhandsJob.draftPrUrl && snap.state !== 'draft_pr_ready') {
        snap = transitionDraftPrReady(snap, openhandsJob.draftPrUrl);
      }
      if (openhandsJob.status === 'failed' && snap.state !== 'failed' && snap.state !== 'draft_pr_ready') {
        snap = transitionFailed(snap, 'OpenHands Executor fehlgeschlagen.');
      }
      if (openhandsJob.status === 'blocked' && snap.state !== 'blocked' && snap.state !== 'draft_pr_ready') {
        snap = transitionBlocked(snap, 'OpenHands Executor blockiert.');
      }
      if (openhandsJob.status === 'idle' && snap.state !== 'idle' && snap.state !== 'draft_pr_ready') {
        snap = createIdleSnapshot(`sovereign-${Date.now()}`);
      }
      return snap;
    });
  }, [openhandsJob, chatRepoSnapshot]);

  // ── Slash command menu state (Issue #428)
  const [selectedSlashIndex, setSelectedSlashIndex] = useState(0);
  const [slashMenuDismissed, setSlashMenuDismissed] = useState(false);
  const slashMatches = useMemo(
    () => matchingSlashCommands(wishText),
    [wishText],
  );
  const showSlashCommands =
    shouldShowSlashMenu(wishText) &&
    slashMatches.length > 0 &&
    !slashMenuDismissed;

  // ── Issue #429: Haptic feedback helper using runtime
  const triggerHaptic = useCallback(
    (type: "light" | "medium" | "heavy" = "light") => {
      triggerAndroidHaptic(typeof navigator === "undefined" ? undefined : navigator, type);
    },
    [],
  );

  const addLog = useCallback((level: string, msg: string, tabId = "sys") => {
    const ts = new Date().toLocaleTimeString("de-DE", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setStatusLogs((prev) => [...prev.slice(-199), { ts, level, msg, tabId }]);
  }, []);

  const openRepoExplorer = useCallback(() => {
    if (!chatRepoSnapshot) return;
    setShowRepoExplorer(true);
  }, [chatRepoSnapshot]);

  const openRepoExplorerFromFileBadge = useCallback(() => {
    setShowRepoExplorer(true);
  }, []);

  const handleRepoExplorerFileClick = useCallback(
    (path: string) => {
      const cleanPath = path.trim();
      if (!cleanPath) return;
      setWishText(createRepoFilePrompt(cleanPath));
      setShowRepoExplorer(false);
      addLog("info", `Repo file prompt prepared: ${cleanPath}`, "router");
    },
    [addLog],
  );

  const appendChatLine = useCallback(
    (
      line: Omit<ChatLine, "id" | "createdAt"> & {
        readonly id?: string;
        readonly createdAt?: number;
      },
    ) => {
      chatLineIndexRef.current += 1;
      const createdAt = line.createdAt ?? Date.now();
      setChatHistory((previous) => [
        ...previous,
        {
          ...line,
          id: line.id ?? createChatLineId(line.role, chatLineIndexRef.current),
          createdAt,
        },
      ]);
      nowRef.current = createdAt;
    },
    [],
  );

  // ── Issue #447: Auto-save workflow patterns after Draft PR success
  usePatternMemoryStore({
    agentWorkSnapshot,
    patternMemoryStore,
    setPatternMemoryStore,
    mission,
    repoOwner: chatRepoSnapshot?.owner ?? '',
    repoName: chatRepoSnapshot?.repo ?? '',
    appendChatLine,
  });

  // ── Issue #425: Track unseen messages
  const lastChatHistoryLengthRef = useRef(chatHistory.length);
  useEffect(() => {
    if (chatHistory.length > lastChatHistoryLengthRef.current) {
      if (userScrolledAway) {
        setUnseenCount(
          (prev) =>
            prev + (chatHistory.length - lastChatHistoryLengthRef.current),
        );
      }
    }
    lastChatHistoryLengthRef.current = chatHistory.length;
  }, [chatHistory.length, userScrolledAway]);

  useEffect(() => {
    setSlashMenuDismissed(false);
    setSelectedSlashIndex((current) => {
      if (slashMatches.length === 0) return 0;
      return Math.min(current, slashMatches.length - 1);
    });
  }, [slashMatches.length, wishText]);

  const emitMissionChange = useCallback(
    (nextMission: string) => {
      lastMissionRef.current = nextMission;
      ignoreNextMissionSyncRef.current = true;
      onMissionChange(nextMission);
    },
    [onMissionChange],
  );

  const switchTab = useCallback(
    (id: string, auto = false) => {
      setActiveTab(id);
      setSequence((prev) => [...prev.slice(-11), { tabId: id, auto }]);
      addLog("info", `Tab → ${id} (${auto ? "auto" : "manual"})`, id);
    },
    [addLog],
  );

  // ── Original v3 derived values (verbatim)
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
  const workerBlocked = Boolean(workerBlocker);
  const runtimeThinkingActive = Boolean(
    chatResponseBusy ||
    openhandsIsRunning ||
    repoBusy ||
    localRepoLoading ||
    runtimeBusy ||
    isPublishing,
  );
  const workStateStatus = runtimeThinkingActive
    ? chatResponseBusy
      ? "Cloudflare Worker antwortet"
      : openhandsJobStatus?.trim() || "Runtime arbeitet"
    : workerBlocker
      ? `blocked · ${workerBlocker.diagnostic.status ? `Worker HTTP ${workerBlocker.diagnostic.status}` : "Worker blockiert"}`
      : effectiveRepoReady
        ? "idle · Repo-Kontext bereit"
        : "idle · Repo fehlt";
  const cuteThinkingLabel = useMemo(
    () =>
      formatCuteWorkStateLabel({
        index: thinkingFrameIndex,
        active: runtimeThinkingActive,
        status: workStateStatus,
      }),
    [runtimeThinkingActive, thinkingFrameIndex, workStateStatus],
  );
  const outcomeHints = useMemo(
    () => buildOutcomeHints(openhandsJob),
    [openhandsJob],
  );
  const agentDisabled =
    !effectiveRepoReady ||
    repoBusy ||
    localRepoLoading ||
    runtimeBusy ||
    Boolean(openhandsIsRunning) ||
    !openhandsReady ||
    !onStartOpenHands;
  const agentStatus = workerBlocker
    ? "error"
    : chatResponseBusy
      ? "thinking"
      : deriveAgentStatus({
          repoBusy,
          runtimeBusy,
          isPublishing,
          openhandsIsRunning,
          openhandsJob,
          localRepoLoading,
          localRepoError: Boolean(chatRepoError),
        });
  const workerSourceTier: RuntimeTier = workerBlocker
    ? "blocked"
    : chatResponseBusy
      ? "active"
      : "ready";
  const runtimeSource = {
    id: "worker-chat",
    label: workerBlocker ? "Cloudflare Worker blockiert" : "Cloudflare Worker",
    tier: workerSourceTier,
    description: workerBlocker ? workerBlocker.message : SOVEREIGN_WORKER_CHAT,
    available: !workerBlocker,
  };
  const runtimeSources = [
    runtimeSource,
    {
      id: "worker-kv",
      label: "Worker KV",
      tier: "ready" as RuntimeTier,
      description: SOVEREIGN_WORKER_KV,
      available: true,
    },
    {
      id: "worker-models",
      label: `${DEV_CHAT_WORKER_MODELS.length} Modelle`,
      tier: "ready" as RuntimeTier,
      description: DEV_CHAT_WORKER_MODELS.map((m) => m.label).join(" · "),
      available: true,
    },
    {
      id: "openhands-runtime",
      label: openhandsReady ? "OpenHands Executor" : "OpenHands offline",
      tier: (openhandsReady
        ? openhandsIsRunning
          ? "active"
          : "ready"
        : "blocked") as RuntimeTier,
      description: openhandsReady
        ? "Echte Agent-Runtime für Code/Draft-PR-Aufträge"
        : "Agent-Runtime nicht verbunden",
      available: Boolean(openhandsReady),
    },
    {
      id: "repo-snapshot",
      label: effectiveRepoReady ? "Repo Snapshot" : "Repo fehlt",
      tier: (effectiveRepoReady ? "ready" : "blocked") as RuntimeTier,
      description: effectiveRepoReady ? effectiveRepoReason : repoReason,
      available: effectiveRepoReady,
    },
  ];
  const chatLines = useMemo(
    () =>
      buildChatLines({
        repoReady: effectiveRepoReady,
        repoReason: effectiveRepoReason,
        runtimeThinkingActive,
        cuteThinkingLabel,
        sovereignSummary,
        disabledReason: state.disabledReason,
        openhandsJob,
        chatRepoSnapshot,
        chatRepoError,
        chatHistory,
      }),
    [
      chatHistory,
      chatRepoError,
      chatRepoSnapshot,
      cuteThinkingLabel,
      effectiveRepoReady,
      effectiveRepoReason,
      openhandsJob,
      runtimeThinkingActive,
      sovereignSummary,
      state.disabledReason,
    ],
  );

  // PAL stats
  const palStats = useMemo(() => {
    const t = palDecisions.length;
    if (!t) return null;
    const cost = palDecisions.reduce((s, d) => s + d.costFactor, 0);
    return {
      total: t,
      savings: Math.round(((t * 30 - cost) / (t * 30)) * 100),
    };
  }, [palDecisions]);
  const lastPal = palDecisions[palDecisions.length - 1] ?? null;

  // ── Original v3 effects (verbatim)
  useEffect(() => {
    const h = window.setInterval(
      () => setTFI((c) => c + 1),
      runtimeThinkingActive ? CUTE_THINKING_FRAME_MS : CUTE_IDLE_FRAME_MS,
    );
    return () => window.clearInterval(h);
  }, [runtimeThinkingActive]);

  useEffect(() => {
    if (mission === lastMissionRef.current) return;
    lastMissionRef.current = mission;
    if (ignoreNextMissionSyncRef.current) {
      ignoreNextMissionSyncRef.current = false;
      return;
    }
    if (wishText.trim() || chatHistory.length > 0) return;
    setWishText(missionToWishText(mission));
  }, [chatHistory.length, mission, wishText]);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [chatLines.length, outcomeHints.length, runtimeThinkingActive]);

  useEffect(() => {
    nowRef.current = Date.now();
  }, [chatLines.length]);

  // ── AppControl runtime binding
  // No simulated progress: lamps, phases and conditions are derived from real runtime state.
  useEffect(() => {
    const jobBlocked =
      openhandsJob?.status === "blocked" ||
      openhandsJob?.status === "failed" ||
      Boolean(chatRepoError) ||
      Boolean(workerBlocker);
    const hasOutput =
      (openhandsJob?.changedFiles?.length ?? 0) > 0 ||
      Boolean(openhandsJob?.draftPrUrl);
    const budState = deriveBudStateFromPalDecisions(palDecisions);
    const budBlocked = budState.selectionResult?.status === "blocked";
    const nextSignals: Record<string, SignalType> = {
      chat: workerBlocker
        ? "error"
        : runtimeThinkingActive
          ? "processing"
          : wishText.trim() || chatHistory.length > 0
            ? "active"
            : "idle",
      init: effectiveRepoReady ? "active" : "warning",
      router: workerBlocker
        ? "error"
        : localRepoLoading || repoBusy
          ? "processing"
          : effectiveRepoReady
            ? "active"
            : "idle",
      pattern: palDecisions.length > 0 ? "active" : "idle",
      sync: workerBlocker
        ? "error"
        : openhandsIsRunning
          ? "processing"
          : openhandsReady
            ? "active"
            : "warning",
      orchestr: jobBlocked
        ? "error"
        : isPublishing || openhandsIsRunning
          ? "processing"
          : hasOutput
            ? "active"
            : "idle",
      logger:
        statusLogs.length > 0 || outcomeHints.length > 0 ? "active" : "idle",
      budget: budBlocked
        ? "error"
        : palDecisions.length > 0
          ? "active"
          : "idle",
    };

    setSignals((previous) =>
      sameRecord(previous, nextSignals) ? previous : nextSignals,
    );
    const nextConditions: Partial<Record<ModuleId, ModuleCond[]>> = {
      init: [
        { label: "Module loaded", status: "pass" },
        { label: "Config valid", status: openhandsConfig ? "pass" : "wait" },
      ],
      router: [
        {
          label: "Repo context available",
          status: effectiveRepoReady ? "pass" : "wait",
        },
        {
          label: "No runtime blocker",
          status: state.disabledReason || workerBlocker ? "fail" : "pass",
        },
        {
          label: "Chat intent present",
          status: wishText.trim() || chatHistory.length > 0 ? "pass" : "wait",
        },
      ],
      pattern: [
        {
          label: "PAL decision available",
          status: palDecisions.length > 0 ? "pass" : "wait",
        },
        {
          label: "Confidence stable",
          status: confidence >= 0.5 ? "pass" : "wait",
        },
        { label: "No fake progress", status: "pass" },
        { label: "No hard percent display", status: "pass" },
      ],
      sync: [
        {
          label: "Worker route clear",
          status: workerBlocker ? "fail" : "pass",
        },
        {
          label: "OpenHands configured",
          status: openhandsReady ? "pass" : "wait",
        },
        {
          label: "Runtime active only on real job",
          status: openhandsIsRunning ? "pass" : "wait",
        },
        {
          label: "Repo snapshot synced",
          status: chatRepoSnapshot || repoReady ? "pass" : "wait",
        },
      ],
      orchestr: [
        { label: "Repo gate", status: effectiveRepoReady ? "pass" : "wait" },
        { label: "Agent gate", status: !agentDisabled ? "pass" : "wait" },
        { label: "Stopper clear", status: jobBlocked ? "fail" : "pass" },
        {
          label: "Worker blocker clear",
          status: workerBlocker ? "fail" : "pass",
        },
      ],
      logger: [
        { label: "Logger active", status: "pass" },
        {
          label: "Runtime events recorded",
          status: statusLogs.length > 0 ? "pass" : "wait",
        },
      ],
      budget: [
        {
          label: "Route active",
          status: palDecisions.length > 0 ? "pass" : "wait",
        },
        {
          label: "Budget available",
          status: budBlocked ? "fail" : "pass",
        },
        { label: "Ledger synced", status: "pass" },
      ],
    };

    setConditions((previous) =>
      sameConditions(previous, nextConditions) ? previous : nextConditions,
    );
    setPhases((previous) => {
      const next = Object.fromEntries(
        MODULES.map((module) => [
          module.id,
          phaseFromSignalAndConditions(
            nextSignals[module.id] ?? "idle",
            nextConditions[module.id] ?? [],
          ),
        ]),
      ) as Record<string, AnimPhase>;
      return sameRecord(previous, next) ? previous : next;
    });
    setConfidence(
      buildRuntimeConfidence({
        effectiveRepoReady,
        openhandsReady,
        runtimeThinkingActive,
        blocked: jobBlocked || Boolean(state.disabledReason),
        palDecisions: palDecisions.length,
        outcomeHints: outcomeHints.length,
      }),
    );

    const previousSignals = signals;
    for (const module of MODULES) {
      const previous = previousSignals[module.id] ?? "idle";
      const next = nextSignals[module.id] ?? "idle";
      if (previous !== next)
        addLog("signal", `Signal[${module.id}] → ${next}`, module.id);
    }
  }, [
    addLog,
    agentDisabled,
    chatHistory.length,
    chatRepoError,
    chatRepoSnapshot,
    confidence,
    effectiveRepoReady,
    isPublishing,
    localRepoLoading,
    openhandsConfig,
    openhandsIsRunning,
    openhandsJob?.changedFiles?.length,
    openhandsJob?.draftPrUrl,
    openhandsJob?.status,
    openhandsReady,
    outcomeHints.length,
    palDecisions.length,
    repoBusy,
    repoReady,
    runtimeThinkingActive,
    signals,
    state.disabledReason,
    statusLogs.length,
    wishText,
    workerBlocker,
  ]);

  // ── Chat runtime actions: composer draft, chat history, worker route and executor gate are separated.
  const startAgentFromText = (text: string) => {
    const clean = collapseRepeatedAnalyzedMission(
      buildAnalyzedMission({
        wish: text,
        repoReady: effectiveRepoReady,
        repoReason: effectiveRepoReason,
      }),
    );
    emitMissionChange(clean);
    onStartOpenHands?.(clean);
  };

  const handleSubmit = async () => {
    const submittedText = wishText.trim();
    if (!submittedText || localRepoLoading || chatResponseBusy || isPublishing)
      return;
    setWishText("");
    _processSubmit(submittedText);
  };

  // Retry submit with a specific message (used by WorkerBlockerCard and Banner)
  const retrySubmit = async (message: string) => {
    if (localRepoLoading || chatResponseBusy || isPublishing) return;
    setWishText("");
    _processSubmit(message);
  };

  const _processSubmit = async (submittedText: string) => {
    // ── Issue #445: SecureInputGuard — block secrets before any storage or LLM path
    const securePolicy = evaluateInputPolicy(submittedText);
    if (securePolicy.shouldBlock) {
      appendChatLine({
        role: "assistant",
        text: securePolicy.userMessage,
      });
      addLog("warn", `SecureInputGuard: ${securePolicy.kind ?? "secret"} detected and blocked`, "router");
      return;
    }

    // ── Issue #428: Slash command handling
    if (submittedText.startsWith("/")) {
      const parsedSlash = parseSlashCommand(submittedText);
      if (!parsedSlash) {
        appendChatLine({
          role: "assistant",
          text: `Unbekannter Befehl. Verfügbare: ${SOVEREIGN_SLASH_COMMANDS.map((c) => c.cmd).join(", ")}`,
        });
        return;
      }

      const { command, argument } = parsedSlash;
      if (command.action === "analyze") {
        triggerHaptic("medium");
        onGenerateIdeas();
        return;
      }
      if (command.action === "fix") {
        triggerHaptic("medium");
        onGenerateErrorWorkflow();
        return;
      }
      if (command.action === "pr") {
        triggerHaptic("medium");
        onPublishDraftPr();
        return;
      }
      if (command.action === "repo") {
        if (!argument) {
          appendChatLine({
            role: "assistant",
            text: "Verwendung: /repo <GitHub-URL>",
          });
          return;
        }
        await _processSubmit(argument);
        return;
      }
      if (command.action === "clear") {
        // Clear chat lines but NOT repo, token, remote memory
        setChatHistory([]);
        setPalDecisions([]);
        triggerHaptic("light");
        appendChatLine({
          role: "assistant",
          text: "Chat-Verlauf gelöscht. Repository und Token bleiben erhalten.",
        });
        return;
      }
    }

    // Haptic feedback for send (Issue #429)
    triggerHaptic("light");

    appendChatLine({ role: "user", text: submittedText });

    const parsedRepo = parseDevChatGithubUrl(submittedText);
    if (parsedRepo) {
      setRepoLoading(true);
      setChatRepoError(null);
      triggerHaptic("medium");
      const result = await fetchDevChatRepoTree(parsedRepo);
      setRepoLoading(false);
      if (result.ok && result.snapshot) {
        setChatRepo(result.snapshot);
        triggerHaptic("medium");
        const summary = summarizeDevChatRepoSnapshot(result.snapshot);
        appendChatLine({
          role: "assistant",
          text: `Repo geladen. ${summary}\nTop-Level: ${result.snapshot.dirs.join(" · ") || "keine Top-Level-Ordner erkannt"}\nDer Repo-Snapshot bleibt Runtime-Kontext und wird nicht in die Eingabezeile geschrieben.`,
          file: result.snapshot.lastFile,
          path: result.snapshot.lastPath,
        });
        const d = palRoute(
          `Repo geladen: ${result.snapshot.name}`,
          0,
          result.snapshot.fileCount,
          palDecisions,
        );
        setPalDecisions((prev) => [...prev.slice(-99), d]);
        addLog("info", `PAL → ${d.tier} · ${d.modelLabel}`, "sys");
        return;
      }
      const errorText = result.error ?? "Repo konnte nicht geladen werden.";
      setChatRepoError(errorText);
      triggerHaptic("heavy");
      appendChatLine({
        role: "assistant",
        text: `Repo-Laden blockiert: ${errorText}`,
      });
      return;
    }

    const workerDiagnosticIntent = isWorkerDiagnosticQuestion(submittedText);
    if (
      workerBlocker &&
      !isWorkerRetryIntent(submittedText) &&
      !isOpenHandsExecutionIntent(submittedText)
    ) {
      appendChatLine({
        role: "assistant",
        text: buildWorkerBlockerAnswer({
          blocker: workerBlocker,
          repoReady: effectiveRepoReady,
          chatRepoSnapshot,
          openhandsReady,
        }),
      });
      addLog(
        "warn",
        `Worker blocked · ${workerBlocker.diagnostic.scope}${workerDiagnosticIntent ? " · local explanation" : " · retry prevented"}`,
        "router",
      );
      return;
    }

    if (workerBlocker && isWorkerRetryIntent(submittedText)) {
      setWorkerBlocker(null);
      addLog("info", "Worker retry requested by user", "router");
    }

    const d = palRoute(
      submittedText,
      chatHistory.length + 1,
      chatRepoSnapshot?.fileCount ?? 0,
      palDecisions,
    );
    setPalDecisions((prev) => [...prev.slice(-99), d]);
    addLog("info", `PAL → ${d.tier} · ${d.modelLabel}`, "sys");

    if (isOpenHandsExecutionIntent(submittedText)) {
      if (!agentDisabled) {
        appendChatLine({
          role: "assistant",
          text: "Code-/Draft-PR-Auftrag erkannt. Ich übergebe an OpenHands Executor und halte den Worker Chat als Standardroute bereit.",
        });
        startAgentFromText(submittedText);
        return;
      }
      appendChatLine({
        role: "assistant",
        text: `OpenHands Executor blockiert: ${state.disabledReason || effectiveRepoReason}. Ich beantworte den Auftrag deshalb zuerst über den Cloudflare Worker.`,
      });
    }

    setChatResponseBusy(true);
    setStreamingText("");

    const workerMessages = buildWorkerMessages({
      submittedText,
      chatHistory,
      repoReady: effectiveRepoReady,
      repoReason: effectiveRepoReason,
      chatRepoSnapshot,
    });

    // Stream chunks directly into UI for immediate feedback
    let fullText = "";
    let streamError: {
      status?: number;
      statusText?: string;
      bodySnippet?: string;
    } | null = null;
    let streamDiagnostic: DevChatWorkerDiagnostic | null = null;
    try {
      for await (const chunk of streamDevChatWorkerReply({
        model: d.modelId,
        messages: workerMessages,
      })) {
        fullText += chunk;
        setStreamingText(fullText);
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    } catch (err) {
      const diagnostic = (err as { diagnostic?: DevChatWorkerDiagnostic })
        ?.diagnostic;
      streamDiagnostic = diagnostic ?? null;
      streamError = {
        status: diagnostic?.status ?? (err as { status?: number })?.status,
        statusText:
          diagnostic?.statusText ??
          (err as { statusText?: string })?.statusText,
        bodySnippet: diagnostic?.bodySnippet ?? (err as Error)?.message,
      };
    }

    setChatResponseBusy(false);
    setStreamingText(null);

    if (fullText) {
      setWorkerBlocker(null);
      // ── Issue #445: chatClaimGuard — verify response against runtime snapshot before display
      const claimCheck = checkChatClaim(fullText, agentWorkSnapshot);
      const textToAppend =
        claimCheck.allowed || !claimCheck.honestFallback
          ? fullText
          : `${fullText}\n\n_[Sovereign: ${claimCheck.honestFallback}]_`;
      if (!claimCheck.allowed && claimCheck.violations.length > 0) {
        addLog("warn", `chatClaimGuard: ${claimCheck.violations.join(", ")}`, "router");
      }
      appendChatLine({ role: "assistant", text: textToAppend });
      return;
    }

    const fallback = streamDiagnostic
      ? null
      : await fetchDevChatWorkerReply({
          model: d.modelId,
          messages: workerMessages,
        });

    if (fallback?.ok && fallback.content) {
      setWorkerBlocker(null);
      appendChatLine({ role: "assistant", text: fallback.content });
      return;
    }

    const health = await fetchDevChatWorkerHealth();
    const diagnostic = streamDiagnostic ??
      fallback?.diagnostic ?? {
        route: SOVEREIGN_WORKER_CHAT,
        model: d.modelId,
        messageCount: workerMessages.length,
        scope: streamError?.status ? "worker_runtime" : "network",
        canClientFix: false,
        nextAction: streamError?.status
          ? "Worker-Diagnose prüfen; kaputten Call nicht blind wiederholen."
          : "Netzwerk, CORS oder Worker-Erreichbarkeit prüfen.",
        status: streamError?.status,
        statusText: streamError?.statusText,
        bodySnippet: streamError?.bodySnippet,
      };
    const blocker: WorkerRuntimeBlocker = {
      message: "Stream fehlgeschlagen oder leer.",
      diagnostic,
      health,
      createdAt: Date.now(),
    };
    setWorkerBlocker(blocker);
    appendChatLine({
      role: "assistant",
      text: buildWorkerBlockerAnswer({
        blocker,
        repoReady: effectiveRepoReady,
        chatRepoSnapshot,
        openhandsReady,
      }),
    });
    addLog(
      "error",
      `Worker blocked · ${diagnostic.scope}${diagnostic.status ? ` · HTTP ${diagnostic.status}` : ""}`,
      "router",
    );
  };

  const selectedSlashCommand =
    slashMatches[selectedSlashIndex] ?? slashMatches[0];
  const submitSelectedSlashCommand = (command: SlashCommandDefinition) => {
    const clean = wishText.trimStart();
    const argument = clean.startsWith(command.cmd)
      ? clean.slice(command.cmd.length).trim()
      : "";
    const submitted = argument ? `${command.cmd} ${argument}` : command.cmd;
    setWishText("");
    setSlashMenuDismissed(false);
    void _processSubmit(submitted);
  };

  const handleComposerKeyDown = (
    event: React.KeyboardEvent<HTMLTextAreaElement>,
  ): boolean => {
    if (!showSlashCommands) return false;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedSlashIndex((index) => (index + 1) % slashMatches.length);
      return true;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedSlashIndex(
        (index) => (index - 1 + slashMatches.length) % slashMatches.length,
      );
      return true;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setSlashMenuDismissed(true);
      return true;
    }
    if (event.key === "Enter" && !event.shiftKey && selectedSlashCommand) {
      event.preventDefault();
      submitSelectedSlashCommand(selectedSlashCommand);
      return true;
    }
    return false;
  };

  const submitDisabled =
    localRepoLoading || chatResponseBusy || isPublishing || !wishText.trim();
  const isChat = activeTab === "chat";
  const activeMod = MODULES.find((m) => m.id === activeTab) ?? MODULES[0];

  // ─────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────
  return (
    <section
      className={builderContainerContract.rootClass}
      data-role={builderContainerContract.dataRole}
      data-testid={builderContainerContract.testId}
      data-layout="devchat-appcontrol-integrated"
      aria-label={builderContainerContract.ariaLabel}
      style={{
        width: "100%",
        maxWidth: MAX_W,
        margin: "0 auto",
        height: "100dvh",
        display: "flex",
        flexDirection: "column",
        background: C.bg,
        color: C.text,
        fontFamily: "system-ui, -apple-system, sans-serif",
        overflow: "hidden",
        position: "relative",
        WebkitTapHighlightColor: "transparent",
      }}
    >
      <style>{`
        @keyframes sdc-pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.3;transform:scale(.8)} }
        @keyframes sdc-typing-caret { 0%,45%{opacity:1} 46%,100%{opacity:.18} }
        textarea::placeholder { color: #3d4f61; }
        ::-webkit-scrollbar { width: 3px; height: 3px; }
        ::-webkit-scrollbar-thumb { background: #232d3a; border-radius: 2px; }
        ::-webkit-scrollbar-track { background: transparent; }
      `}</style>

      {/* TOP BAR — v3 design + module lamps + PAL badge */}
      <TopBar
        status={agentStatus}
        repoReady={effectiveRepoReady}
        chatRepoSnapshot={chatRepoSnapshot}
        repoReason={effectiveRepoReason}
        onMenuOpen={() => setShowSide(true)}
        onRepoClick={openRepoExplorer}
        onSourceClick={() => setShowRuntime(true)}
        source={runtimeSource}
        modules={MODULES}
        signals={signals}
        activeTab={activeTab}
        onTabClick={switchTab}
        panelOpen={panelOpen}
        onPanelToggle={() => setPanelOpen((v) => !v)}
        palTier={lastPal?.tier ?? null}
        palSavings={palStats?.savings ?? null}
      />

      {/* COLLAPSIBLE STATUS/LOG PANEL */}
      <StatusPanel
        open={panelOpen}
        logs={statusLogs}
        signals={signals}
        modules={MODULES}
        onClearLogs={() => setStatusLogs([])}
      />

      {/* ── Issue #426: Worker Degraded Banner */}
      {workerBlocker && (
        <WorkerDegradedBanner
          blocker={workerBlocker}
          userMessage={
            chatHistory.length > 0
              ? chatHistory[chatHistory.length - 1].text
              : undefined
          }
          onRetryWithMessage={(msg) => {
            setWorkerBlocker(null);
            addLog("info", "Worker retry from banner", "router");
            retrySubmit(msg);
          }}
        />
      )}

      {/* MAIN CONTENT */}
      {isChat ? (
        /* ── CHAT VIEW with auto-scroll lock (Issue #425) */
        <div
          ref={scrollRef}
          data-testid="sovereign-chat-body-window"
          aria-label="Sovereign Chat Verlauf"
          onScroll={(e) => {
            const el = e.currentTarget;
            const isNearBottom =
              el.scrollHeight - el.scrollTop - el.clientHeight < 48;
            setUserScrolledAway(!isNearBottom);
          }}
          style={{
            flex: 1,
            overflowY: "auto",
            overflowX: "hidden",
            background: C.bg,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {!wishText.trim() && !chatRepoSnapshot && chatHistory.length === 0 ? (
            <WelcomeScreen
              onIdea={(opt) => setWishText((c) => appendOption(c, opt))}
            />
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 10,
                padding: "16px 0 8px",
              }}
            >
              {chatLines.map((line) => (
                <Bubble
                  key={line.id}
                  msg={line}
                  now={nowRef.current}
                  onLongPress={(draft) => setWishText(draft)}
                  onOpenFile={openRepoExplorerFromFileBadge}
                />
              ))}
              {streamingText !== null && (
                <Bubble
                  msg={{
                    id: "stream",
                    role: "assistant",
                    text: streamingText,
                    createdAt: Date.now(),
                  }}
                  now={nowRef.current}
                />
              )}
              {agentStatus === "thinking" && streamingText === null && (
                <ThinkingDots />
              )}
              <OutcomeHints hints={outcomeHints} />

              {/* ── Issue #445: AgentWorkTimeline — live task progress in chat feed */}
              {agentWorkSnapshot.state !== 'idle' && (
                <AgentWorkTimeline snapshot={agentWorkSnapshot} />
              )}

              {/* ── Issue #443: OpenHands Job Truth Card */}
              {openhandsJob && openhandsJob.status !== 'idle' && (
                <OpenHandsJobTruthCard
                  job={openhandsJob}
                  onStart={onStartOpenHands ? () => onStartOpenHands(wishText) : undefined}
                  onPreview={() => appendChatLine({ role: 'assistant', text: 'Vorschau wird geladen…' })}
                  onCancel={onCancelOpenHands}
                  onOpenDraftPr={openhandsJob.draftPrUrl ? () => window.open(openhandsJob.draftPrUrl, '_blank') : undefined}
                />
              )}

              {/* ── Issue #443: GitHub Access Card (shown when write access needed but not available) */}
              {!githubWriteAllowed && (openhandsJob?.status === 'running' || isPublishing) && (
                <GitHubAccessCard
                  snapshot={githubAccessState}
                  onProvideToken={(token) => {
                    // SECURITY: Real GitHub API validation required before ready state.
                    // For now, accept format-valid tokens but require explicit re-validation
                    // on actual GitHub write operations (Draft PR, Push).
                    // Token masked immediately, real token never stored in runtime state.
                    const formatResult = validateGitHubTokenFormat(token);
                    if (formatResult.isValid) {
                      setGitHubAccessState(startGitHubAccessValidation(formatResult.maskedToken));
                      // NOTE: In production, this would trigger actual GitHub API validation.
                      // For now, transition to 'requested' to indicate format OK but pending real auth.
                      setGitHubAccessState(requestGitHubAccess(formatResult.maskedToken));
                      appendChatLine({ 
                        role: 'assistant', 
                        text: `Token-Format akzeptiert (${formatResult.maskedToken}). GitHub-Schreibzugriff wird für Draft PR benötigt.` 
                      });
                    } else {
                      setGitHubAccessState(failGitHubAccessValidation('', formatResult.error || 'Ungültiges Format'));
                    }
                  }}
                  onDismiss={() => {}}
                />
              )}

              {/* ── Issue #426: Worker Blocker Card */}
              {workerBlocker && (
                <WorkerBlockerCard
                  blocker={workerBlocker}
                  onRetry={() => {
                    setWorkerBlocker(null);
                    addLog("info", "Worker retry from card", "router");
                  }}
                  onRetryWithMessage={(msg) => {
                    setWorkerBlocker(null);
                    addLog(
                      "info",
                      "Worker retry with message from card",
                      "router",
                    );
                    retrySubmit(msg);
                  }}
                  onExplain={() => {
                    const explanation = explainDevChatWorkerDiagnostic(
                      workerBlocker.diagnostic,
                    );
                    appendChatLine({ role: "assistant", text: explanation });
                  }}
                  onOpenHandsInstead={(msg) => {
                    startAgentFromText(msg);
                  }}
                  userMessage={
                    chatHistory.length > 0
                      ? chatHistory[chatHistory.length - 1].text
                      : undefined
                  }
                />
              )}

              {/* ── Issue #431: Draft PR Card */}
              {openhandsJob?.draftPrUrl && (
                <DraftPrCard
                  url={openhandsJob.draftPrUrl}
                  changedFiles={openhandsJob.changedFiles || []}
                  onOpenBrowser={() =>
                    window.open(openhandsJob.draftPrUrl, "_blank")
                  }
                  onDiscussInChat={() =>
                    setWishText(`Erkläre mir die Änderungen im Draft PR.`)
                  }
                />
              )}

              {/* ── Issue #445: AgentResultCard — structured result when PR is ready */}
              {agentWorkSnapshot.state === 'draft_pr_ready' && agentWorkSnapshot.draftPrUrl && (
                <AgentResultCard
                  snapshot={agentWorkSnapshot}
                  onOpen={() => window.open(agentWorkSnapshot.draftPrUrl!, '_blank')}
                  onViewDiff={() =>
                    setWishText('Erkläre mir die Änderungen im Draft PR.')
                  }
                />
              )}

              {/* ── Issue #425: Scroll-away indicator */}
              {userScrolledAway && (
                <div
                  style={{
                    textAlign: "center",
                    fontSize: 11,
                    color: C.textMuted,
                    padding: "4px 16px",
                    fontFamily: "monospace",
                  }}
                >
                  ↑ Nach oben gescrollt · Neue Nachrichten unten
                </div>
              )}

              {/* ── Issue #425: Jump Badge */}
              {unseenCount > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    scrollRef.current?.scrollTo({
                      top: scrollRef.current.scrollHeight,
                      behavior: "smooth",
                    });
                    setUnseenCount(0);
                    setUserScrolledAway(false);
                  }}
                  style={{
                    position: "sticky",
                    bottom: 16,
                    alignSelf: "center",
                    padding: "8px 16px",
                    borderRadius: 20,
                    background: C.accent,
                    color: C.bg,
                    fontSize: 13,
                    fontWeight: 500,
                    border: "none",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  ↓ {unseenCount} Neue Nachricht{unseenCount > 1 ? "en" : ""}
                </button>
              )}

              <div style={{ height: 8 }} />
            </div>
          )}
        </div>
      ) : (
        /* ── MODULE VIEW */
        <div style={{ flex: 1, overflowY: "auto", background: C.bg }}>
          <ModuleScreen
            mod={activeMod}
            signals={signals}
            phases={phases}
            conditions={conditions}
            confidence={confidence}
            sequence={sequence}
            inspectorSignals={deriveRuntimeInspectorSignals(
              activeMod.id.toUpperCase() as "PAT" | "ORC" | "INT" | "BUD",
              buildPatInspectorStateFromStore(patternMemoryStore),
              {
                palDecisions: palDecisions.length,
                fastTierCount: palDecisions.filter((d) => d.tier === "fast").length,
                smartTierCount: palDecisions.filter((d) => d.tier === "smart").length,
                powerTierCount: palDecisions.filter((d) => d.tier === "power").length,
              },
              { chatRepoSnapshot },
              deriveBudStateFromPalDecisions(palDecisions),
            )}
            onSignalClick={(prompt) => setWishText(prompt)}
          />
          <div style={{ height: 12 }} />
        </div>
      )}

      {/* COMPOSER — only in chat view, v3 verbatim */}
      {isChat && (
        <>
          {/* ── Issue #445: SovereignToolLauncher — quick-action "+" launcher */}
          <SovereignToolLauncher
            onSelect={(toolId: ToolId) => {
              if (toolId === 'repo') { setShowRepoExplorer(true); return; }
              if (toolId === 'executor') {
                if (wishText.trim()) startAgentFromText(wishText.trim());
                return;
              }
              if (toolId === 'github_access') {
                appendChatLine({ role: 'assistant', text: 'GitHub-Zugang: Token im Kanal eingeben oder via Einstellungen hinterlegen.' });
                return;
              }
              if (toolId === 'runtime_logs') { setPanelOpen((v) => !v); return; }
              if (toolId === 'diff') {
                setWishText('Zeige mir die aktuellen Änderungen im Repo.');
                return;
              }
            }}
          />
          <Composer
            value={wishText}
            onChange={setWishText}
            onSubmit={() => {
              void handleSubmit();
            }}
            onKeyDown={handleComposerKeyDown}
            disabled={submitDisabled}
            loading={localRepoLoading}
            placeholder={
              chatRepoSnapshot
                ? `Frage zu ${chatRepoSnapshot.name}…`
                : "GitHub URL oder Auftrag…"
            }
            routeHint={composerRouteHint({
              draft: wishText,
              workerBlocked,
              agentDisabled,
            })}
            slashMenu={
              showSlashCommands ? (
                <SlashCommandMenu
                  commands={slashMatches}
                  selectedIndex={selectedSlashIndex}
                  onSelect={submitSelectedSlashCommand}
                />
              ) : null
            }
          />
        </>
      )}

      {/* BOTTOM TAB BAR — 7 tabs, SESSION removed */}
      <BottomTabBar
        modules={MODULES}
        activeTab={activeTab}
        signals={signals}
        onTabClick={switchTab}
      />

      {/* OVERLAYS — v3 verbatim */}
      {showRuntimeSheet && (
        <RuntimeSheet
          sources={runtimeSources}
          current={runtimeSource}
          onClose={() => setShowRuntime(false)}
        />
      )}
      {showRepoExplorer && (
        <div
          onClick={() => setShowRepoExplorer(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 80,
            background: "rgba(14,17,22,0.82)",
            backdropFilter: "blur(6px)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-end",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              maxHeight: "78vh",
              overflowY: "auto",
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderBottom: "none",
              borderRadius: "20px 20px 0 0",
              padding: "12px 14px 20px",
            }}
          >
            <RepoTreeExplorer
              snapshot={chatRepoSnapshot}
              onClose={() => setShowRepoExplorer(false)}
              onFileClick={handleRepoExplorerFileClick}
            />
          </div>
        </div>
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
          palStats={palStats}
          chatHistory={chatHistory}
          onExportChat={async () => {
            const exported = exportChatHistory(chatHistory, chatRepoSnapshot);
            const result = await shareChatExport(exported);
            if (result === "copied") {
              appendChatLine({
                role: "assistant",
                text: "Chat in Zwischenablage kopiert.",
              });
            } else if (result === "failed") {
              appendChatLine({
                role: "assistant",
                text: "Chat konnte nicht geteilt werden.",
              });
            }
          }}
        />
      )}
      {showOpenHandsBriefing && openhandsConfig && (
        <div
          onClick={() => setOHB(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            background: "rgba(14,17,22,0.88)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "100%",
              maxWidth: 440,
              maxHeight: "90vh",
              overflowY: "auto",
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
