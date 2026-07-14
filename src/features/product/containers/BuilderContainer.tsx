import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  appendOption,
  buildAnalyzedMission,
  buildOutcomeHints,
  collapseRepeatedAnalyzedMission,
  deriveAgentStatus,
  fmtTime,
  isAnalyzedMission,
  missionToWishText,
  normalizeMissionText,
  safeHttpsUrl,
  splitFilePath,
  type AgentStatus,
  type ChatOutcomeHint,
  type IdeaOption,
} from "../runtime/builderContainerHelpers";
import { deriveBuilderContainerState } from "../runtime/builderContainerRuntime";
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
import {
  buildToolchainAutoContext,
  formatToolchainAutoContext,
} from "../runtime/toolchainAutoCallingRuntime";
import { Ampel } from "../components/Ampel";
import { FileBadge } from "../components/FileBadge";
import { ThoughtBubble } from "../components/ThoughtBubble";
import { ThinkingDots } from "../components/ThinkingDots";
import { OutcomeHints } from "../components/OutcomeHints";
import { C, STATUS_COLOR, STATUS_LABEL } from "../components/builderConstants";
import { WorkbenchStatusChips } from "../components/WorkbenchStatusChips";
import { WorkbenchSlotDrawer } from "../components/WorkbenchSlotDrawer";
import { WorkbenchSidePanel } from "../components/WorkbenchSidePanel";
import {
  WorkerBlockerCard,
  WorkerDegradedBanner,
} from "../components/WorkerBlockerCard";
import { DraftPrCard } from "../components/DraftPrCard";
import { ChatMarkdown } from "../components/ChatMarkdown";
import { PacedChatText } from "../components/PacedChatText";
import { GitHubAccessCard } from "../components/GitHubAccessCard";
import { SecurityBlockCard } from "../components/SecurityBlockCard";
import { RepoTreeExplorer } from "../components/RepoTreeExplorer";
import { CompactRepoSetupSheet } from "../components/CompactRepoSetupSheet";
import { PatchDiffEvidenceSheet } from "../components/PatchDiffEvidenceSheet";
import { RuntimeEvidenceLogSheet } from "../components/RuntimeEvidenceLogSheet";
import { ActionSuggestionStrip } from "../components/ActionSuggestionStrip";
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
import {
  SOVEREIGN_PRESET_ACTIONS,
  buildSovereignPresetActionSubmission,
  evaluateSovereignPresetActionGate,
  getSovereignPresetAction,
  type SovereignPresetActionId,
} from "../runtime/sovereignPresetActionRuntime";
import { loadSessionMemory, formatSessionMemoryAge } from "../runtime/sovereignSessionMemory";
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
import {
  createBudgetLedger,
  recordRouteUsage,
  selectLlmRoute,
  createRouteRegistry,
  createUserPlanState,
  summarizeLlmBudgetState,
  type LlmBudgetLedger,
  type LlmRouteSelectionResult,
} from "../runtime/llmRouteBudgetRuntime";
import {
  decideSovereignCapabilityRoute,
  buildCapabilityRouteActionEvent,
} from "../runtime/sovereignCapabilityRouter";
import type { CapabilityRouterInput } from "../runtime/sovereignCapabilityRouter";
import type {
  SovereignAgentConfig,
  SovereignAgentJobSnapshot,
} from "../runtime/sovereignAgentRuntime";
import {
  createGitHubAccessSnapshot,
  requestGitHubAccess,
  startGitHubAccessValidation,
  completeGitHubAccessValidation,
  failGitHubAccessValidation,
  validateGitHubTokenFormat,
  validateGitHubTokenForRepo,
  canPerformGitHubWrite,
  type GitHubAccessSnapshot,
} from "../runtime/githubAccessRuntime";
import { evaluateInputPolicy, createSecurityCardDisplay } from "../runtime/secureInputGuard";
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
import { AgentEventStream } from "../components/AgentEventStream";
import { AgentResultCard } from "../components/AgentResultCard";
import { SovereignActionStreamPanel } from "../components/SovereignActionStreamPanel";
import {
  appendSovereignActionEvent,
  buildBlockedActionEvent,
  buildInputReceivedEvent,
  buildLocalRuntimeResultEvent,
  buildRepoLoadedEvent,
  buildRouteSelectionEvent,
  buildWorkerRequestEvent,
  buildWorkerResponseEvent,
  createSovereignActionStreamState,
  type SovereignActionEventInput,
} from "../runtime/sovereignActionStreamRuntime";
import {
  createInitialDraftState,
  createIntegrationIntentDraft,
  canConfirmIntegrationIntentDraft,
  buildDraftCreatedEvent,
  buildDraftConfirmedEvent,
  buildDraftRejectedEvent,
  buildDraftRephrasedEvent,
  buildRouteStartedEvent,
  buildRouteBlockedEvent,
  hasPendingDraft,
  type IntegrationIntentDraftState,
  type IntegrationIntentDraft,
  type IntegrationIntentDraftGateSnapshot,
} from "../runtime/integrationIntentDraftRuntime";
import { IntegrationIntentDraftCard } from "../components/IntegrationIntentDraftCard";
import { SovereignToolLauncher, type ToolId } from "../components/SovereignToolLauncher";
import { useLauncherStore } from "../../launcher/useLauncherStore";
import { LauncherMenu } from "../../launcher/components/LauncherMenu";
import { LauncherWindowHost } from "../../launcher/components/LauncherWindowHost";
import { LauncherTaskbar } from "../../launcher/components/LauncherTaskbar";
import { LauncherProvider, readGeminiApiKeyFromStorage } from "../../launcher/LauncherContext";
import {
  usePatternMemoryStore,
  loadPatternMemoryStoreFromStorage,
} from "../hooks/usePatternMemoryStore";
import { buildSovereignToolCapabilityRegistry } from "../runtime/sovereignToolCapabilityRuntime";
import { createSovereignWorkspaceScope } from "../runtime/sovereignWorkspaceScopeRuntime";
import {
  classifySovereignExecutorIntent,
} from "../runtime/sovereignExecutorRuntime";
import { decideSovereignExecutorBridgeRoute } from "../../../runtime/sovereignExecutorBridgeRuntime";

// ─────────────────────────────────────────────────────────────
// TYPES  (identical props to BuilderContainer — drop-in swap)
// ─────────────────────────────────────────────────────────────

export interface SovereignStagedChange {
  readonly path: string;
  readonly content: string;
  readonly baseContent?: string;
}

export interface SovereignDraftPrPublishInput {
  readonly repoUrl: string;
  readonly branch: string;
  readonly mission: string;
  readonly changes: readonly SovereignStagedChange[];
  readonly confirmed: boolean;
  readonly githubAccessToken?: string;
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
  onPublishDraftPr: (input: SovereignDraftPrPublishInput) => void | Promise<void>;
  agentReady?: boolean;
  agentConfig?: SovereignAgentConfig;
  agentJob?: SovereignAgentJobSnapshot;
  agentJobStatus?: string;
  agentIsRunning?: boolean;
  onStartAgent?: (mission: string, input?: { readonly repoUrl: string; readonly branch?: string; readonly githubAccessToken?: string }) => void | Promise<void>;
  onCancelAgent?: () => void;
  /**
   * Traditional publish path — set by the parent to the PR URL returned by
   * mergeWhenGreen once approvalConfirmed === true. Omit when not available.
   */
  publishedPrUrl?: string;
}

// Local types — extracted to builderContainerTypes.ts
import type {
  AnimPhase,
  ChatLine,
  ChatRole,
  CondStatus,
  ModuleCfg,
  ModuleCond,
  ModuleId,
  RuntimeSource,
  RuntimeTier,
  SignalType,
  WorkerRuntimeBlocker,
} from "../runtime/builderContainerTypes";
import {
  deriveWorkbenchStatusSlots,
  type WorkbenchStatusSlot,
  type WorkbenchStatusSlotId,
  type WorkbenchStatusTone,
} from "../runtime/builderWorkbenchStatus";
// Chat/PAL helpers — extracted to builderChatHelpers.ts / builderPALRuntime.ts
import {
  buildChatLines,
  buildLocalStatusAnswer,
  buildRuntimeConfidence,
  buildWorkerBlockerAnswer,
  buildWorkerMessages,
  composerRouteHint,
  confidenceLabel,
  createChatLineId,
  isFollowUpWhyQuestion,
  isLocalCompletionStatusQuestion,
  isWriteIntent,
  phaseFromSignalAndConditions,
  sameConditions,
  sameRecord,
} from "../runtime/builderChatHelpers";
import {
  BUD_PLAN,
  BUD_REGISTRY,
  deriveBudFromLedger,
  palRoute,
  type PALDecision,
} from "../runtime/builderPALRuntime";

// ─────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────

const CUTE_THINKING_FRAME_MS = 1100;
const CUTE_IDLE_FRAME_MS = 1450;
const builderContainerContract = getSovereignContainerContract("builder");

const TIER_COLOR: Record<RuntimeTier, string> = {
  ready: C.green,
  active: C.sky,
  blocked: C.rose,
  unknown: C.amber,
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
// HELPERS — extracted to builderContainerHelpers.ts
// appendOption, normalizeMissionText, collapseRepeatedAnalyzedMission,
// isAnalyzedMission, missionToWishText, buildAnalyzedMission,
// safeHttpsUrl, splitFilePath, buildOutcomeHints, deriveAgentStatus, fmtTime
// ─────────────────────────────────────────────────────────────

// Intent detection from workerIntentDetector module
import {
  isSovereignAgentExecutionIntent,
  isCodeGenerationIntent,
  isWorkerRetryIntent,
  isWorkerDiagnosticQuestion,
  isDelegationIntent,
  isDelegatedSovereignAgentExecutionIntent,
  isExecutorStatusQuestion,
  buildExecutorStatusAnswer,
  isAlternativeWriteRouteIntent,
  buildAlternativeRouteStatusAnswer,
} from "../runtime/workerIntentDetector";
import { buildDirectPatchPlanWithContentLoad, detectDirectPatchTarget } from "../runtime/directGithubPatchRuntime";
import { buildGeneratedFileDiffReport, type GeneratedFileDiffReport } from "../runtime/generatedFileDiffPreview";
import {
  buildSovereignInspectionResultEvent,
  buildSovereignRuntimeEvidenceLog,
  decideSovereignCompactShortcutExecution,
} from "../runtime/sovereignCompactShortcutExecutionRuntime";
import {
  useSovereignToolInspectionStore,
  type SovereignToolInspectionId,
} from "../runtime/sovereignToolInspectionRuntime";
import {
  decideSovereignSideMenuDraftPr,
  decideSovereignSideMenuShare,
  type SovereignSideMenuDraftPrDecision,
  type SovereignSideMenuShareDecision,
} from "../runtime/sovereignSideMenuRuntime";
import {
  buildRepoEvidenceScopeKey,
  buildRepositoryTargetKey,
  selectRepoScopedAgentJob,
  selectRepositoryScopedPullRequestUrl,
} from "../runtime/sovereignRepoEvidenceScopeRuntime";
import { useCreditGuard } from '../../billing/useCreditGuard';
import {
  buildAreRepositoryState,
  evaluateAreInference,
  quarantineAreResponse,
  type AreInferenceResult,
} from '../../inference/areInferenceApi';
import { emitAreStateTransition, type ArePreviousState } from '../../inference/arePredictiveBridge';
import { CreditDisplay } from '../../billing/components/CreditDisplay';
import { PaywallModal } from '../../billing/PaywallModal';
import { useUserStore } from '../../user/useUserStore';
import { LoginModal } from '../../user/components/LoginModal';
import { UserProfile } from '../../user/components/UserProfile';
import { useToolchainStore } from '../../toolchain/useToolchainStore';
import { useSkillsStore } from '../../toolchain/useSkillsStore';
import { SkillScanPanel } from '../../toolchain/components/SkillScanPanel';

// ─────────────────────────────────────────────────────────────
// PAL ROUTER — imported from builderPALRuntime.ts
// ─────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────
// SUB-COMPONENTS
// ─────────────────────────────────────────────────────────────

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
              title={m.id}
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



// TopBar — v3 verbatim + Workbench status chips + panel toggle + PAL badge
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
  credits,
  userAvatar,
  userInitials,
  userLoggedIn,
  onUserClick,
  workbenchStatusSlots,
  onWorkbenchSlotClick,
  showInspector,
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
  credits?: number;
  userAvatar?: string | null;
  userInitials?: string;
  userLoggedIn?: boolean;
  onUserClick?: () => void;
  workbenchStatusSlots: WorkbenchStatusSlot[];
  onWorkbenchSlotClick: (id: WorkbenchStatusSlotId) => void;
  showInspector: boolean;
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
          title="Menü"
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

        <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, overflow: "hidden" }}>
            <span
              style={{
                fontFamily: "monospace",
                fontSize: 13,
                fontWeight: 700,
                color: C.text,
                letterSpacing: -0.3,
                whiteSpace: "nowrap",
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

        {userLoggedIn && credits !== undefined && (
          <CreditDisplay credits={credits} />
        )}

        {/* User avatar / login button — Issue #459 */}
        {onUserClick && (
          <button
            type="button"
            onClick={onUserClick}
            aria-label={userLoggedIn ? 'Profil' : 'Anmelden'}
            title={userLoggedIn ? 'Profil' : 'Anmelden'}
            style={{
              width: 32, height: 32, borderRadius: '50%',
              background: userLoggedIn ? `${C.accent}22` : C.bg,
              border: `1px solid ${userLoggedIn ? `${C.accent}55` : C.border}`,
              color: userLoggedIn ? C.accent : C.textSub,
              fontSize: userAvatar ? 0 : 13,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', flexShrink: 0,
              overflow: 'hidden', fontWeight: 700,
              padding: 0,
            }}
          >
            {userAvatar
              ? <img src={userAvatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : userLoggedIn
                ? <span style={{ fontSize: 11 }}>{userInitials || '?'}</span>
                : <span>👤</span>
            }
          </button>
        )}

        <Ampel status={status} compact />

        <button
          type="button"
          onClick={onSourceClick}
          aria-label="RT – Runtime Quelle"
          title="Runtime Quelle"
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
          aria-label={panelOpen ? "Panel schließen" : "Panel öffnen"}
          title={panelOpen ? "Panel schließen" : "Panel öffnen"}
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

      {/* Werkbank Status — Actions/Files/Logs/Errors/Draft PR, primary and always visible */}
      <WorkbenchStatusChips slots={workbenchStatusSlots} onSlotClick={onWorkbenchSlotClick} />

      {/* Inspector — technical runtime modules, internal-only, hidden unless explicitly opened */}
      {showInspector && (
        <>
          <div
            style={{
              padding: "3px 10px 0",
              fontFamily: "monospace",
              fontSize: 8,
              color: C.textMuted,
              borderTop: `1px solid ${C.border}`,
            }}
          >
            Inspector (intern)
          </div>
          <ModuleLamps
            modules={modules}
            signals={signals}
            activeTab={activeTab}
            onTabClick={onTabClick}
          />
        </>
      )}
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
            aria-label="Logs löschen"
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
              padding: "9px 12px",
              background: isUser ? C.userBg : C.asstBg,
              borderRadius: isUser
                ? "18px 18px 4px 18px"
                : "4px 18px 18px 18px",
              border: `1px solid ${isUser ? "#243c5a" : C.border}`,
              color: C.text,
              fontSize: 13,
              lineHeight: 1.45,
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
        className="sovereign-idea-grid"
        style={{
          display: "grid",
          gap: 10,
          width: "100%",
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
          width: "100%",
          maxWidth: 520,
          margin: "0 auto",
          background: C.surface,
          borderRadius: "20px 20px 0 0",
          border: `1px solid ${C.border}`,
          borderBottom: "none",
          padding: "0 0 24px",
          maxHeight: "80vh",
          overflowY: "auto",
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
  onOpenAllTools,
  onOpenRepo,
  onOpenRuntimeLogs,
  onOpenGithubAccess,
  onSelectPreset,
  onDraftPrAction,
  draftPrDecision,
  shareDecision,
  chatRepoSnapshot,
  githubAccessState,
  onCancelAgent,
  agentIsRunning,
  palStats,
  onExportChat,
}: {
  onClose: () => void;
  onOpenAllTools: () => void;
  onOpenRepo: () => void;
  onOpenRuntimeLogs: () => void;
  onOpenGithubAccess: () => void;
  onSelectPreset: (id: SovereignPresetActionId) => void;
  onDraftPrAction: () => void;
  draftPrDecision: SovereignSideMenuDraftPrDecision;
  shareDecision: SovereignSideMenuShareDecision;
  chatRepoSnapshot: DevChatRepoSnapshot | null;
  githubAccessState: GitHubAccessSnapshot['state'];
  onCancelAgent?: () => void;
  agentIsRunning?: boolean;
  palStats: { total: number; savings: number } | null;
  onExportChat?: () => void | Promise<void>;
}) {
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const runAndClose = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Sovereign Seitenmenü"
      data-testid="sovereign-side-menu"
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
        data-testid="sovereign-side-menu-panel"
        style={{
          width: "min(86vw, 320px)",
          maxHeight: "100dvh",
          overflowY: "auto",
          overscrollBehavior: "contain",
          WebkitOverflowScrolling: "touch",
          background: C.surface,
          borderLeft: `1px solid ${C.border}`,
          display: "flex",
          flexDirection: "column",
          boxShadow: "-8px 0 32px rgba(0,0,0,0.5)",
          paddingBottom: "env(safe-area-inset-bottom)",
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
            aria-label="Menü schließen"
            title="Menü schließen"
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

        {/* Runtime-bound tools — same surfaces as the compact launcher */}
        <div
          style={{
            margin: "8px 12px 0",
            padding: "10px",
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
              marginBottom: 8,
            }}
          >
            Werkzeuge · echte Flächen
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {[
              { label: "⬡ Alle Tools", status: "Launcher", action: onOpenAllTools },
              { label: chatRepoSnapshot ? "⎇ Repo öffnen" : "⎇ Repo laden", status: chatRepoSnapshot ? "bereit" : "Setup", action: onOpenRepo },
              { label: "≡ Runtime Logs", status: "Evidence", action: onOpenRuntimeLogs },
              {
                label: "🔑 GitHub Access",
                status: githubAccessState === 'ready' ? "validiert" : githubAccessState === 'validating' || githubAccessState === 'requested' ? "prüft" : "fehlt",
                action: onOpenGithubAccess,
              },
            ].map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={() => runAndClose(item.action)}
                style={{
                  minHeight: 48,
                  padding: "8px 9px",
                  borderRadius: 9,
                  background: C.surface,
                  border: `1px solid ${C.border}`,
                  color: C.text,
                  cursor: "pointer",
                  textAlign: "left",
                  fontFamily: "monospace",
                  fontSize: 10,
                }}
              >
                <span style={{ display: "block" }}>{item.label}</span>
                <span style={{ display: "block", marginTop: 3, fontSize: 8, color: C.textMuted }}>{item.status}</span>
              </button>
            ))}
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
              disabled={!shareDecision.canShare}
              data-gate-state={shareDecision.canShare ? 'ready' : 'evidence-missing'}
              title={shareDecision.reason}
              onClick={() => {
                if (!shareDecision.canShare) return;
                const result = onExportChat();
                if (result && typeof (result as Promise<void>).then === 'function') {
                  void Promise.resolve(result).catch(() => undefined).finally(onClose);
                  return;
                }
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
                cursor: shareDecision.canShare ? "pointer" : "not-allowed",
                opacity: shareDecision.canShare ? 1 : 0.48,
                textAlign: "left",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
              }}
            >
              <span><span>📤</span> Chat teilen</span>
              <span style={{ fontSize: 8, color: C.textMuted }}>{shareDecision.statusLabel}</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => runAndClose(() => onSelectPreset('architecture_feature_suggestions'))}
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
            onClick={() => runAndClose(() => onSelectPreset('error_fix_plan'))}
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
          {agentIsRunning && onCancelAgent && (
            <button
              type="button"
              onClick={() => {
                onCancelAgent();
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
            disabled={!draftPrDecision.canAct}
            onClick={() => {
              if (!draftPrDecision.canAct) return;
              onDraftPrAction();
              onClose();
            }}
            data-role={SOVEREIGN_ACTION_DRAFT_PR.dataRole}
            data-testid={SOVEREIGN_ACTION_DRAFT_PR.testId}
            data-gate-state={draftPrDecision.state}
            aria-label={SOVEREIGN_ACTION_DRAFT_PR.ariaLabel}
            title={draftPrDecision.reason}
            style={{
              width: "100%",
              padding: "14px",
              borderRadius: 14,
              background: draftPrDecision.canAct
                ? draftPrDecision.action === 'publish-draft-pr'
                  ? C.orange
                  : `${C.amber}22`
                : C.bg,
              border: draftPrDecision.canAct ? "none" : `1px solid ${C.border}`,
              color: draftPrDecision.canAct ? "#fff" : C.textMuted,
              fontFamily: "monospace",
              fontSize: 13,
              fontWeight: 700,
              cursor: draftPrDecision.canAct ? "pointer" : "not-allowed",
              opacity: draftPrDecision.canAct ? 1 : 0.58,
              boxShadow: draftPrDecision.action === 'publish-draft-pr' ? `0 4px 16px ${C.orange}40` : "none",
            }}
          >
            <span style={{ display: "block" }}>{draftPrDecision.label}</span>
            <span style={{ display: "block", marginTop: 4, fontSize: 8, fontWeight: 500, opacity: 0.82 }}>
              {draftPrDecision.statusLabel}
            </span>
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
          title="Senden"
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

// BottomTabBar — Chat stays the sole primary destination; the Inspector toggle
// reveals the technical runtime modules (see ModuleLamps) as an internal debug
// view. Files/Diff/Draft PR/Logs live as understandable Workbench surfaces
// (WorkbenchStatusChips + drawer), not as bottom-nav module abbreviations.
function BottomTabBar({
  activeTab,
  onChatClick,
  inspectorOpen,
  onToggleInspector,
}: {
  activeTab: string;
  onChatClick: () => void;
  inspectorOpen: boolean;
  onToggleInspector: () => void;
}) {
  const isChat = activeTab === "chat";
  return (
    <nav
      style={{
        height: 56,
        background: C.bg,
        borderTop: `1px solid ${C.border}`,
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        flexShrink: 0,
      }}
      aria-label="Sovereign Studio Tabs"
    >
      <button
        type="button"
        onClick={onChatClick}
        aria-current={isChat ? "page" : undefined}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 3,
          background: isChat ? `${C.sky}08` : "transparent",
          border: "none",
          borderTop: `2px solid ${isChat ? C.sky : "transparent"}`,
          cursor: "pointer",
          padding: "4px 2px",
          minWidth: 0,
        }}
      >
        <span style={{ fontSize: 15, color: isChat ? C.sky : C.textMuted }}>⬡</span>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 7.5,
            color: isChat ? C.sky : C.textMuted,
            letterSpacing: 0.3,
          }}
        >
          CHAT
        </span>
      </button>
      <button
        type="button"
        onClick={onToggleInspector}
        aria-pressed={inspectorOpen}
        title="Technische Runtime-Module (intern)"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 3,
          background: inspectorOpen ? `${C.violet}08` : "transparent",
          border: "none",
          borderTop: `2px solid ${inspectorOpen ? C.violet : "transparent"}`,
          cursor: "pointer",
          padding: "4px 2px",
          minWidth: 0,
        }}
      >
        <span style={{ fontSize: 15, color: inspectorOpen ? C.violet : C.textMuted }}>⚙</span>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 7.5,
            color: inspectorOpen ? C.violet : C.textMuted,
            letterSpacing: 0.3,
          }}
        >
          INSPECTOR
        </span>
      </button>
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
  agentReady,
  agentConfig,
  agentJob,
  agentJobStatus,
  agentIsRunning,
  onStartAgent,
  onCancelAgent,
  publishedPrUrl,
}: BuilderContainerProps) {
  // ── Original v3 state (verbatim)
  const [patternMemoryStore, setPatternMemoryStore] = useState<PatternMemoryStore>(() => loadPatternMemoryStoreFromStorage());
  const [wishText, setWishText] = useState(() => missionToWishText(mission));
  const [thinkingFrameIndex, setTFI] = useState(0);
  const [showRuntimeSheet, setShowRuntime] = useState(false);
  const [showSideMenu, setShowSide] = useState(false);
  const [showRepoExplorer, setShowRepoExplorer] = useState(false);
  const [showRepoSetup, setShowRepoSetup] = useState(false);
  const [repoSetupUrl, setRepoSetupUrl] = useState('');
  const [repoSetupError, setRepoSetupError] = useState<string | null>(null);
  const [showRuntimeEvidenceLogs, setShowRuntimeEvidenceLogs] = useState(false);
  const [showPatchDiffEvidence, setShowPatchDiffEvidence] = useState(false);
  const [patchDiffReport, setPatchDiffReport] = useState<GeneratedFileDiffReport | null>(null);
  const [showAgentBriefing, setOHB] = useState(false);
  const [chatRepoSnapshot, setChatRepo] = useState<DevChatRepoSnapshot | null>(
    null,
  );
  const [chatRepoError, setChatRepoError] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatLine[]>([]);
  const [chatResponseBusy, setChatResponseBusy] = useState(false);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [workerBlocker, setWorkerBlocker] =
    useState<WorkerRuntimeBlocker | null>(null);
  const [lastWorkerRequestMessage, setLastWorkerRequestMessage] = useState<string | null>(null);
  const [patchPreviewReady, setPatchPreviewReady] = useState(false);
  const [patchConfirmed, setPatchConfirmed] = useState(false);
  const [stagedChanges, setStagedChanges] = useState<SovereignStagedChange[]>([]);
  const [lastAnswerWasLocal, setLastAnswerWasLocal] = useState(false);
  const [localRepoLoading, setRepoLoading] = useState(false);
  const lastMissionRef = useRef(mission);
  const ignoreNextMissionSyncRef = useRef(false);
  const chatLineIndexRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const nowRef = useRef(Date.now());
  const clearPatchEvidence = useCallback(() => {
    setPatchDiffReport(null);
    setPatchPreviewReady(false);
    setPatchConfirmed(false);
    setStagedChanges([]);
    setShowPatchDiffEvidence(false);
  }, []);

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
  // ── Gap 3: Security card state — shown inline when a secret is detected in input
  const [securityCardPending, setSecurityCardPending] = useState<{
    title: string; text: string; hint: string; buttonLabel: string;
  } | null>(null);
  // When user taps "GitHub-Zugang öffnen" in SecurityBlockCard, force GitHubAccessCard visible
  const [showGitHubAccessOverride, setShowGitHubAccessOverride] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [showInspector, setShowInspector] = useState(false);
  const [openWorkbenchSlot, setOpenWorkbenchSlot] = useState<WorkbenchStatusSlotId | null>(null);
  const [palDecisions, setPalDecisions] = useState<PALDecision[]>([]);
  const [budgetLedger, setBudgetLedger] = useState<LlmBudgetLedger>(createBudgetLedger());
  const { credits, chargeCredits } = useCreditGuard();
  // ── Issue #459: User auth state
  const { user: authUser, refreshUser } = useUserStore();
  const [showLogin, setShowLogin]     = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showPaywall, setShowPaywall] = useState(false);
  useEffect(() => { refreshUser(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Sovereign App Toolchain — auto-load after login
  const { loadTools: loadToolchain, getToolContext, loaded: toolchainLoaded } = useToolchainStore();
  useEffect(() => {
    if (authUser && !toolchainLoaded) { loadToolchain(); }
  }, [authUser, toolchainLoaded, loadToolchain]);

  // ── Sovereign Skill System — auto-load + dynamic slash commands
  const {
    loadSkills,
    getActiveSkillContext,
    getSkillSlashCommands,
    skills: installedSkills,
    loaded: skillsLoaded,
  } = useSkillsStore();
  useEffect(() => {
    if (authUser && !skillsLoaded) { loadSkills(); }
  }, [authUser, skillsLoaded, loadSkills]);
  const [showSkillScan, setShowSkillScan] = useState(false);

  // Dynamic skill slash commands (from installed skills)
  const skillSlashCommands = useMemo(
    () => getSkillSlashCommands().map((s) => ({
      cmd: s.cmd,
      label: s.label,
      action: 'skill-run' as const,
      description: s.description,
      adapted_prompt: s.adapted_prompt,
      is_skill: true,
    })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [installedSkills],
  );
  const [statusLogs, setStatusLogs] = useState<
    Array<{ ts: string; level: string; msg: string; tabId: string }>
  >([]);

  // ── Issue #425: Auto-scroll lock and jump badge
  const [userScrolledAway, setUserScrolledAway] = useState(false);
  const [unseenCount, setUnseenCount] = useState(0);

  const currentRepoScopeKey = useMemo(
    () => buildRepoEvidenceScopeKey(chatRepoSnapshot),
    [chatRepoSnapshot],
  );
  const currentRepositoryTargetKey = useMemo(
    () => buildRepositoryTargetKey(chatRepoSnapshot),
    [chatRepoSnapshot],
  );
  const scopedPublishedPrUrl = useMemo(
    () => selectRepositoryScopedPullRequestUrl(publishedPrUrl, currentRepositoryTargetKey),
    [currentRepositoryTargetKey, publishedPrUrl],
  );
  const scopedAgentJob = useMemo(
    () => selectRepoScopedAgentJob(agentJob, chatRepoSnapshot),
    [chatRepoSnapshot, agentJob],
  );
  const scopedAgentIsRunning = Boolean(
    scopedAgentJob
    && ['queued', 'provisioning', 'running', 'validating'].includes(scopedAgentJob.status),
  );

  // ── Issue #443: GitHub Access State
  const [githubAccessState, setGitHubAccessState] = useState<GitHubAccessSnapshot>(
    createGitHubAccessSnapshot(),
  );
  const [validatedGitHubTargetKey, setValidatedGitHubTargetKey] = useState<string | null>(null);
  const pendingWriteIntentRef = useRef<string | null>(null);
  const currentRepoScopeKeyRef = useRef<string | null>(currentRepoScopeKey);
  currentRepoScopeKeyRef.current = currentRepoScopeKey;
  const isCurrentRepoScope = useCallback(
    (scopeKey: string | null) => Boolean(scopeKey && currentRepoScopeKeyRef.current === scopeKey),
    [],
  );
  const currentRepositoryTargetKeyRef = useRef<string | null>(currentRepositoryTargetKey);
  currentRepositoryTargetKeyRef.current = currentRepositoryTargetKey;
  const githubWriteAllowed = Boolean(
    currentRepositoryTargetKey
    && validatedGitHubTargetKey === currentRepositoryTargetKey
    && canPerformGitHubWrite(githubAccessState),
  );
  const effectiveGitHubAccessState = githubAccessState.state === 'ready' && !githubWriteAllowed
    ? 'missing'
    : githubAccessState.state;
  const effectiveGitHubAccessSnapshot = useMemo(
    () => effectiveGitHubAccessState === githubAccessState.state
      ? githubAccessState
      : createGitHubAccessSnapshot(),
    [effectiveGitHubAccessState, githubAccessState],
  );
  
  // #501: Store validated token in memory for Direct Patch content loading
  // Token is kept only for the current session (component lifetime)
  // SECURITY: Never persisted to sessionStorage/localStorage
  const githubTokenRef = useRef<string | null>(null);
  const previousRepoScopeKeyRef = useRef<string | null>(currentRepoScopeKey);
  const arePreviousStateRef = useRef<ArePreviousState | null>(null);
  useEffect(() => {
    arePreviousStateRef.current = null;
  }, [authUser?.id, currentRepoScopeKey]);

  // ── Issue #445: AgentWorkTimeline state
  const [agentWorkSnapshot, setAgentWorkSnapshot] = useState<AgentWorkSnapshot>(
    () => createIdleSnapshot(`sovereign-${Date.now()}`),
  );

  useEffect(() => {
    const previousScopeKey = previousRepoScopeKeyRef.current;
    if (previousScopeKey === currentRepoScopeKey) return;
    previousRepoScopeKeyRef.current = currentRepoScopeKey;

    clearPatchEvidence();
    setOpenWorkbenchSlot(null);
    setShowRepoExplorer(false);
    setAgentWorkSnapshot(createIdleSnapshot(`sovereign-${Date.now()}`));

    const accessMatchesCurrentRepo = Boolean(
      currentRepositoryTargetKey
      && validatedGitHubTargetKey === currentRepositoryTargetKey,
    );
    if (!accessMatchesCurrentRepo) {
      githubTokenRef.current = null;
      pendingWriteIntentRef.current = null;
      setValidatedGitHubTargetKey(null);
      setGitHubAccessState(createGitHubAccessSnapshot());
      setShowGitHubAccessOverride(false);
    }
  }, [
    clearPatchEvidence,
    currentRepoScopeKey,
    currentRepositoryTargetKey,
    validatedGitHubTargetKey,
  ]);

  // ── Issue #520: Integration Intent Draft State
  // Shows draft card for recognized integration tasks before execution
  const [intentDraftState, setIntentDraftState] = useState<IntegrationIntentDraftState>(
    createInitialDraftState,
  );

  // ── Issue #445: Sync AgentWorkSnapshot only from the current repo/branch job.
  useEffect(() => {
    if (!scopedAgentJob) {
      if (agentJob && agentJob.status !== 'idle') {
        setAgentWorkSnapshot(createIdleSnapshot(`sovereign-${Date.now()}`));
      }
      return;
    }

    const repo = chatRepoSnapshot
      ? `${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo}`
      : null;
    setAgentWorkSnapshot((prev) => {
      let snap = prev;
      if (scopedAgentJob.status === 'queued' || scopedAgentJob.status === 'running') {
        if (snap.state === 'idle') {
          snap = transitionIntentDetected(
            snap,
            repo ?? 'unknown/repo',
            chatRepoSnapshot?.branch ?? 'main',
          );
        }
        if (snap.state === 'intent_detected') {
          snap = transitionExecutorStarting(snap, 'sovereign-agent');
        }
        if (snap.state === 'executor_starting' && scopedAgentJob.jobId) {
          snap = transitionExecutorRunning(snap, scopedAgentJob.jobId);
        }
      }
      if (scopedAgentJob.status === 'failed' && snap.state !== 'failed' && snap.state !== 'draft_pr_ready') {
        snap = transitionFailed(snap, 'Sovereign Agent Runtime fehlgeschlagen.');
      }
      if (scopedAgentJob.status === 'blocked' && snap.state !== 'blocked' && snap.state !== 'draft_pr_ready') {
        snap = transitionBlocked(snap, 'Sovereign Agent Runtime blockiert.');
      }
      if (scopedAgentJob.draftPrUrl && snap.state !== 'draft_pr_ready' && snap.state !== 'failed' && snap.state !== 'blocked') {
        snap = transitionDraftPrReady(snap, scopedAgentJob.draftPrUrl);
        if (patchPreviewReady) {
          setPatchPreviewReady(false);
          setPatchConfirmed(true);
        }
      }
      if (scopedAgentJob.status === 'idle' && snap.state !== 'idle' && snap.state !== 'draft_pr_ready') {
        snap = createIdleSnapshot(`sovereign-${Date.now()}`);
      }
      return snap;
    });
  }, [chatRepoSnapshot, agentJob, patchPreviewReady, scopedAgentJob]);

  // ── Slash command menu state (Issue #428)
  const [selectedSlashIndex, setSelectedSlashIndex] = useState(0);
  const [slashMenuDismissed, setSlashMenuDismissed] = useState(false);
  const slashMatches = useMemo(
    () => matchingSlashCommands(wishText, skillSlashCommands),
    [wishText, skillSlashCommands],
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

  const stageGeneratedPatch = useCallback((args: {
    readonly path: string;
    readonly proposedContent: string;
    readonly baseContent: string;
    readonly summary: string;
  }) => {
    const report = buildGeneratedFileDiffReport(
      [{ path: args.path, content: args.proposedContent, reason: args.summary || 'Direct GitHub Patch generiert' }],
      [{ path: args.path, content: args.baseContent, found: true }],
    );
    setPatchDiffReport(report);
    setStagedChanges([{
      path: args.path,
      content: args.proposedContent,
      baseContent: args.baseContent,
    }]);
    setPatchPreviewReady(true);
    setPatchConfirmed(false);
    setShowPatchDiffEvidence(true);
  }, []);

  const [actionStream, setActionStream] = useState(() => createSovereignActionStreamState());
  const appendActionEvent = useCallback((event: SovereignActionEventInput) => {
    setActionStream((current) => appendSovereignActionEvent(current, event));
  }, []);
  const inspectionEvidence = useSovereignToolInspectionStore((store) => store.evidence);
  const completedInspectionEvidenceRef = useRef<Partial<Record<SovereignToolInspectionId, number>>>({});
  const sovereignAgentStartAvailable = Boolean(agentReady && onStartAgent);
  const executorIntent = useMemo(() => classifySovereignExecutorIntent(wishText), [wishText]);
  const runtimeEvidenceLog = useMemo(
    () => buildSovereignRuntimeEvidenceLog(actionStream.events, scopedAgentJob?.events ?? []),
    [actionStream.events, scopedAgentJob?.events],
  );

  useEffect(() => {
    const inspectionIds: readonly SovereignToolInspectionId[] = ['health', 'memory', 'coverage', 'settings'];
    for (const id of inspectionIds) {
      const evidence = inspectionEvidence[id];
      if (!evidence) continue;
      if (completedInspectionEvidenceRef.current[id] === evidence.observedAt) continue;

      const started = [...actionStream.events].reverse().find(
        (entry) => entry.route === id
          && entry.state === 'running'
          && entry.label === `${id} Inspektion geöffnet`,
      );
      if (!started) continue;

      const resultEvent = buildSovereignInspectionResultEvent(id, evidence, started.createdAt);
      if (!resultEvent) continue;
      completedInspectionEvidenceRef.current[id] = evidence.observedAt;
      appendActionEvent(resultEvent);
    }
  }, [actionStream.events, appendActionEvent, inspectionEvidence]);

  const hasScopedWorkerResponse = useMemo(
    () => actionStream.events.some((event) =>
      event.route === 'worker'
      && event.kind === 'llm_response_received'
      && event.state === 'done'
    ),
    [actionStream.events],
  );

  // ── Builder Workbench status slots (Actions/Files/Logs/Errors/Draft PR) —
  // derived purely from runtime state, never fabricated. Fronts the technical
  // module lamps as the primary, always-visible status vocabulary.
  const workbenchStatusSlots = useMemo(
    () =>
      deriveWorkbenchStatusSlots({
        logs: statusLogs,
        workerBlocker,
        chatRepoError,
        agentJob: scopedAgentJob,
        publishedPrUrl: scopedPublishedPrUrl,
        githubState: effectiveGitHubAccessState,
        agentConfigured: sovereignAgentStartAvailable,
        patchRouteAvailable: Boolean(githubWriteAllowed && chatRepoSnapshot && githubTokenRef.current),
      }),
    [
      statusLogs,
      workerBlocker,
      chatRepoError,
      scopedAgentJob,
      scopedPublishedPrUrl,
      effectiveGitHubAccessState,
      sovereignAgentStartAvailable,
      githubWriteAllowed,
      chatRepoSnapshot,
    ],
  );

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

  // ── Issue #557: Show session restore age on startup
  useEffect(() => {
    const snapshot = loadSessionMemory(localStorage);
    if (!snapshot) return;
    const age = formatSessionMemoryAge(snapshot, Date.now());
    const ONE_DAY_MS = 24 * 60 * 60 * 1000;
    const isVeryOld = Date.now() - snapshot.savedAt > ONE_DAY_MS;
    const message = isVeryOld
      ? `Ältere Sitzung wiederhergestellt — bitte Repo/Status prüfen. (${age})`
      : `Letzte Sitzung von vor ${age} wiederhergestellt.`;
    appendChatLine({ role: 'assistant', text: message });
  }, [appendChatLine]);

  // ── Issue #447: Auto-save workflow patterns after Draft PR success
  usePatternMemoryStore({
    agentWorkSnapshot,
    patternMemoryStore,
    setPatternMemoryStore,
    mission,
    repoOwner: chatRepoSnapshot?.owner ?? '',
    repoName: chatRepoSnapshot?.repo ?? '',
    appendChatLine,
    publishedPrUrl: scopedPublishedPrUrl,
  });

  // ── Aufgabe 5: Track unseen activity — not just chat lines, but also the
  // inline action stream (Sovereign trace) and streaming worker replies.
  // Every new chat line, action-stream event, or freshly-started stream
  // counts as one unit of "unseen" activity while the user has scrolled away.
  const chatActivitySignal =
    chatHistory.length + actionStream.events.length + (streamingText !== null ? 1 : 0);
  const lastChatActivitySignalRef = useRef(chatActivitySignal);
  useEffect(() => {
    if (chatActivitySignal > lastChatActivitySignalRef.current) {
      if (userScrolledAway) {
        setUnseenCount(
          (prev) =>
            prev + (chatActivitySignal - lastChatActivitySignalRef.current),
        );
      }
    }
    lastChatActivitySignalRef.current = chatActivitySignal;
  }, [chatActivitySignal, userScrolledAway]);

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
  // A complete local runtime snapshot is the sole Builder repo truth. The legacy
  // repoReady prop may describe another surface, but cannot authorize Builder work.
  const isPartialRepoSnapshot = Boolean(chatRepoSnapshot && !currentRepoScopeKey);
  const effectiveRepoReady = Boolean(currentRepoScopeKey);
  const effectiveRepoReason = effectiveRepoReady && chatRepoSnapshot
    ? summarizeDevChatRepoSnapshot(chatRepoSnapshot)
    : repoReason.trim() || 'Kein vollständiger Builder-Repo-Snapshot vorhanden.';
  const state = deriveBuilderContainerState({
    repoReady: effectiveRepoReady,
    repoBusy: repoBusy || localRepoLoading,
    runtimeBusy,
    isPublishing,
    mission,
    sovereignSummary,
    sovereignPreview,
  });
  useEffect(() => {
    if (!effectiveRepoReady) return;
    setShowRepoSetup(false);
    setRepoSetupError(null);
  }, [effectiveRepoReady]);
  const workerBlocked = Boolean(workerBlocker);
  const runtimeThinkingActive = Boolean(
    chatResponseBusy ||
    scopedAgentIsRunning ||
    repoBusy ||
    localRepoLoading ||
    runtimeBusy ||
    isPublishing,
  );
  const workStateStatus = runtimeThinkingActive
    ? chatResponseBusy
      ? "Cloudflare Worker antwortet"
      : scopedAgentJob
        ? agentJobStatus?.trim() || "Sovereign Agent Runtime arbeitet"
        : "Runtime arbeitet"
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
    () => buildOutcomeHints(scopedAgentJob),
    [scopedAgentJob],
  );
  const agentDisabled =
    !effectiveRepoReady ||
    repoBusy ||
    localRepoLoading ||
    runtimeBusy ||
    Boolean(scopedAgentIsRunning) ||
    !sovereignAgentStartAvailable;
  const agentStatus = workerBlocker
    ? "error"
    : chatResponseBusy
      ? "thinking"
      : deriveAgentStatus({
          repoBusy,
          runtimeBusy,
          isPublishing,
          agentIsRunning: scopedAgentIsRunning,
          agentJob: scopedAgentJob,
          localRepoLoading,
          localRepoError: Boolean(chatRepoError),
        });
  const workerHealthReady = workerBlocker?.health?.ok === true;
  const workerResponseReady = hasScopedWorkerResponse;
  const workerSourceTier: RuntimeTier = workerBlocker
    ? "blocked"
    : chatResponseBusy
      ? "active"
      : workerHealthReady || workerResponseReady
        ? "ready"
        : "unknown";
  const runtimeSource = {
    id: "worker-chat",
    label: workerBlocker
      ? "Cloudflare Worker blockiert"
      : workerSourceTier === "unknown"
        ? "Cloudflare Worker nicht geprüft"
        : "Cloudflare Worker",
    tier: workerSourceTier,
    description: workerBlocker
      ? workerBlocker.message
      : workerSourceTier === "unknown"
        ? "Noch keine Health- oder Response-Evidence für diese Sitzung."
        : SOVEREIGN_WORKER_CHAT,
    available: workerHealthReady || workerResponseReady,
  };
  const runtimeSources = [
    runtimeSource,
    {
      id: "worker-kv",
      label: "Worker KV konfiguriert",
      tier: "unknown" as RuntimeTier,
      description: `${SOVEREIGN_WORKER_KV} · keine Sitzungs-Evidence`,
      available: false,
    },
    {
      id: "worker-models",
      label: "Modellkatalog konfiguriert",
      tier: "unknown" as RuntimeTier,
      description: `${DEV_CHAT_WORKER_MODELS.map((m) => m.label).join(" · ")} · keine vollständige Live-Evidence`,
      available: false,
    },
    {
      id: "sovereign-agent-runtime",
      label: sovereignAgentStartAvailable ? "Sovereign Agent Runtime" : "Sovereign Agent offline",
      tier: (sovereignAgentStartAvailable
        ? scopedAgentIsRunning
          ? "active"
          : "ready"
        : "blocked") as RuntimeTier,
      description: sovereignAgentStartAvailable
        ? "Interne Sovereign Agent Runtime für Code/Draft-PR-Aufträge"
        : agentReady
          ? "Sovereign Agent Runtime konfiguriert, aber Start-Callback nicht verdrahtet"
          : "Sovereign Agent Runtime nicht verbunden",
      available: sovereignAgentStartAvailable,
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
        agentJob: scopedAgentJob,
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
      scopedAgentJob,
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

  // ── Aufgabe 5: Robust autoscroll — scroll to bottom on any new chat line,
  // action-stream event, or stream update, UNLESS the user has intentionally
  // scrolled away. While scrolled away, new activity only bumps the unseen
  // badge (see chatActivitySignal effect above), never yanks the viewport.
  useEffect(() => {
    if (!scrollRef.current) return;
    if (userScrolledAway) return;
    const node = scrollRef.current;
    const raf = requestAnimationFrame(() => {
      if (typeof node.scrollTo === "function") {
        node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
      } else {
        node.scrollTop = node.scrollHeight;
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [
    chatLines.length,
    outcomeHints.length,
    runtimeThinkingActive,
    streamingText,
    actionStream.events.length,
    workerBlocker,
    showGitHubAccessOverride,
    userScrolledAway,
  ]);

  useEffect(() => {
    nowRef.current = Date.now();
  }, [chatLines.length]);

  // ── AppControl runtime binding
  // No simulated progress: lamps, phases and conditions are derived from real runtime state.
  useEffect(() => {
    const jobBlocked =
      scopedAgentJob?.status === "blocked" ||
      scopedAgentJob?.status === "failed" ||
      Boolean(chatRepoError) ||
      Boolean(workerBlocker);
    const hasOutput =
      (scopedAgentJob?.changedFiles?.length ?? 0) > 0 ||
      Boolean(scopedAgentJob?.draftPrUrl);
    const budState = deriveBudFromLedger(budgetLedger);
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
        : scopedAgentIsRunning
          ? "processing"
          : agentReady
            ? "active"
            : "warning",
      orchestr: jobBlocked
        ? "error"
        : isPublishing || scopedAgentIsRunning
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
        { label: "Config valid", status: agentConfig ? "pass" : "wait" },
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
          label: "Sovereign Agent configured",
          status: agentReady ? "pass" : "wait",
        },
        {
          label: "Runtime active only on real job",
          status: scopedAgentIsRunning ? "pass" : "wait",
        },
        {
          label: "Repo snapshot synced",
          status: effectiveRepoReady ? "pass" : "wait",
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
          status: runtimeEvidenceLog.length > 0 ? "pass" : "wait",
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
        agentReady,
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
    agentConfig,
    scopedAgentIsRunning,
    scopedAgentJob?.changedFiles?.length,
    scopedAgentJob?.draftPrUrl,
    scopedAgentJob?.status,
    agentReady,
    outcomeHints.length,
    palDecisions.length,
    budgetLedger,
    repoBusy,
    runtimeEvidenceLog.length,
    runtimeThinkingActive,
    signals,
    state.disabledReason,
    statusLogs.length,
    wishText,
    workerBlocker,
  ]);

  // ── Chat runtime actions: composer draft, chat history, worker route and executor gate are separated.
  const startAgentFromText = async (text: string): Promise<boolean> => {
    const intent = classifySovereignExecutorIntent(text);
    if (!effectiveRepoReady || !chatRepoSnapshot) {
      appendActionEvent(buildBlockedActionEvent({ route: 'agent-job', label: 'Sovereign Agent Start blockiert', detail: 'Kein vollständiger Builder-Repo-Snapshot vorhanden.', kind: 'blocked' }));
      setShowRepoSetup(true);
      appendChatLine({ role: 'assistant', text: 'Executor blockiert: Bitte zuerst den Repository-Snapshot über das Repo-Setup laden.' });
      return false;
    }
    if (intent !== 'code_execution' && intent !== 'draft_pr') {
      appendActionEvent(buildBlockedActionEvent({ route: 'agent-job', label: 'Sovereign Agent Start blockiert', detail: 'Kein bestätigter Code- oder Draft-PR-Ausführungsauftrag.', kind: 'blocked' }));
      appendChatLine({ role: 'assistant', text: 'Executor blockiert: Der aktuelle Text ist kein klarer Code- oder Draft-PR-Ausführungsauftrag.' });
      return false;
    }
    if (!githubWriteAllowed) {
      appendActionEvent({ kind: 'github_access_required', route: 'github-access', label: 'Executor braucht GitHub-Zugang', detail: 'Ausführungsauftrag erkannt, aber GitHub-Schreibzugang ist nicht validiert.', state: 'blocked' });
      setShowGitHubAccessOverride(true);
      appendChatLine({ role: 'assistant', text: 'Executor-Auftrag erkannt. Vor dem Start muss der GitHub-Schreibzugang im sicheren Feld validiert werden.' });
      return false;
    }

    const clean = collapseRepeatedAnalyzedMission(
      buildAnalyzedMission({
        wish: text,
        repoReady: true,
        repoReason: effectiveRepoReason,
      }),
    );
    emitMissionChange(clean);

    if (!onStartAgent) {
      appendActionEvent(buildBlockedActionEvent({
        route: 'agent-job',
        label: 'Sovereign Agent Start blockiert',
        detail: 'Kein Start-Callback für die Sovereign Agent Runtime verdrahtet.',
        kind: 'blocked',
      }));
      appendChatLine({
        role: 'assistant',
        text: 'Sovereign Agent Runtime kann nicht gestartet werden: Start-Callback ist nicht verdrahtet. Es wurde kein Job gestartet und keine Datei geändert.',
      });
      addLog('error', 'Sovereign Agent start blocked: missing onStartAgent callback', 'router');
      return false;
    }

    clearPatchEvidence();
    appendActionEvent({
      kind: 'agent_job_requested',
      route: 'agent-job',
      label: 'Sovereign Agent Job angefragt',
      detail: `Startanforderung für ${chatRepoSnapshot.repoUrl}#${chatRepoSnapshot.branch} wurde an die Runtime übergeben. Warte auf bestätigten Job-State.`,
      state: 'queued',
    });

    try {
      await onStartAgent(clean, {
        repoUrl: chatRepoSnapshot.repoUrl,
        branch: chatRepoSnapshot.branch,
        githubAccessToken: githubTokenRef.current || undefined,
      });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Sovereign Agent Start fehlgeschlagen.';
      appendActionEvent({
        kind: 'failed',
        route: 'agent-job',
        label: 'Sovereign Agent Start fehlgeschlagen',
        detail: message,
        state: 'failed',
      });
      appendChatLine({
        role: 'assistant',
        text: `Sovereign Agent Runtime konnte nicht gestartet werden.
Grund: ${message}
Es wurde kein Job gestartet und keine Datei geändert.`,
      });
      addLog('error', `Sovereign Agent start failed: ${message}`, 'router');
      return false;
    }
  };

  const publishConfirmedDraftPr = async (): Promise<void> => {
    if (!chatRepoSnapshot || !currentRepoScopeKey) {
      setShowRepoSetup(true);
      appendActionEvent(buildBlockedActionEvent({
        route: 'repo',
        label: 'Draft-PR-Übergabe blockiert',
        detail: 'Kein vollständiger Repository-Snapshot vorhanden.',
        kind: 'blocked',
      }));
      return;
    }

    const hasStagedChanges = stagedChanges.length > 0;
    const hasAgentEvidence = Boolean(
      scopedAgentJob?.jobId && (scopedAgentJob.changedFiles?.length ?? 0) > 0,
    );
    if (!hasStagedChanges && !hasAgentEvidence) {
      appendActionEvent(buildBlockedActionEvent({
        route: 'github-patch',
        label: 'Draft-PR-Übergabe blockiert',
        detail: 'Weder bestätigte staged Änderungen noch serverseitige Changed-File-Evidence vorhanden.',
        kind: 'patch_blocked',
      }));
      appendChatLine({
        role: 'assistant',
        text: 'Draft PR blockiert: Es gibt noch keine bestätigte Änderung mit Runtime-Evidence.',
      });
      return;
    }
    if (hasStagedChanges && !patchConfirmed) {
      setShowPatchDiffEvidence(true);
      appendActionEvent(buildBlockedActionEvent({
        route: 'github-patch',
        label: 'Patch-Bestätigung erforderlich',
        detail: 'Die lokale Diff-Vorschau muss vor der Backend-Übergabe ausdrücklich bestätigt werden.',
        kind: 'blocked',
      }));
      return;
    }

    appendActionEvent({
      kind: 'agent_job_requested',
      route: 'agent-job',
      label: 'Bestätigte Änderungen werden übergeben',
      detail: hasStagedChanges
        ? `${stagedChanges.length} bestätigte Dateiänderung(en) werden an den isolierten Runtime-Workspace übergeben.`
        : 'Der vorhandene belegte Agent-Job wird bis zur Draft-PR-Erstellung fortgeführt.',
      state: 'queued',
    });
    try {
      await onPublishDraftPr({
        repoUrl: chatRepoSnapshot.repoUrl,
        branch: chatRepoSnapshot.branch,
        mission: lastMissionRef.current.trim() || mission.trim() || 'Create a reviewed Draft PR.',
        changes: stagedChanges,
        confirmed: !hasStagedChanges || patchConfirmed,
        githubAccessToken: githubTokenRef.current || undefined,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendActionEvent({
        kind: 'failed',
        route: 'github-patch',
        label: 'Draft-PR-Übergabe fehlgeschlagen',
        detail: message,
        state: 'failed',
      });
      appendChatLine({
        role: 'assistant',
        text: `Draft-PR-Übergabe fehlgeschlagen. Grund: ${message}`,
      });
    }
  };

  const handleSubmit = async () => {
    const submittedText = wishText.trim();
    if (!submittedText || localRepoLoading || chatResponseBusy || isPublishing)
      return;
    setWishText("");
    void _processSubmit(submittedText);
  };

  // Retry submit with a specific message (used by WorkerBlockerCard and Banner)
  const retrySubmit = async (
    message: string,
    options: { readonly ignoreExistingWorkerBlocker?: boolean } = {},
  ) => {
    if (localRepoLoading || chatResponseBusy || isPublishing) return;
    setWishText("");
    void _processSubmit(message, options);
  };

  const _processSubmit = async (
    submittedText: string,
    options: { readonly ignoreExistingWorkerBlocker?: boolean } = {},
  ) => {
    const routingWorkerBlocker = options.ignoreExistingWorkerBlocker ? null : workerBlocker;
    // ── Issue #445: SecureInputGuard — block secrets before any storage or LLM path
    const securePolicy = evaluateInputPolicy(submittedText);
    if (securePolicy.shouldBlock) {
      // Show security card with "GitHub-Zugang öffnen" button — never store token or route to LLM
      const card = createSecurityCardDisplay(securePolicy);
      if (card) setSecurityCardPending(card);
      addLog("warn", `SecureInputGuard: ${securePolicy.kind ?? "secret"} detected and blocked`, "router");
      return;
    }

    // ── Issue #428: Slash command handling
    if (submittedText.startsWith("/")) {
      const parsedSlash = parseSlashCommand(submittedText, skillSlashCommands);
      if (!parsedSlash) {
        appendChatLine({
          role: "assistant",
          text: `Unbekannter Befehl. Verfügbare: ${[...SOVEREIGN_SLASH_COMMANDS, ...skillSlashCommands].map((c) => c.cmd).join(", ")}`,
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
        void publishConfirmedDraftPr();
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
        setChatHistory([]);
        setPalDecisions([]);
        setBudgetLedger(createBudgetLedger());
        triggerHaptic("light");
        appendChatLine({
          role: "assistant",
          text: "Chat-Verlauf gelöscht. Repository und Token bleiben erhalten.",
        });
        return;
      }
      if (command.action === "skills") {
        const active = installedSkills.filter((s) => s.is_active);
        if (active.length === 0) {
          appendChatLine({
            role: "assistant",
            text: "Keine Skills installiert. Nutze /scan-skills <owner/repo> um Skills aus einem Repo zu importieren.",
          });
        } else {
          appendChatLine({
            role: "assistant",
            text: [
              `**${active.length} installierte Skills:**`,
              ...active.map((s) => `• \`/${s.slug}\` — ${s.description}`),
              "",
              "Tipp: /scan-skills <owner/repo> für mehr Skills.",
            ].join("\n"),
          });
        }
        return;
      }
      if (command.action === "scan-skills") {
        setShowSkillScan(true);
        return;
      }
      if (command.action === "skill-run" && command.adapted_prompt) {
        triggerHaptic("light");
        appendChatLine({ role: "user", text: submittedText });
        appendChatLine({
          role: "assistant",
          text: `**${command.label}** wird ausgeführt…\n\n${command.adapted_prompt.slice(0, 600)}`,
        });
        return;
      }
    }

    // Haptic feedback for send (Issue #429)
    triggerHaptic("light");

    appendChatLine({ role: "user", text: submittedText });
    appendActionEvent(buildInputReceivedEvent(submittedText));

    // ── Issue #522 P2 Fix 2 & 3: Local routing BEFORE Integration Intent Draft Detection
    // Status, diagnostic, and retry intents must be handled locally FIRST.
    // They should NOT create an integration draft card.
    // Order matters: local routes > createIntegrationIntentDraft > capability router

    // P2 Fix 2: Status questions - answered locally from runtime state
    if (isLocalCompletionStatusQuestion(submittedText)) {
      const statusAnswer = buildLocalStatusAnswer({
        githubWriteAllowed,
        githubAccessState: effectiveGitHubAccessState,
        writeIntentBlockedByRepo: !effectiveRepoReady,
        agentRunning: scopedAgentJob?.status === 'running',
        draftPrUrl: scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl ?? null,
        hasPatch: Boolean(scopedAgentJob?.changedFiles?.length),
        patchPreviewReady,
        patchConfirmed,
        hasWorkerResponse: hasScopedWorkerResponse,
        workerBlocker: routingWorkerBlocker,
        buildWorkerBlockerAnswer: routingWorkerBlocker
          ? () =>
              buildWorkerBlockerAnswer({
                blocker: routingWorkerBlocker,
                repoReady: effectiveRepoReady,
                chatRepoSnapshot,
                agentReady,
              })
          : undefined,
        questionText: submittedText,
      });
      appendChatLine({ role: 'assistant', text: statusAnswer });
      setLastAnswerWasLocal(true);
      appendActionEvent(buildLocalRuntimeResultEvent({
        label: 'Status-Frage',
        detail: 'Lokale Antwort aus Runtime-State',
      }));
      addLog('info', 'Issue #522 P2 Fix 2: Status question handled locally - no draft created', 'router');
      return;
    }

    // Fix: "Warum?" follow-up after local status answer → answer locally, no worker call
    if (lastAnswerWasLocal && isFollowUpWhyQuestion(submittedText)) {
      const whyAnswer = patchPreviewReady
        ? "Die Patch-Vorschau wurde erzeugt, aber noch nicht angewendet. Es gibt noch keinen Commit und keinen Draft PR, weil die Vorschau erst geprüft und bestätigt werden muss."
        : !githubWriteAllowed
        ? "Weil sicherer GitHub-Zugang noch fehlt. Sobald der Zugang verifiziert ist, läuft der Auftrag automatisch weiter."
        : routingWorkerBlocker
        ? "Weil der Worker blockiert ist. Bitte den Fehler prüfen oder den Auftrag präzisieren."
        : "Weil noch kein Auftrag gestartet wurde oder der Auftrag blockiert ist. Bitte Auftrag neu starten.";
      appendChatLine({ role: 'assistant', text: whyAnswer });
      setLastAnswerWasLocal(true);
      appendActionEvent(buildLocalRuntimeResultEvent({
        label: 'Warum-Folgefrage',
        detail: 'Lokale Erklärung aus Runtime-State — kein Worker-Call',
      }));
      addLog('info', 'Fix: Follow-up why question answered locally - no worker call', 'router');
      return;
    }

    // P2 Fix 2: Worker retry intents - clear blocker and trigger real retry
    // Runtime-Truth: Retry must produce Action → Request → Response, not just UI reset
    if (isWorkerRetryIntent(submittedText) && routingWorkerBlocker) {
      // If user asks status question, answer locally first before retry
              if (submittedText && isLocalCompletionStatusQuestion(submittedText)) {
        const statusAnswer = buildLocalStatusAnswer({
          githubWriteAllowed,
          githubAccessState: effectiveGitHubAccessState,
          writeIntentBlockedByRepo: !effectiveRepoReady,
          agentRunning: scopedAgentJob?.status === 'running',
          draftPrUrl: scopedAgentJob?.draftPrUrl ?? null,
          hasPatch: Boolean(scopedAgentJob?.changedFiles?.length),
          patchPreviewReady,
          patchConfirmed,
          hasWorkerResponse: hasScopedWorkerResponse,
          workerBlocker: routingWorkerBlocker,
          buildWorkerBlockerAnswer: routingWorkerBlocker
            ? () =>
                buildWorkerBlockerAnswer({
                  blocker: routingWorkerBlocker,
                  repoReady: effectiveRepoReady,
                  chatRepoSnapshot,
                  agentReady,
                })
            : undefined,
        });
        appendChatLine({ role: 'assistant', text: statusAnswer });
        appendActionEvent(buildLocalRuntimeResultEvent({
          label: 'Status-Frage beantwortet',
          detail: 'Lokale Antwort aus Runtime-State',
        }));
        addLog('info', 'Retry + status question → local answer first', 'router');
        return;
      }
      if (lastWorkerRequestMessage) {
        // Real retry: re-submit the last request through the full pipeline
        setWorkerBlocker(null);
        appendChatLine({
          role: 'assistant',
          text: 'Worker-Blocker zurückgesetzt. Retry wird ausgeführt...',
        });
        appendActionEvent(buildLocalRuntimeResultEvent({
          label: 'Retry gestartet',
          detail: 'Worker-Blocker zurückgesetzt; letzter Request wird erneut ausgeführt',
        }));
        addLog('info', 'Issue #522 P2 Fix 2: Retry intent triggers real retry via retrySubmit', 'router');
        retrySubmit(lastWorkerRequestMessage, { ignoreExistingWorkerBlocker: true });
        return;
      } else {
        // Honest state: no prior request to retry
        appendChatLine({
          role: 'assistant',
          text: 'Worker-Blocker zurückgesetzt. Es gibt keinen vorherigen Request zum Wiederholen.',
        });
        appendActionEvent(buildLocalRuntimeResultEvent({
          label: 'Retry',
          detail: 'Worker-Blocker zurückgesetzt; kein vorheriger Request vorhanden',
        }));
        addLog('info', 'Issue #522 P2 Fix 2: Retry intent clears blocker - no prior request to retry', 'router');
        setWorkerBlocker(null);
        setChatResponseBusy(false);
        return;
      }
    }

    // P2 Fix 3: Diagnostic questions ("warum passiert nichts?") - answered locally
    const _executorIsActive = agentWorkSnapshot.state !== 'idle' ||
      (scopedAgentJob != null && scopedAgentJob.status !== 'idle');
    if (isExecutorStatusQuestion(submittedText) && (_executorIsActive || !routingWorkerBlocker)) {
      const statusAnswer = buildExecutorStatusAnswer({
        agentState: agentWorkSnapshot.state,
        agentStatus: scopedAgentJob?.status,
        changedFiles: scopedAgentJob?.changedFiles?.length ?? 0,
        draftPrUrl: scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl ?? null,
        blockerReason: agentWorkSnapshot.blockerReason,
      });
      appendChatLine({ role: 'assistant', text: statusAnswer });
      appendActionEvent(buildLocalRuntimeResultEvent({
        label: 'Diagnose-Frage',
        detail: 'Lokale Antwort aus Runtime-State',
      }));
      addLog('info', 'Issue #522 P2 Fix 3: Diagnostic question answered locally - no draft created', 'router');
      return;
    }

    // P2 Fix 3: Worker blocker diagnostic - answered locally, no draft
    if (
      routingWorkerBlocker &&
      !isWorkerRetryIntent(submittedText) &&
      !isSovereignAgentExecutionIntent(submittedText)
    ) {
      appendChatLine({
        role: "assistant",
        text: buildWorkerBlockerAnswer({
          blocker: routingWorkerBlocker,
          repoReady: effectiveRepoReady,
          chatRepoSnapshot,
          agentReady,
        }),
      });
      appendActionEvent(buildLocalRuntimeResultEvent({
        label: 'Worker-Diagnose',
        detail: routingWorkerBlocker.diagnostic.scope,
      }));
      addLog('info', `Issue #522 P2 Fix 3: Worker diagnostic answered locally - no draft created`, 'router');
      return;
    }

    // ── Issue #520: Integration Intent Draft Detection
    // Normal non-question inputs with a connected repo are treated as potential
    // integration/implementation requests. Show a draft card for confirmation.
    // BUT: Explicit executor commands and delegation intents bypass the draft card
    // to maintain backward compatibility with existing test expectations.
    // Fix: Safe-analysis presets are read-only and must never create an integration draft.
    const isSafeAnalysisPreset = submittedText.includes('Preset-Ausführungsmodus: safe_analysis');
    if (effectiveRepoReady &&
        !isSafeAnalysisPreset &&
        !isSovereignAgentExecutionIntent(submittedText) &&
        !isDelegationIntent(submittedText) &&
        !isDelegatedSovereignAgentExecutionIntent(submittedText, chatHistory)) {
      const repoFiles = chatRepoSnapshot?.filePaths?.map((path) => ({
        path,
        type: 'blob' as const,
        size: 0,
        sha: '',
      })) ?? [];

      const draft = createIntegrationIntentDraft(submittedText, repoFiles);
      if (draft) {
        appendActionEvent(buildDraftCreatedEvent(draft));
        setIntentDraftState({ status: 'pending', draft });
        addLog('info', `Integration intent draft created: ${draft.title}`, 'router');
        // Don't continue to capability router - wait for user confirmation
        return;
      }
    }

    // ── Issue #502: Sovereign Capability Router
    // Central routing decision using real runtime state.
    // BuilderContainer shows the decision; it does not create it.
    const capabilityRouterInput: CapabilityRouterInput = {
      text: submittedText,
      repoReady: effectiveRepoReady,
      githubAccessState: effectiveGitHubAccessState,
      agentReady: agentReady ?? false,
      directGitHubPatchReady: Boolean(githubWriteAllowed && chatRepoSnapshot && githubTokenRef.current),
      workspaceReady: false, // Workspace executor not yet integrated
      hasActiveWorkerBlocker: Boolean(routingWorkerBlocker),
      hasPackage: Boolean(scopedAgentJob?.changedFiles?.length),
      hasDraft: Boolean(scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl),
      hasWorkflowReport: Boolean(agentWorkSnapshot.commitSha),
    };
    const capabilityDecision = decideSovereignCapabilityRoute(capabilityRouterInput);

    // Emit action event for Sovereign Action Stream
    const routeActionEvent = buildCapabilityRouteActionEvent(capabilityDecision, agentWorkSnapshot.traceId, agentWorkSnapshot.events.length);
    // Cast to match SovereignActionEventInput (capability router uses its own route/kind types)
    appendActionEvent({
      kind: 'route_selected',
      route: routeActionEvent.route as 'repo' | 'free-chat' | 'code-llm' | 'worker' | 'sovereign-agent' | 'github-patch' | 'direct-github-patch' | 'github-access' | 'toolchain' | 'runtime',
      label: routeActionEvent.label,
      detail: routeActionEvent.detail,
      state: routeActionEvent.state,
    });

    // Log routing decision for telemetry
    addLog("info", `Capability Router: route=${capabilityDecision.route} allowed=${capabilityDecision.allowed} blocker=${capabilityDecision.blocker ?? 'none'}`, "router");

    // ── Issue #502: Blocked capability decisions stop legacy routing
    // BUT: Some cases must let legacy flow handle them:
    // - Worker retry (retry/nochmal) should clear blocker and retry
    // - Repo-first: no repo + no GitHub → tell user to load repo first
    // - Legacy fallback: unrecognized intents → Worker handles them
    if (!capabilityDecision.allowed) {
      // P1: Worker retry should bypass blocking - let legacy handle it
      if (isWorkerRetryIntent(submittedText) && routingWorkerBlocker) {
        setWorkerBlocker(null);
        addLog("info", "Capability Router: worker retry bypasses blocked decision", "router");
        // Continue to legacy retry flow below
      }
      // P1: Repo-first when no repo loaded - GitHub access needs a repo to validate against
      else if (capabilityDecision.blocker === 'github_access_missing' && !effectiveRepoReady) {
        appendChatLine({
          role: 'assistant',
          text: 'Route blockiert: GitHub-Zugang erfordert ein geladenes Repository.\nBitte zuerst GitHub-Repo-Link senden.',
        });
        addLog("warn", "Capability Router blocked: repo-first needed before GitHub access", "router");
        return;
      }
      // P2: Legacy Worker fallback for unrecognized intents
      else if (capabilityDecision.blocker === 'unsupported_intent') {
        addLog("info", "Capability Router: unsupported intent, falling through to legacy Worker", "router");
        // Continue to legacy Worker/executor flow below
      }
      // Default: Block with clear message
      else {
        const blockerMessage = capabilityDecision.blocker
          ? `Route blockiert: ${capabilityDecision.reason}`
          : `Auftrag nicht erlaubt: ${capabilityDecision.reason}`;
        appendChatLine({
          role: 'assistant',
          text: blockerMessage,
        });
        addLog("warn", `Capability Router blocked: ${capabilityDecision.route} - ${capabilityDecision.reason}`, "router");
        return;
      }
    }

    // ── Issue #502: Terminal decisions (like local-runtime-answer) stop routing
    // These are completed immediately - no Worker/executor calls needed.
    // BUT: local-runtime-answer must still produce an assistant chat line!
    if (capabilityDecision.isTerminal) {
      if (capabilityDecision.route === 'local-runtime-answer') {
        // Build and append the local status answer BEFORE returning
        // #500: Pass questionText to enable correct startup vs completion question differentiation
        const statusAnswer = buildLocalStatusAnswer({
          githubWriteAllowed,
          githubAccessState: effectiveGitHubAccessState,
          writeIntentBlockedByRepo: !effectiveRepoReady,
          agentRunning: scopedAgentJob?.status === 'running',
          draftPrUrl: scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl ?? null,
          hasPatch: Boolean(scopedAgentJob?.changedFiles?.length),
          patchPreviewReady,
          patchConfirmed,
          hasWorkerResponse: hasScopedWorkerResponse,
          workerBlocker: routingWorkerBlocker,
          buildWorkerBlockerAnswer: routingWorkerBlocker
            ? () =>
                buildWorkerBlockerAnswer({
                  blocker: routingWorkerBlocker,
                  repoReady: effectiveRepoReady,
                  chatRepoSnapshot,
                  agentReady,
                })
            : undefined,
          questionText: submittedText,
        });
        appendChatLine({ role: 'assistant', text: statusAnswer });
        setLastAnswerWasLocal(true);
        addLog('info', 'Capability Router: local-runtime-answer terminal decision completed', 'router');
        return;
      }
      addLog("info", `Capability Router: terminal decision (${String(capabilityDecision.route)}), routing complete`, "router");
      return;
    }

    const parsedRepo = parseDevChatGithubUrl(submittedText);
    if (parsedRepo) {
      setRepoLoading(true);
      setChatRepoError(null);
      appendActionEvent({
        kind: 'route_selected',
        route: 'repo',
        label: 'Route gewählt: repo',
        detail: 'Repo-Snapshot wird geladen.',
        state: 'running',
      });
      triggerHaptic("medium");
      const result = await fetchDevChatRepoTree(parsedRepo);
      setRepoLoading(false);
      if (result.ok && result.snapshot) {
        clearPatchEvidence();
        githubTokenRef.current = null;
        pendingWriteIntentRef.current = null;
        setValidatedGitHubTargetKey(null);
        setGitHubAccessState(createGitHubAccessSnapshot());
        setActionStream(createSovereignActionStreamState());
        setStatusLogs([]);
        setWorkerBlocker(null);
        setLastWorkerRequestMessage(null);
        setLastAnswerWasLocal(false);
        setChatRepo(result.snapshot);
        triggerHaptic("medium");
        const summary = summarizeDevChatRepoSnapshot(result.snapshot);
        appendActionEvent(buildRepoLoadedEvent(summary));
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
        setBudgetLedger((prev) => recordRouteUsage(prev, d.tier));
        addLog("info", `PAL → ${d.tier} · ${d.modelLabel}`, "sys");
        return;
      }
      const errorText = result.error ?? "Repo konnte nicht geladen werden.";
      setChatRepoError(errorText);
      appendActionEvent(buildBlockedActionEvent({
        route: 'repo',
        label: 'Repo-Laden blockiert',
        detail: errorText,
        kind: 'failed',
      }));
      triggerHaptic("heavy");
      appendChatLine({
        role: "assistant",
        text: `Repo-Laden blockiert: ${errorText}`,
      });
      return;
    }

    // ── Aufgabe 2: Local completion-status questions
    // NOTE: Handled earlier in the flow (see Issue #522 P2 Fix 2 above)
    // to ensure status questions don't create integration drafts.

    // ── Aufgabe 1: Write intents (README/file/patch/commit/push/PR language)
    // must never reach the Worker chat while GitHub write access is missing.
    // Instead of asking for a token in chat, show the GitHubAccessCard.
    // Explicit Sovereign Agent execution intents ("Sovereign Agent", "Draft PR" with
    // execution framing, ...) already have their own dedicated executor
    // readiness gate below (agentDisabled) and must not be short-circuited
    // here — this gate only covers write-language that would otherwise be
    // sent straight to the advisory Worker chat.
    if (isWriteIntent(submittedText) && !isSovereignAgentExecutionIntent(submittedText)) {
      if (!effectiveRepoReady) {
        appendActionEvent(buildBlockedActionEvent({
          route: 'github-access',
          label: 'Schreibauftrag blockiert',
          detail: 'Kein Repo geladen. GitHub-Repo-Link zuerst einfügen.',
          kind: 'access_required',
        }));
        appendChatLine({
          role: 'assistant',
          text: 'Schreibauftrag erkannt.\nEs ist noch kein Repo geladen — bitte zuerst einen GitHub-Repo-Link senden.',
        });
        addLog('warn', 'Write intent blocked: no repo loaded', 'router');
        return;
      }
      if (!githubWriteAllowed) {
        appendActionEvent({
          kind: 'github_access_required',
          route: 'github-access',
          label: 'GitHub-Schreibzugang erforderlich',
          detail: 'Schreibauftrag erkannt · Worker-Chat wird übersprungen.',
          state: 'blocked',
        });
        pendingWriteIntentRef.current = submittedText;
        setShowGitHubAccessOverride(true);
        appendChatLine({
          role: 'assistant',
          text: 'Schreibauftrag erkannt.\nFür Datei-/Repo-Änderungen wird sicherer GitHub-Schreibzugang benötigt.\nBitte GitHub-Zugang unten einrichten — der Auftrag wird nicht an den Worker-Chat gesendet.',
        });
        addLog('warn', 'Write intent blocked: GitHub write access missing', 'router');
        return;
      }
      appendActionEvent({
        kind: 'route_selected',
        route: 'github-patch',
        label: 'Patch/Draft-PR Route gestartet',
        detail: 'GitHub-Schreibzugang bereit · Schreibauftrag wird an Executor übergeben.',
        state: 'running',
      });
      if (agentDisabled) {
        // Use the Runtime Bridge to determine if Sovereign Internal Operator can handle this
        const executorBridgeDecision = decideSovereignExecutorBridgeRoute({
          text: submittedText,
          intent: classifySovereignExecutorIntent(submittedText),
          capabilities: buildSovereignToolCapabilityRegistry({
            repoReady: effectiveRepoReady,
            githubAccessState: effectiveGitHubAccessState,
            githubTokenPresent: Boolean(githubTokenRef.current),
            directPatchSupported: Boolean(chatRepoSnapshot),
            agentConfigured: sovereignAgentStartAvailable,
            workerAvailable: !routingWorkerBlocker,
            workspaceConfigured: false,
            draftPrSupported: true,
            activeExecutorStatus: scopedAgentIsRunning ? "running" : "idle",
          }),
          candidatePath: chatRepoSnapshot
            ? detectDirectPatchTarget(submittedText, chatRepoSnapshot.filePaths ?? []) ?? undefined
            : undefined,
        });

        // Always log the bridge decision
        appendActionEvent(executorBridgeDecision.event);

        if (executorBridgeDecision.bridgeRoute === 'sovereign_internal_operator' && executorBridgeDecision.state === 'allowed') {
          // Internal operator is available - show honest message, no fake patch
          appendChatLine({
            role: 'assistant',
            text: `GitHub-Zugang ist bereit.\nSovereignAgent Fallback ist nicht erforderlich.\n\nRoute: Sovereign Internal Operator\nErgebnis bleibt Draft-PR-only: erst Patch/Diff prüfen, dann Draft PR.\nKein Auto-Merge.`,
          });
          addLog('info', 'Write intent routed via Sovereign Internal Operator bridge', 'router');
          return;
        }

        if (executorBridgeDecision.bridgeRoute === 'executor_runtime' && executorBridgeDecision.state === 'allowed') {
          const tokenForDirectPatch = githubTokenRef.current;
          if (chatRepoSnapshot && tokenForDirectPatch) {
            const patchScopeKey = currentRepoScopeKey;
            clearPatchEvidence();
            const directPatchResult = await buildDirectPatchPlanWithContentLoad({
              repoContext: {
                owner: chatRepoSnapshot.owner,
                name: chatRepoSnapshot.repo,
                branch: chatRepoSnapshot.branch,
                filePaths: chatRepoSnapshot.filePaths ?? [],
              },
              instruction: submittedText,
              githubAccessReady: true,
              token: tokenForDirectPatch,
              fetcher: globalThis.fetch,
            });

            if (!isCurrentRepoScope(patchScopeKey)) {
              appendActionEvent(buildBlockedActionEvent({
                route: 'direct-github-patch',
                label: 'Patch-Ergebnis verworfen',
                detail: 'Das Repo oder der Branch hat sich während der Patch-Erzeugung geändert.',
                kind: 'blocked',
              }));
              return;
            }

            if ('result' in directPatchResult && directPatchResult.result.ok) {
              const res = directPatchResult.result;
              appendActionEvent({
                kind: 'route_selected',
                route: 'direct-github-patch',
                label: 'Direct GitHub Patch Route gewählt',
                detail: `Zieldatei: ${res.targetPath}`,
                state: 'running',
              });
              
              // Diff-Preview in Action Stream einspeisen
              appendActionEvent({
                kind: 'done',
                route: 'github-patch',
                label: 'Patch-Vorschau generiert',
                detail: res.patchSummary,
                state: 'done',
              });

              appendChatLine({
                role: 'assistant',
                text: `Direct GitHub Patch Route verfügbar für ${res.targetPath}.

Patch-Vorschlag:
${res.patchSummary}

Nächste Aktion: ${res.nextAction === 'preview_diff' ? 'Diff-Vorschau prüfen' : 'Draft PR erstellen'}`,
              });
              
              stageGeneratedPatch({
                path: res.targetPath,
                proposedContent: res.proposedContent,
                baseContent: res.baseContent,
                summary: res.patchSummary,
              });
              setLastAnswerWasLocal(true);
              addLog('info', 'Write intent routed through Direct GitHub Patch Route with diff preview', 'router');
              return;
            }

            if ('capability' in directPatchResult && !directPatchResult.capability.available) {
              appendActionEvent(buildBlockedActionEvent({
                route: 'github-patch',
                label: 'Direct Patch nicht verfügbar',
                detail: `Route erlaubt; Direct Patch noch nicht verfügbar: ${directPatchResult.capability.reason}`,
                kind: 'patch_blocked',
              }));
              appendChatLine({
                role: 'assistant',
                text: `Schreibauftrag erkannt.
${executorBridgeDecision.reason}

Route ist erlaubt, aber Direct Patch konnte noch keinen Patchplan erzeugen.
Grund: ${directPatchResult.capability.reason}

Es wurde noch keine Datei geändert. Nächste Aktion: Zielpfad präzisieren oder Executor verbinden.`,
              });
              addLog('info', 'Write intent bridge allowed; direct patch not available: ' + directPatchResult.capability.reason, 'router');
              return;
            }

            // Runtime-Truth: Handle Direct Patch failure (result.ok === false)
            if ('result' in directPatchResult && !directPatchResult.result.ok) {
              const failureResult = directPatchResult.result;
              const errorMessage = 'reason' in failureResult ? failureResult.reason : 'Direct Patch fehlgeschlagen';
              appendActionEvent({
                kind: 'failed',
                route: 'direct-github-patch',
                label: 'Direct Patch fehlgeschlagen',
                detail: errorMessage,
                state: 'failed',
              });
              appendChatLine({
                role: 'assistant',
                text: `Direct GitHub Patch fehlgeschlagen: ${errorMessage}`,
              });
              addLog('error', 'Direct patch failed: ' + errorMessage, 'router');
              return;
            }
          }

          appendActionEvent({
            kind: 'patch_blocked',
            route: 'github-patch',
            label: 'Patch/Draft-PR Route geprüft — wartet auf Zielpfad',
            detail: 'Route erlaubt; kein Patch/Diff erzeugt — Zielpfad oder Executor erforderlich.',
            state: 'blocked',
          });
          appendChatLine({
            role: 'assistant',
            text: `Schreibauftrag erkannt.
${executorBridgeDecision.reason}

Route ist erlaubt, aber es wurde noch kein Patch/Diff erzeugt.
Nächste Aktion: Zielpfad nennen oder Executor verbinden.
Es wurde noch keine Datei geändert.`,
          });
          addLog('info', 'Write intent bridge allowed without patch result: ' + executorBridgeDecision.reason, 'router');
          return;
        }

        // Bridge blocked - show clear blocker message with reason
        appendChatLine({
          role: 'assistant',
          text: `Schreibauftrag kann nicht ausgeführt werden.\n\nGrund: ${executorBridgeDecision.reason}\n\nEs wurde noch keine Datei geändert.`,
        });
        addLog('warn', 'Write intent blocked by bridge: ' + executorBridgeDecision.reason, 'router');
        return;
      }
      addLog('info', 'Write intent routed to patch/draft-pr executor after GitHub access gate', 'router');
      const agentStartRequested = await startAgentFromText(submittedText);
      if (agentStartRequested) {
        appendChatLine({
          role: 'assistant',
          text: 'GitHub-Zugang ist bereit. Schreibauftrag wurde an die Sovereign Agent Runtime übergeben. Warte auf bestätigten Job-State. Ergebnis bleibt Draft PR, kein Auto-Merge.',
        });
      }
      return;
    }

    // ── #500/#501 Alternative write route: answer locally without Sovereign Agent lock-in.
    // NOTE: Status, diagnostic, and retry intents are handled earlier in the flow
    // (see Issue #522 P2 Fix 2 & 3 above) to ensure they don't create integration drafts.
    // These questions must be answered from runtime state, not forwarded to Sovereign Agent.
    if (isAlternativeWriteRouteIntent(submittedText)) {
      // #501: Calculate directPatchAvailable honestly
      // Direct Patch is available in principle (route exists) but requires:
      // - githubWriteAllowed (validated token)
      // - chatRepoSnapshot (repo loaded)
      // - target file exists in repo
      // - token in memory for content loading
      const targetPath = chatRepoSnapshot 
        ? detectDirectPatchTarget(submittedText, chatRepoSnapshot.filePaths ?? [])
        : null;
      const tokenAvailable = Boolean(githubTokenRef.current);
      const directPatchAvailable = Boolean(
        githubWriteAllowed && 
        chatRepoSnapshot && 
        targetPath !== null &&
        tokenAvailable
      );
      const altRouteAnswer = buildAlternativeRouteStatusAnswer({
        githubAccessReady: githubWriteAllowed,
        githubAccessState: effectiveGitHubAccessState,
        agentReady: agentReady ?? false,
        directPatchAvailable,
      });
      appendChatLine({ role: 'assistant', text: altRouteAnswer });
      addLog('info', 'Alternative route question answered locally · githubAccessReady=' + githubWriteAllowed + ' · tokenAvailable=' + tokenAvailable + ' · target=' + targetPath, 'router');
      return;
    }

    // ── #458 + Delegation: Execution intent routing — BEFORE credit guard.
    // Sovereign Agent execution does not go through the Worker Chat (gemini-2.0-flash) path;
    // charging LLM credits for an executor handoff is incorrect.
    const isExecutionIntent = isSovereignAgentExecutionIntent(submittedText);
    const isDelegatedExecution = isDelegatedSovereignAgentExecutionIntent(submittedText, chatHistory);

    if (isExecutionIntent || isDelegatedExecution) {
      if (!agentDisabled) {
        // Immediately reflect intent in AgentWorkTimeline — truth from runtime, not from polling.
        const _repo = chatRepoSnapshot
          ? `${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo}`
          : 'unknown/repo';
        appendActionEvent({
          kind: 'intent_detected',
          route: 'runtime',
          label: 'Ausführungsabsicht erkannt',
          detail: `Repo: ${_repo}`,
          state: 'done',
        });
        setAgentWorkSnapshot((prev) =>
          prev.state === 'idle'
            ? transitionIntentDetected(prev, _repo, chatRepoSnapshot?.branch ?? 'main')
            : prev,
        );
        addLog('info', `Execution intent · type=${isDelegatedExecution ? 'delegated' : 'explicit'} · repo=${_repo}`, 'router');
        const agentStartRequested = await startAgentFromText(submittedText);
        if (agentStartRequested) {
          appendChatLine({
            role: "assistant",
            text: "Ausführungsauftrag erkannt.\nRoute gewählt: Sovereign Agent Runtime.\nJob-Start wurde angefragt; bestätigter Job-State kommt aus der Runtime. Ergebnis bleibt Draft PR, kein Auto-Merge.",
          });
        }
        return;
      }
      // agentDisabled === true: Use Runtime Bridge to check Sovereign Internal Operator availability
      const executorBridgeDecision = decideSovereignExecutorBridgeRoute({
        text: submittedText,
        intent: classifySovereignExecutorIntent(submittedText),
        capabilities: buildSovereignToolCapabilityRegistry({
          repoReady: effectiveRepoReady,
          githubAccessState: effectiveGitHubAccessState,
          githubTokenPresent: Boolean(githubTokenRef.current),
          directPatchSupported: Boolean(chatRepoSnapshot),
          agentConfigured: sovereignAgentStartAvailable,
          workerAvailable: !routingWorkerBlocker,
          workspaceConfigured: false,
          draftPrSupported: true,
          activeExecutorStatus: scopedAgentIsRunning ? "running" : "idle",
        }),
        candidatePath: chatRepoSnapshot
          ? detectDirectPatchTarget(submittedText, chatRepoSnapshot.filePaths ?? []) ?? undefined
          : undefined,
      });

      // Always log the bridge decision
      appendActionEvent(executorBridgeDecision.event);

      if (executorBridgeDecision.bridgeRoute === 'sovereign_internal_operator' && executorBridgeDecision.state === 'allowed') {
        // Internal operator is available - runtime handoff decision, no fake patch claimed
        appendChatLine({
          role: "assistant",
          text: `Ausführungsauftrag erkannt.\nRoute gewählt: Sovereign Internal Operator (${executorBridgeDecision.internalOperatorRoute ?? 'intern'}).\n\nSovereignAgent Runtime bleibt optional, wenn Direct Patch den Auftrag belegen kann.\nDer Auftrag bleibt Draft-PR-only: erst Patch/Diff prüfen, dann Draft PR.\nKein Auto-Merge.`,
        });
        addLog('info', `Execution intent via Sovereign Internal Operator bridge · intent=${isDelegatedExecution ? 'delegated' : 'explicit'}`, 'router');
        return;
      }

      if (executorBridgeDecision.bridgeRoute === 'executor_runtime' && executorBridgeDecision.state === 'allowed') {
        appendActionEvent({
          kind: 'patch_blocked',
          route: 'github-patch',
          label: 'Patch/Draft-PR Route geprüft — wartet auf Zielpfad',
          detail: executorBridgeDecision.reason,
          state: 'blocked',
        });
        appendChatLine({
          role: "assistant",
          text: `Ausführungsauftrag erkannt.
Route gewählt: Patch/Draft-PR Runtime.

${executorBridgeDecision.reason}

Sovereign Agent Runtime ist nicht Pflicht, solange Direct Patch den Auftrag belegen kann. Es wurde noch keine Datei geändert; nächster Schritt ist Patch/Diff erzeugen oder Executor verbinden.`,
        });
        addLog('info', `Execution intent allowed by bridge without mandatory Sovereign Agent · intent=${isDelegatedExecution ? 'delegated' : 'explicit'}`, 'router');
        return;
      }

      // Bridge blocked - show clear blocker with honest reason
      const blockerReason = executorBridgeDecision.reason;
      appendChatLine({
        role: "assistant",
        text: `Ausführungsauftrag kann nicht ausgeführt werden.\n\nGrund: ${blockerReason}`,
      });
      addLog("warn", `Execution blocked by bridge: agentDisabled=true, intent=${isDelegatedExecution ? 'delegated' : 'explicit'} · ${blockerReason}`, "router");
      return;
    }

    if (!isSafeAnalysisPreset && isCodeGenerationIntent(submittedText)) {
      appendActionEvent(buildRouteSelectionEvent({
        route: 'code-llm',
        reason: 'Code-Auftrag erkannt; Code-LLM/Worker erzeugt Antwort oder Patchvorschlag.',
        state: 'running',
      }));
    }

    // ── Aufgabe 6: Write-intent result gate. GitHub write access is verified
    // above, but a mere Worker text response still must not be treated as
    // "done" — the result gate (sovereignActionStreamRuntime) requires a
    // patch/diff, Draft PR, or an explicit blocked/access_required state
    // before the write intent can be considered resolved.
    if (!isSafeAnalysisPreset && isWriteIntent(submittedText) && !isCodeGenerationIntent(submittedText)) {
      appendActionEvent(buildRouteSelectionEvent({
        route: 'code-llm',
        reason: 'Schreibauftrag erkannt; Ergebnis gilt erst mit Patch/Diff, Draft PR oder explizitem Blocker als abgeschlossen.',
        state: 'running',
      }));
    }

    // ARE is evaluated before credit deduction and before any online call.
    // Reference knowledge includes uploaded PDFs; experience remains a separate,
    // evidence-accepted memory. No local synthesis capability is claimed yet.
    let areInferenceResult: AreInferenceResult | null = null;
    let referenceKnowledgeContext = '';
    let experiencePatternContext = '';
    if (authUser) {
      try {
        const workerHealthForInference = await fetchDevChatWorkerHealth();
        areInferenceResult = await evaluateAreInference({
          prompt: submittedText,
          repository: buildAreRepositoryState({
            owner: chatRepoSnapshot?.owner,
            repo: chatRepoSnapshot?.repo,
            branch: chatRepoSnapshot?.branch,
            repositoryRevision: chatRepoSnapshot?.treeSha,
            files: chatRepoSnapshot?.files ?? [],
          }),
          onlineAvailable: workerHealthForInference.ok,
          limit: 5,
        });
        const transition = emitAreStateTransition(arePreviousStateRef.current, areInferenceResult);
        arePreviousStateRef.current = {
          stateHash: areInferenceResult.stateHash,
          state: areInferenceResult.state,
        };
        if (transition.changed) {
          addLog('info', `ARE-State geändert: ${transition.changeKinds.join(', ')} · ${transition.currentStateHash.slice(0, 12)}`, 'pattern');
        }
        referenceKnowledgeContext = areInferenceResult.knowledgeContext;
        experiencePatternContext = areInferenceResult.experienceContext;

        for (const [memoryKind, blocker] of Object.entries(areInferenceResult.blockers)) {
          if (!blocker) continue;
          appendActionEvent(buildBlockedActionEvent({
            route: 'runtime',
            label: `ARE ${memoryKind}-Evidence unvollständig`,
            detail: blocker,
            kind: 'blocked',
          }));
        }

        if (areInferenceResult.selectedKnowledgeIds.length > 0) {
          appendActionEvent({
            kind: 'context_collected',
            route: 'runtime',
            label: 'ARE Referenzwissen gefunden',
            detail: `${areInferenceResult.selectedKnowledgeIds.length} semantisch passende Knowledge-/PDF-Blöcke · State ${areInferenceResult.stateHash.slice(0, 12)}.`,
            state: 'done',
          });
        }
        if (areInferenceResult.selectedPatternIds.length > 0) {
          appendActionEvent({
            kind: 'context_collected',
            route: 'runtime',
            label: 'ARE Erfahrung gefunden',
            detail: `${areInferenceResult.selectedPatternIds.length} evidence-geprüfte Muster · Adapter ${areInferenceResult.adapter}.`,
            state: 'done',
          });
        }
        if (areInferenceResult.decision === 'local') {
          appendActionEvent(buildBlockedActionEvent({
            route: 'runtime',
            label: 'ARE-Lokalroute noch nicht ausführbar',
            detail: 'Das Backend meldet lokale Synthese, aber der Builder besitzt noch keinen bestätigten lokalen Ausführungsadapter.',
            kind: 'blocked',
          }));
          appendChatLine({
            role: 'assistant',
            text: 'ARE hat eine lokale Route gewählt, aber im Builder ist noch kein bestätigter lokaler Code-Ausführungsadapter verbunden. Es wurde kein Credit abgezogen und kein Online-Call gestartet.',
          });
          return;
        }
        if (areInferenceResult.decision === 'blocked') {
          appendActionEvent(buildBlockedActionEvent({
            route: 'runtime',
            label: 'ARE-Inferenz blockiert',
            detail: areInferenceResult.reasons.join(' · '),
            kind: 'blocked',
          }));
          appendChatLine({
            role: 'assistant',
            text: 'ARE-Inferenz blockiert: Die App ist offline und es ist noch kein belastbarer lokaler Code-Synthese-Adapter installiert. PDF- und Erfahrungswissen bleiben erhalten; es wurde kein Credit abgezogen und kein Online-Call gestartet.',
          });
          return;
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        appendActionEvent(buildBlockedActionEvent({
          route: 'runtime',
          label: 'ARE-Inferenz fehlgeschlagen',
          detail: message,
          kind: 'failed',
        }));
        appendChatLine({
          role: 'assistant',
          text: `ARE-Inferenz ist nicht verfügbar. Der Auftrag wurde vor Credit-Abzug und Online-Call gestoppt.\nGrund: ${message}`,
        });
        addLog('warn', `ARE-Inferenz nicht verfügbar: ${message}`, 'pattern');
        return;
      }
    } else {
      appendActionEvent(buildBlockedActionEvent({
        route: 'runtime',
        label: 'ARE-Erinnerung übersprungen',
        detail: 'Kein bestätigter Benutzer-Session-State; persönliche Knowledge-/Experience-Suche wurde nicht ausgeführt.',
        kind: 'blocked',
      }));
    }

    const quarantineOnlineAnswer = async (responseText: string, modelId: string) => {
      if (!areInferenceResult || areInferenceResult.decision !== 'online_required') return;
      try {
        const quarantine = await quarantineAreResponse({
        prompt: submittedText,
        response: responseText,
        stateHash: areInferenceResult.stateHash,
        adapter: areInferenceResult.adapter,
        modelId,
        metadata: {
          repository: currentRepositoryTargetKey,
          knowledgeIds: areInferenceResult.selectedKnowledgeIds,
          patternIds: areInferenceResult.selectedPatternIds,
        },
      });
        appendActionEvent({
          kind: 'context_collected',
          route: 'runtime',
          label: quarantine.duplicate ? 'Online-Antwort bereits in Quarantäne' : 'Online-Antwort quarantänisiert',
          detail: quarantine.learningState === 'pending_evidence'
            ? 'DB bestätigt: Kandidat wartet auf akzeptierte Runtime-Evidence und ist noch kein gelerntes Muster.'
            : `DB bestätigt bestehenden Zustand: ${quarantine.candidate.status}.`,
          state: 'done',
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        appendActionEvent(buildBlockedActionEvent({
          route: 'runtime',
          label: 'ARE-Quarantäne fehlgeschlagen',
          detail: message,
          kind: 'failed',
        }));
        addLog('warn', `ARE-Quarantäne nicht verfügbar: ${message}`, 'pattern');
      }
    };

    // ── #458 Credit guard — route first, then charge the exact selected model.
    const d = palRoute(
      submittedText,
      chatHistory.length + 1,
      chatRepoSnapshot?.fileCount ?? 0,
      palDecisions,
    );
    const _estimatedTokens = Math.ceil(submittedText.length / 3 * 1.3);
    const _canProceed = await chargeCredits(d.modelId, _estimatedTokens);
    if (!_canProceed) {
      addLog("warn", `Credits nicht ausreichend für ${d.modelId} — Paywall geöffnet`, "billing");
      return;
    }

    setPalDecisions((prev) => [...prev.slice(-99), d]);
    setBudgetLedger((prev) => recordRouteUsage(prev, d.tier));
    addLog("info", `PAL → ${d.tier} · ${d.modelLabel}`, "sys");
    appendActionEvent(buildWorkerRequestEvent(d.modelLabel));

    setLastAnswerWasLocal(false);
    setPatchConfirmed(false);
    setLastWorkerRequestMessage(submittedText);
    setChatResponseBusy(true);
    setStreamingText("");

    // ── Issue #468: Toolchain Auto-Calling — read-only Auto-Calls vor Worker-Messages
    const toolchainAutoResult = await buildToolchainAutoContext({
      submittedText,
      repoSnapshot: chatRepoSnapshot,
      fetchImpl: globalThis.fetch,
    });
    const autoToolchainContext = toolchainAutoResult.context || "";
    if (autoToolchainContext.trim()) {
      appendActionEvent({
        kind: 'context_collected',
        route: 'toolchain',
        label: 'Toolchain-Kontext gesammelt',
        detail: 'Read-only Auto-Context bereit.',
        state: 'done',
      });
    }

    const workerMessages = buildWorkerMessages({
      submittedText,
      chatHistory,
      repoReady: effectiveRepoReady,
      repoReason: effectiveRepoReason,
      chatRepoSnapshot,
      toolchainContext: [
        getToolContext(),
        getActiveSkillContext(),
        autoToolchainContext,
        referenceKnowledgeContext,
        experiencePatternContext,
      ].filter(Boolean).join('\n\n'),
    });

    // Stream chunks directly into UI for immediate feedback
    let fullText = "";
    let streamError: {
      status?: number;
      statusText?: string;
      bodySnippet?: string;
    } | null = null;
    let streamDiagnostic: DevChatWorkerDiagnostic | null = null;
    let streamFallbackMetadata: { fallbackUsed: boolean; preferredModel: string; actualModel: string; fallbackReason?: string } | null = null;
    
    try {
      for await (const chunk of streamDevChatWorkerReply(
        {
          model: d.modelId,
          messages: workerMessages,
        },
        (metadata) => {
          streamFallbackMetadata = metadata;
        }
      )) {
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

    if (fullText && !streamError && !streamDiagnostic) {
      setWorkerBlocker(null);
      appendActionEvent(buildWorkerResponseEvent());
      // ── Issue #445: chatClaimGuard — verify response against runtime snapshot before display
      const claimCheck = checkChatClaim(fullText, agentWorkSnapshot);
      let textToAppend =
        claimCheck.allowed || !claimCheck.honestFallback
          ? fullText
          : `${fullText}\n\n_[Sovereign: ${claimCheck.honestFallback}]_`;
      
      if (streamFallbackMetadata?.fallbackUsed) {
        textToAppend += `\n\n_Hinweis: ${streamFallbackMetadata.preferredModel} war nicht erreichbar, Antwort kam von ${streamFallbackMetadata.actualModel}._`;
      }

      if (!claimCheck.allowed && claimCheck.violations.length > 0) {
        addLog("warn", `chatClaimGuard: ${claimCheck.violations.join(", ")}`, "router");
      }
      appendChatLine({ role: "assistant", text: textToAppend });
      await quarantineOnlineAnswer(fullText, streamFallbackMetadata?.actualModel ?? d.modelId);
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
      appendActionEvent(buildWorkerResponseEvent());

      const claimCheck = checkChatClaim(fallback.content, agentWorkSnapshot);
      let textToAppend =
        claimCheck.allowed || !claimCheck.honestFallback
          ? fallback.content
          : `${fallback.content}\n\n_[Sovereign: ${claimCheck.honestFallback}]_`;

      if (!claimCheck.allowed && claimCheck.violations.length > 0) {
        addLog("warn", `chatClaimGuard: ${claimCheck.violations.join(", ")}`, "router");
      }

      if (fallback.fallbackUsed) {
        textToAppend += `\n\n_Hinweis: ${fallback.preferredModel} war nicht erreichbar, Antwort kam von ${fallback.actualModel}._`;
      }

      appendChatLine({ role: "assistant", text: textToAppend });
      await quarantineOnlineAnswer(fallback.content, fallback.actualModel ?? d.modelId);
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
    appendActionEvent(buildBlockedActionEvent({
      route: 'worker',
      label: 'Worker blockiert',
      detail: diagnostic.nextAction || blocker.message,
      kind: 'failed',
    }));
    setWorkerBlocker(blocker);
    appendChatLine({
      role: "assistant",
      text: buildWorkerBlockerAnswer({
        blocker,
        repoReady: effectiveRepoReady,
        chatRepoSnapshot,
        agentReady,
      }),
    });
    addLog(
      "error",
      `Worker blocked · ${diagnostic.scope}${diagnostic.status ? ` · HTTP ${diagnostic.status}` : ""}`,
      "router",
    );
  };

  const handleRepoSetupLoad = () => {
    const clean = repoSetupUrl.trim();
    if (!clean) {
      setRepoSetupError('GitHub Repository URL fehlt.');
      return;
    }
    if (!parseDevChatGithubUrl(clean)) {
      const reason = 'Ungültige GitHub Repository URL. Erwartet wird https://github.com/owner/repository.';
      setRepoSetupError(reason);
      appendActionEvent(buildBlockedActionEvent({ route: 'repo', label: 'Repo-Setup blockiert', detail: reason, kind: 'blocked' }));
      return;
    }
    setRepoSetupError(null);
    void _processSubmit(clean);
  };

  const handlePresetActionSelect = (actionId: SovereignPresetActionId) => {
    const action = getSovereignPresetAction(actionId);
    const submitted = buildSovereignPresetActionSubmission(action, {
      repoReady: effectiveRepoReady,
      repoFullName: chatRepoSnapshot ? `${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo}` : null,
      branch: chatRepoSnapshot?.branch ?? null,
      githubWriteReady: githubWriteAllowed,
      agentReady: agentReady ?? false,
    });
    const gate = evaluateSovereignPresetActionGate(action, {
      repoReady: effectiveRepoReady,
      githubWriteReady: githubWriteAllowed,
      agentReady: agentReady ?? false,
    });

    if (!gate.canStart) {
      if (action.requiresRepo && !effectiveRepoReady) {
        setRepoSetupError(null);
        setShowRepoSetup(true);
        appendActionEvent(buildBlockedActionEvent({
          route: 'repo',
          label: `Preset wartet auf Repo: ${action.shortLabel}`,
          detail: `${gate.reason} ${gate.nextAction}`,
          kind: 'blocked',
        }));
        appendChatLine({
          role: 'assistant',
          text: `${action.icon} ${action.label}
Status: ${gate.reason}
Das echte Repo-Setup wurde geöffnet.`,
        });
        return;
      }
      if (action.requiresGithubWrite && effectiveRepoReady && !githubWriteAllowed) {
        pendingWriteIntentRef.current = submitted;
        setShowGitHubAccessOverride(true);
        appendActionEvent({
          kind: 'github_access_required',
          route: 'github-access',
          label: `GitHub-Schreibzugang erforderlich: ${action.shortLabel}`,
          detail: 'Preset-Auftrag wurde vorgemerkt; Worker-Chat wird übersprungen.',
          state: 'blocked',
        });
        appendChatLine({
          role: 'assistant',
          text: [
            `${action.icon} ${action.label}`,
            `Status: ${gate.reason}`,
            'Ich habe diesen Auftrag vorgemerkt.',
            'Bitte GitHub-Zugang im sicheren Feld eingeben — danach läuft dieser Auftrag automatisch weiter.',
          ].join('\n'),
        });
        addLog('warn', `Preset write action blocked: GitHub access gate opened for ${action.id}`, 'router');
        return;
      }

      appendActionEvent(buildBlockedActionEvent({
        route: action.requiresRepo ? 'repo' : 'runtime',
        label: `Preset blockiert: ${action.shortLabel}`,
        detail: `${gate.reason} ${gate.nextAction}`,
        kind: action.requiresGithubWrite ? 'access_required' : 'blocked',
      }));
      appendChatLine({
        role: 'assistant',
        text: [
          `${action.icon} ${action.label}`,
          `Status: ${gate.reason}`,
          `Nächste Aktion: ${gate.nextAction}`,
        ].join('\n'),
      });
      return;
    }

    if (action.risk === 'safe_analysis') {
      appendActionEvent(buildRouteSelectionEvent({
        route: action.route === 'runtime_review' ? 'runtime' : 'worker',
        reason: `${action.label} ist eine sichere Analyse-Preset-Aktion; kein GitHub-Schreibzugang und kein Executor-Start.`,
        state: 'running',
      }));
      addLog('info', `Safe preset analysis routed without executor: ${action.id}`, 'router');
    }

    setWishText('');
    void _processSubmit(submitted);
  };

  const handleCompactToolSelect = (toolId: ToolId) => {
    const decision = decideSovereignCompactShortcutExecution({
      id: toolId,
      repoSnapshotReady: effectiveRepoReady,
      repoFileCount: effectiveRepoReady && chatRepoSnapshot
        ? chatRepoSnapshot.files.filter((entry) => entry.type === 'blob').length
        : 0,
      changedFiles: scopedAgentJob?.changedFiles ?? [],
      patchDiffAvailable: Boolean(patchDiffReport),
      githubAccessState: effectiveGitHubAccessState,
      executorAvailable: sovereignAgentStartAvailable,
      executorActive: scopedAgentIsRunning,
      executorIntent,
      runtimeEventCount: runtimeEvidenceLog.length,
    });
    if (decision.event) appendActionEvent(decision.event);

    if (decision.surface === 'repo-setup') {
      setRepoSetupError(null);
      setShowRepoSetup(true);
      return;
    }
    if (decision.surface === 'repo-explorer' || decision.surface === 'files-explorer') {
      setShowRepoExplorer(true);
      return;
    }
    if (decision.surface === 'changed-files') {
      setOpenWorkbenchSlot('files');
      return;
    }
    if (decision.surface === 'patch-diff' && patchDiffReport) {
      setShowPatchDiffEvidence(true);
      return;
    }
    if (decision.surface === 'github-access') {
      setShowGitHubAccessOverride(true);
      appendChatLine({ role: 'assistant', text: `${decision.reason} ${decision.nextAction}` });
      return;
    }
    if (decision.surface === 'github-status') {
      appendChatLine({
        role: 'assistant',
        text: effectiveGitHubAccessState === 'ready'
          ? 'GitHub-Zugang ist validiert. Secret-Werte werden weder angezeigt noch im Chat gespeichert.'
          : 'GitHub-Zugang wird bereits geprüft. Es wurde keine zweite Validierung gestartet.',
      });
      return;
    }
    if (decision.surface === 'executor-status') {
      appendChatLine({
        role: 'assistant',
        text: `${decision.reason} ${decision.nextAction}`,
      });
      return;
    }
    if (decision.surface === 'executor-request') {
      void startAgentFromText(wishText.trim());
      return;
    }
    if (decision.surface === 'runtime-logs') {
      setShowRuntimeEvidenceLogs(true);
      return;
    }
    if (decision.surface === 'blocked') {
      appendChatLine({ role: 'assistant', text: `${decision.reason} Nächste Aktion: ${decision.nextAction}` });
    }
  };

  const sideMenuShareDecision = useMemo(
    () => decideSovereignSideMenuShare(chatHistory.length),
    [chatHistory.length],
  );
  const sideMenuDraftPrDecision = useMemo(
    () => decideSovereignSideMenuDraftPr({
      repoReady: effectiveRepoReady,
      hasChangeEvidence: Boolean(
        (patchConfirmed && stagedChanges.length > 0)
        || (scopedAgentJob?.changedFiles?.length ?? 0) > 0,
      ),
      githubWriteReady: githubWriteAllowed,
      isPublishing,
      draftPrUrl: scopedAgentJob?.draftPrUrl ?? scopedPublishedPrUrl,
    }),
    [
      effectiveRepoReady,
      githubWriteAllowed,
      isPublishing,
      patchConfirmed,
      stagedChanges.length,
      scopedAgentJob?.changedFiles?.length,
      scopedAgentJob?.draftPrUrl,
      scopedPublishedPrUrl,
    ],
  );

  const handleSideMenuCancelAgent = () => {
    if (!onCancelAgent || !scopedAgentIsRunning) return;

    appendActionEvent({
      kind: 'route_selected',
      route: 'agent-job',
      label: 'Agent-Abbruch angefragt',
      detail: 'Der Abbruch-Callback wurde aufgerufen. Der Agent gilt erst nach bestätigtem Backend-State als gestoppt.',
      state: 'queued',
    });
    try {
      onCancelAgent();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendActionEvent({
        kind: 'failed',
        route: 'agent-job',
        label: 'Agent-Abbruch konnte nicht angefragt werden',
        detail: message,
        state: 'failed',
      });
      appendChatLine({
        role: 'assistant',
        text: `Agent-Abbruch konnte nicht angefragt werden. Grund: ${message}`,
      });
    }
  };

  const handleSideMenuDraftPrAction = () => {
    if (sideMenuDraftPrDecision.action === 'open-repo-setup') {
      handleCompactToolSelect('repo');
      return;
    }
    if (sideMenuDraftPrDecision.action === 'open-github-access') {
      handleCompactToolSelect('github_access');
      return;
    }
    if (sideMenuDraftPrDecision.action !== 'publish-draft-pr') return;

    void publishConfirmedDraftPr();
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
    <>
    <section
      className={[
        builderContainerContract.rootClass,
        chatRepoSnapshot ? "sovereign-builder-container--repo-ready" : "",
      ].filter(Boolean).join(" ")}
      data-role={builderContainerContract.dataRole}
      data-testid={builderContainerContract.testId}
      data-layout="devchat-appcontrol-integrated"
      aria-label={builderContainerContract.ariaLabel}
      style={{
        width: "100%",
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
        /* Responsive shell width — phones and tablets (portrait/landscape, e.g. iPad 9th gen "A9")
           use the full device viewport; only large desktop/tablet-landscape screens get a
           comfortable reading-width cap so the chat doesn't stretch edge-to-edge forever. */
        .sovereign-builder-container { max-width: 100vw; }
        @media (min-width: 1180px) {
          .sovereign-builder-container { max-width: 980px; }
        }
        /* WorkbenchSidePanel: hidden on phone/tablet portrait, only visible on wide desktop/landscape */
        .sovereign-side-panel { display: none; }
        @media (min-width: 1024px) and (min-height: 600px) {
          .sovereign-side-panel { display: flex; }
        }
        .sovereign-chat-workbench { flex: 1; min-height: 0; display: flex; background: ${C.bg}; }
        .sovereign-chat-body { min-width: 0; }
        .sovereign-repo-split-inspector { display: none; }
        @media (orientation: landscape) and (min-width: 860px) and (min-height: 520px), (min-width: 1024px) and (min-height: 600px) {
          .sovereign-builder-container--repo-ready { max-width: 100vw; }
          .sovereign-repo-split-inspector {
            display: flex;
            flex: 0 0 clamp(240px, 28vw, 360px);
            min-width: 0;
            max-width: 38vw;
            overflow: hidden;
            border-right: 1px solid ${C.border};
            background: ${C.surface};
          }
          .sovereign-repo-split-inspector [data-testid="repo-split-inspector"] {
            width: 100%;
            height: 100%;
            overflow: auto;
            padding: 10px 12px 14px;
          }
          .sovereign-chat-workbench--split .sovereign-chat-body { border-left: 1px solid ${C.border}; }
        }
        /* Responsive chat bubble */
        .sovereign-chat-bubble { max-width: 92%; }
        @media (min-width: 640px) {
          .sovereign-chat-bubble { max-width: min(720px, 88%); }
        }
        /* Responsive code blocks */
        .sovereign-code-block { max-width: 100%; overflow-x: auto; white-space: pre; -webkit-overflow-scrolling: touch; }
        /* Idea grid */
        .sovereign-idea-grid { grid-template-columns: 1fr 1fr; max-width: 340px; }
        @media (min-width: 620px) {
          .sovereign-idea-grid { grid-template-columns: repeat(3, 1fr); max-width: 560px; }
        }
        @media (min-width: 900px) {
          .sovereign-idea-grid { grid-template-columns: repeat(4, 1fr); max-width: 720px; }
        }
        ::-webkit-scrollbar-track { background: transparent; }
      `}</style>

      {/* TOP BAR — v3 design + Workbench status chips + PAL badge */}
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
        credits={credits}
        userLoggedIn={!!authUser}
        userAvatar={authUser?.avatarUrl ?? null}
        userInitials={authUser
          ? (authUser.displayName || authUser.email)
              .split(' ').map((w: string) => w[0]).join('').toUpperCase().slice(0, 2)
          : undefined}
        onUserClick={() => authUser ? setShowProfile(true) : setShowLogin(true)}
        workbenchStatusSlots={workbenchStatusSlots}
        onWorkbenchSlotClick={(id) => {
          if (id === "logs") {
            setPanelOpen((v) => !v);
            return;
          }
          setOpenWorkbenchSlot(id);
        }}
        showInspector={showInspector}
      />

      {/* COLLAPSIBLE STATUS/LOG PANEL */}
      <StatusPanel
        open={panelOpen}
        logs={statusLogs}
        signals={signals}
        modules={MODULES}
        onClearLogs={() => setStatusLogs([])}
      />

      {/* Werkbank Slot Drawer — Actions/Files/Errors/Draft PR bottom sheet */}
      {openWorkbenchSlot && (
        <WorkbenchSlotDrawer
          slot={workbenchStatusSlots.find((s) => s.id === openWorkbenchSlot) ?? workbenchStatusSlots[0]}
          onClose={() => setOpenWorkbenchSlot(null)}
          onOpenDraftPr={(url) => window.open(url, "_blank", "noopener,noreferrer")}
        />
      )}

      {/* ── Issue #426: Worker Degraded Banner */}
      {workerBlocker && (
        <WorkerDegradedBanner
          blocker={workerBlocker}
          userMessage={lastWorkerRequestMessage ?? undefined}
          onRetryWithMessage={(msg) => {
            setWorkerBlocker(null);
            appendActionEvent(buildLocalRuntimeResultEvent({
              label: 'Retry gestartet',
              detail: 'Worker-Banner hat den letzten Request erneut an die echte Worker-Route übergeben.',
            }));
            addLog("info", "Worker retry from banner", "router");
            retrySubmit(msg, { ignoreExistingWorkerBlocker: true });
          }}
        />
      )}

      {/* MAIN CONTENT */}
      <div className={chatRepoSnapshot && isChat ? "sovereign-chat-workbench sovereign-chat-workbench--split" : "sovereign-chat-workbench"}>
        {chatRepoSnapshot && isChat ? (
          <aside className="sovereign-repo-split-inspector" aria-label="Repo-Baum Split-Bereich">
            <RepoTreeExplorer
              snapshot={chatRepoSnapshot}
              variant="split"
              onFileClick={handleRepoExplorerFileClick}
            />
          </aside>
        ) : null}
      {isChat ? (
        /* ── CHAT VIEW with auto-scroll lock (Issue #425) */
        <div
          ref={scrollRef}
          className="sovereign-chat-body"
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
          {/* Fix 5: Partial-Snapshot Guard — never show fabricated repo truth */}
          {isPartialRepoSnapshot && (
            <div
              role="alert"
              data-testid="partial-repo-snapshot-warning"
              style={{
                margin: '8px 0',
                padding: '10px 14px',
                borderRadius: 10,
                background: '#fbbf2412',
                border: '1px solid #fbbf2440',
                fontSize: 12,
                color: '#fbbf24',
                display: 'flex',
                gap: 8,
                alignItems: 'flex-start',
              }}
            >
              <span style={{ flexShrink: 0 }}>⚠️</span>
              <span>
                <strong>Unvollständiger Repo-Snapshot.</strong> Owner, Repo, Branch oder URL fehlt.
                Der angezeigte Zustand wäre unvollständig. Bitte Repo neu laden.
              </span>
            </div>
          )}

          {!wishText.trim() && !chatRepoSnapshot && chatHistory.length === 0 && !securityCardPending ? (
            <WelcomeScreen
              onIdea={(opt) => setWishText((c) => appendOption(c, opt))}
            />
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                padding: "12px 0 6px",
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
              <SovereignActionStreamPanel stream={actionStream} />

              {/* ── Issue #520 + #522: Integration Intent Draft Card — runtime-contracted routing */}
              {hasPendingDraft(intentDraftState) && (() => {
                const draft = intentDraftState.draft;
                
                // Build Capability Registry from runtime truth (no tokens, no fakes)
                const capabilities = buildSovereignToolCapabilityRegistry({
                  repoReady: effectiveRepoReady,
                  githubAccessState: effectiveGitHubAccessState,
                  githubTokenPresent: Boolean(githubTokenRef.current),
                  directPatchSupported: Boolean(chatRepoSnapshot && githubWriteAllowed && githubTokenRef.current),
                  agentConfigured: sovereignAgentStartAvailable,
                  workerAvailable: !workerBlocker,
                  workspaceConfigured: false,
                  draftPrSupported: githubWriteAllowed,
                  activeExecutorStatus:
                    scopedAgentIsRunning ||
                    ['intent_detected', 'executor_starting', 'executor_running', 'branch_created', 'commit_created'].includes(agentWorkSnapshot.state)
                      ? 'running'
                      : 'idle',
                });

                // Build Workspace Scope only when repo is loaded (no fake scope)
                const workspaceScope = chatRepoSnapshot
                  ? createSovereignWorkspaceScope({
                      repoFullName: `${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo}`,
                      repoUrl: `https://github.com/${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo}`,
                      branch: chatRepoSnapshot.branch,
                      allowedPaths: ['src/', 'tests/', 'scripts/', 'README.md', 'docs/'],
                      forbiddenPaths: ['.env', '.env.local', 'node_modules/', 'dist/', 'build/', 'android/app/build/'],
                      draftPrOnly: true,
                      githubWriteValidated: githubWriteAllowed,
                      maxAction: 'draft_pr',
                    })
                  : null;

                // Gate snapshot for card display (kept for backward compatibility)
                const gateSnapshot: IntegrationIntentDraftGateSnapshot = {
                  repoReady: effectiveRepoReady,
                  githubWriteReady: capabilities.githubWrite.status === 'ready',
                  directPatchReady: capabilities.directPatch.canStart,
                  agentReady: capabilities.agent.canStart,
                };

                // canExecute from runtime truth
                const canExecute = capabilities.directPatch.canStart || capabilities.agent.canStart;
                const confirmCheck = canConfirmIntegrationIntentDraft(draft, gateSnapshot);

                return (
                  <IntegrationIntentDraftCard
                    draft={draft}
                    gateSnapshot={gateSnapshot}
                    canConfirm={effectiveRepoReady && canExecute}
                    confirmBlocker={!effectiveRepoReady ? confirmCheck.blocker : undefined}
                    onConfirm={() => {
                      // Use Runtime Bridge for route decision
                      const intent = classifySovereignExecutorIntent(draft.originalText);
                      const bridgeDecision = decideSovereignExecutorBridgeRoute({
                        text: draft.originalText,
                        intent,
                        capabilities,
                        workspaceScope: workspaceScope ?? undefined,
                        candidatePath: chatRepoSnapshot
                          ? detectDirectPatchTarget(draft.originalText, chatRepoSnapshot.filePaths ?? []) ?? undefined
                          : undefined,
                      });

                      // Log confirmed draft
                      appendActionEvent(buildDraftConfirmedEvent(draft));
                      setIntentDraftState({ status: 'confirmed', draft });

                      // Always log the bridge decision event
                      appendActionEvent(bridgeDecision.event);

                      // Handle Sovereign Internal Operator route
                      if (bridgeDecision.bridgeRoute === 'sovereign_internal_operator') {
                        if (bridgeDecision.state === 'allowed') {
                          // Internal operator is available - runtime handoff decision
                          appendChatLine({
                            role: 'assistant',
                            text: `Integrationsauftrag bestätigt.\n\nRoute: Sovereign Internal Operator\nErgebnis bleibt Draft-PR-only: erst Patch/Diff prüfen, dann Draft PR.\nKein Auto-Merge.`,
                          });
                          addLog('info', `Integration via Sovereign Internal Operator bridge: ${bridgeDecision.reason}`, 'router');
                          setTimeout(() => setIntentDraftState({ status: 'idle' }), 100);
                          return;
                        } else {
                          // Internal operator blocked
                          appendChatLine({
                            role: 'assistant',
                            text: `Auftrag blockiert.\n\nGrund: ${bridgeDecision.reason}`,
                          });
                          addLog('warn', `Integration blocked by bridge: ${bridgeDecision.reason}`, 'router');
                          setTimeout(() => setIntentDraftState({ status: 'idle' }), 100);
                          return;
                        }
                      }

                      // Handle executor_runtime routes from the bridge contract.
                      // Do not cast the bridge decision: the bridge now exposes the original
                      // executor route explicitly so allowed Direct Patch decisions cannot fall
                      // through to the default blocker path.
                      const decision = {
                        route: bridgeDecision.executorRoute ?? 'blocked',
                        reason: bridgeDecision.reason,
                      };

                      switch (decision.route) {
                        case 'github_access':
                          // Open GitHub Access Gate, no executor starts
                          pendingWriteIntentRef.current = draft.originalText;
                          setShowGitHubAccessOverride(true);
                          appendChatLine({
                            role: 'assistant',
                            text: 'GitHub-Schreibzugang wird benötigt.\nBitte Zugang unten einrichten.',
                          });
                          break;

                        case 'direct_patch':
                          // Direct Patch route via proper runtime
                          // Runtime-Truth: All result types must be terminal-handled
                          if (!chatRepoSnapshot) break;
                          addLog('info', `Integration confirmed: ${decision.reason}`, 'router');
                          const patchScopeKey = currentRepoScopeKey;
                          clearPatchEvidence();
                          buildDirectPatchPlanWithContentLoad({
                            repoContext: {
                              owner: chatRepoSnapshot.owner,
                              name: chatRepoSnapshot.repo,
                              branch: chatRepoSnapshot.branch,
                              filePaths: chatRepoSnapshot.filePaths ?? [],
                            },
                            instruction: draft.originalText,
                            githubAccessReady: true,
                            token: githubTokenRef.current!,
                            fetcher: globalThis.fetch,
                          }).then((result) => {
                            if (!isCurrentRepoScope(patchScopeKey)) {
                              appendActionEvent(buildBlockedActionEvent({
                                route: 'direct-github-patch',
                                label: 'Patch-Ergebnis verworfen',
                                detail: 'Das Repo oder der Branch hat sich während der Patch-Erzeugung geändert.',
                                kind: 'blocked',
                              }));
                              setIntentDraftState({ status: 'idle' });
                              return;
                            }

                            // Terminal state: clear draft only after result
                            setTimeout(() => setIntentDraftState({ status: 'idle' }), 100);

                            if ('result' in result && result.result.ok) {
                              // Success: Patch preview generated
                              appendActionEvent({
                                kind: 'route_selected',
                                route: 'direct-github-patch',
                                label: 'Direct GitHub Patch Route gewählt',
                                detail: `Zieldatei: ${result.result.targetPath}`,
                                state: 'running',
                              });
                              appendActionEvent({
                                kind: 'done',
                                route: 'direct-github-patch',
                                label: 'Patch-Vorschau generiert',
                                detail: result.result.patchSummary,
                                state: 'done',
                              });
                              appendChatLine({
                                role: 'assistant',
                                text: `Direct GitHub Patch Route verfügbar für ${result.result.targetPath}.\n\nPatch-Vorschlag:\n${result.result.patchSummary}\n\nNächste Aktion: ${result.result.nextAction === 'preview_diff' ? 'Diff-Vorschau prüfen' : 'Draft PR erstellen'}`,
                              });
                              stageGeneratedPatch({
                                path: result.result.targetPath,
                                proposedContent: result.result.proposedContent,
                                baseContent: result.result.baseContent,
                                summary: result.result.patchSummary,
                              });
                              setLastAnswerWasLocal(true);
                              return;
                            }

                            // Terminal failure: capability unavailable
                            if ('capability' in result && !result.capability.available) {
                              appendActionEvent({
                                kind: 'patch_blocked',
                                route: 'direct-github-patch',
                                label: 'Direct Patch nicht verfügbar',
                                detail: result.capability.reason,
                                state: 'blocked',
                              });
                              appendChatLine({
                                role: 'assistant',
                                text: `Direct GitHub Patch nicht möglich: ${result.capability.reason}`,
                              });
                              return;
                            }

                            // Terminal failure: error state (result.ok === false)
                            if ('result' in result && !result.result.ok) {
                              const failureResult = result.result;
                              const errorMessage = 'reason' in failureResult ? failureResult.reason : 'Unknown error';
                              appendActionEvent({
                                kind: 'failed',
                                route: 'direct-github-patch',
                                label: 'Direct Patch fehlgeschlagen',
                                detail: errorMessage,
                                state: 'failed',
                              });
                              appendChatLine({
                                role: 'assistant',
                                text: `Direct GitHub Patch fehlgeschlagen: ${errorMessage}`,
                              });
                              return;
                            }
                          }).catch((err) => {
                            // Terminal failure: promise rejection
                            setTimeout(() => setIntentDraftState({ status: 'idle' }), 100);
                            const errMsg = err instanceof Error ? err.message : String(err);
                            appendActionEvent({
                              kind: 'failed',
                              route: 'direct-github-patch',
                              label: 'Direct Patch Ausnahme',
                              detail: errMsg,
                              state: 'failed',
                            });
                            appendChatLine({
                              role: 'assistant',
                              text: `Direct GitHub Patch fehlgeschlagen: ${errMsg}`,
                            });
                          });
                          break;

                        case 'sovereign-agent':
                          // Sovereign Agent route — ONLY with validated GitHub write
                          if (!githubWriteAllowed) {
                            // Defensive: block and open access gate
                            appendActionEvent(buildRouteBlockedEvent('GitHub-Zugang erforderlich'));
                            setShowGitHubAccessOverride(true);
                            appendChatLine({
                              role: 'assistant',
                              text: 'Sovereign Agent Runtime benötigt GitHub-Schreibzugang.\nBitte Zugang unten einrichten.',
                            });
                            break;
                          }
                          addLog('info', `Integration confirmed: ${decision.reason}`, 'router');
                          void startAgentFromText(draft.originalText);
                          break;

                        case 'workspace':
                          // Workspace route detected but not yet connected — honest block
                          appendChatLine({
                            role: 'assistant',
                            text: `Workspace-Route erkannt, aber noch nicht verbunden.\n\nGrund: ${decision.reason}`,
                          });
                          break;

                        case 'worker_chat':
                          // Worker Chat — advisory only, no write success
                          appendChatLine({
                            role: 'assistant',
                            text: 'Beratungsroute erkannt. Worker Chat kann Rückfragen beantworten.',
                          });
                          break;

                        case 'local_status':
                          // Status query — answer from runtime state
                          break;

                        case 'blocked':
                        default:
                          // Honest block with reason
                          appendChatLine({
                            role: 'assistant',
                            text: `Auftrag blockiert.\n\nGrund: ${decision.reason}`,
                          });
                          break;
                      }

                      // Clear draft state after processing
                      setTimeout(() => setIntentDraftState({ status: 'idle' }), 100);
                    }}
                    onConfirmWithGitHubAccess={() => {
                      // P2 Fix 4: Called when user clicks "GitHub-Zugang benötigt"
                      // Opens the GitHub Access Gate
                      appendActionEvent({
                        kind: 'github_access_required',
                        route: 'github-access',
                        label: 'GitHub-Schreibzugang erforderlich',
                        detail: 'Draft bestätigt aber GitHub-Zugang fehlt',
                        state: 'blocked',
                      });
                      pendingWriteIntentRef.current = draft.originalText;
                      setShowGitHubAccessOverride(true);
                      appendChatLine({
                        role: 'assistant',
                        text: 'Integrationsauftrag bestätigt.\nGitHub-Schreibzugang wird benötigt.\nBitte Zugang unten einrichten.',
                      });
                      setIntentDraftState({ status: 'idle' });
                      addLog('info', 'Integration draft confirmed: GitHub access gate opened', 'router');
                    }}
                    onRephrase={() => {
                      // Rephrase the draft - put rephrased text in input, don't execute
                      appendActionEvent(buildDraftRephrasedEvent(draft));
                      setWishText(draft.rephrasedText);
                      setIntentDraftState({ status: 'idle' });
                      addLog('info', 'Integration draft rephrased, text updated in input', 'router');
                    }}
                    onReject={() => {
                      // Reject the draft - clear state and log honest rejection
                      appendActionEvent(buildDraftRejectedEvent());
                      setIntentDraftState({ status: 'idle' });
                      appendChatLine({
                        role: 'assistant',
                        text: 'Integrationsauftrag verworfen. Bitte formuliere den Auftrag neu.',
                      });
                      addLog('info', 'Integration draft rejected by user', 'router');
                    }}
                  />
                );
              })()}

              {/* ── Manus/Replit-style live event stream — Sovereign Agent remains one route among several */}
              {agentWorkSnapshot.state !== 'idle' && (
                <AgentEventStream
                  snapshot={agentWorkSnapshot}
                  job={scopedAgentJob}
                  onCancel={onCancelAgent}
                  onOpenDraftPr={
                    (scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl)
                      ? () => window.open((scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl)!, '_blank')
                      : undefined
                  }
                  onOpenFile={openRepoExplorerFromFileBadge}
                />
              )}

              {/* ── Gap 3: Security Block Card — shown when secret detected in chat input */}
              {securityCardPending && (
                <SecurityBlockCard
                  title={securityCardPending.title}
                  text={securityCardPending.text}
                  hint={securityCardPending.hint}
                  buttonLabel={securityCardPending.buttonLabel}
                  onOpenSecureAccess={() => {
                    setShowGitHubAccessOverride(true);
                    setSecurityCardPending(null);
                  }}
                  onDismiss={() => setSecurityCardPending(null)}
                />
              )}

              {/* ── Issue #443: GitHub Access Card (shown when write access needed but not available) */}
              {!githubWriteAllowed && (scopedAgentJob?.status === 'running' || isPublishing || showGitHubAccessOverride) && (
                <GitHubAccessCard
                  snapshot={effectiveGitHubAccessSnapshot}
                  onProvideToken={async (token) => {
                    // SECURITY: Token is only used for this one-shot validation.
                    // It is never written into chat history, logs, telemetry or action events.
                    const formatResult = validateGitHubTokenFormat(token);
                    if (!formatResult.isValid) {
                      setGitHubAccessState(failGitHubAccessValidation('', formatResult.error || 'Ungültiges Format'));
                      setValidatedGitHubTargetKey(null);
                      githubTokenRef.current = null;
                      return;
                    }

                    const validationTargetKey = currentRepositoryTargetKey;
                    const validationRepoScopeKey = currentRepoScopeKey;
                    const validationRepoSnapshot = chatRepoSnapshot;
                    if (!validationTargetKey || !validationRepoScopeKey || !validationRepoSnapshot) {
                      setGitHubAccessState(failGitHubAccessValidation(formatResult.maskedToken, 'Repo-Ziel fehlt für GitHub-Zugangsprüfung.'));
                      setValidatedGitHubTargetKey(null);
                      githubTokenRef.current = null;
                      appendActionEvent(buildBlockedActionEvent({
                        route: 'github-access',
                        label: 'GitHub-Zugang fehlgeschlagen',
                        detail: 'Repo-Ziel fehlt für GitHub-Zugangsprüfung.',
                        kind: 'failed',
                      }));
                      return;
                    }

                    setValidatedGitHubTargetKey(null);
                    setGitHubAccessState(startGitHubAccessValidation(formatResult.maskedToken));
                    appendActionEvent({
                      kind: 'route_selected',
                      route: 'github-access',
                      label: 'GitHub-Zugang wird geprüft',
                      detail: 'Echte GitHub-API-Prüfung läuft.',
                      state: 'running',
                    });
                    appendChatLine({
                      role: 'assistant',
                      text: 'Token wurde übernommen. GitHub-Zugang wird jetzt geprüft. Bitte Zwischenablage auf Android leeren, falls das Token kopiert wurde.',
                    });

                    const validation = await validateGitHubTokenForRepo(
                      token,
                      { owner: validationRepoSnapshot.owner, repo: validationRepoSnapshot.repo },
                      globalThis.fetch,
                    );

                    if (
                      currentRepositoryTargetKeyRef.current !== validationTargetKey
                      || !isCurrentRepoScope(validationRepoScopeKey)
                    ) {
                      setGitHubAccessState(createGitHubAccessSnapshot());
                      setValidatedGitHubTargetKey(null);
                      githubTokenRef.current = null;
                      appendActionEvent(buildBlockedActionEvent({
                        route: 'github-access',
                        label: 'GitHub-Zugangsprüfung verworfen',
                        detail: 'Das Repo-Ziel hat sich während der Validierung geändert. Der alte Prüferfolg wurde nicht übernommen.',
                        kind: 'blocked',
                      }));
                      return;
                    }

                    if (!validation.ok) {
                      setGitHubAccessState(failGitHubAccessValidation(formatResult.maskedToken, validation.error || 'GitHub-Zugangsprüfung fehlgeschlagen.'));
                      setValidatedGitHubTargetKey(null);
                      githubTokenRef.current = null;
                      appendActionEvent(buildBlockedActionEvent({
                        route: 'github-access',
                        label: 'GitHub-Zugang fehlgeschlagen',
                        detail: validation.error || 'GitHub-Zugangsprüfung fehlgeschlagen.',
                        kind: 'failed',
                      }));
                      appendChatLine({
                        role: 'assistant',
                        text: `GitHub-Zugangsprüfung fehlgeschlagen: ${validation.error || 'unbekannter Fehler'}`,
                      });
                      return;
                    }

                    setGitHubAccessState(completeGitHubAccessValidation(formatResult.maskedToken));
                    setValidatedGitHubTargetKey(validationTargetKey);
                    githubTokenRef.current = token;
                    appendActionEvent({
                      kind: 'done',
                      route: 'github-access',
                      label: 'GitHub-Zugang bereit',
                      detail: 'Schreibzugriff auf das geladene Repo wurde bestätigt.',
                      state: 'done',
                    });

                    const pendingWriteIntent = pendingWriteIntentRef.current;
                    pendingWriteIntentRef.current = null;
                    if (!pendingWriteIntent) {
                      appendChatLine({
                        role: 'assistant',
                        text: 'GitHub-Zugang ist bereit. Der Zugangswert wird nicht im Chat gespeichert. Wenn er in einem Screen Recording oder Clipboard-Verlauf sichtbar war, bitte rotieren.',
                      });
                      return;
                    }

                    appendChatLine({
                      role: 'assistant',
                      text: 'GitHub-Zugang ist bereit. Ich nehme den blockierten Schreibauftrag wieder auf. Der Zugangswert wird nicht im Chat gespeichert. Wenn er in einem Screen Recording oder Clipboard-Verlauf sichtbar war, bitte rotieren.',
                    });
                    appendActionEvent({
                      kind: 'route_selected',
                      route: 'github-patch',
                      label: 'Patch/Draft-PR Route gestartet',
                      detail: 'Blockierter Schreibauftrag wird nach bestätigtem GitHub-Zugang fortgesetzt.',
                      state: 'running',
                    });

                    if (agentDisabled) {
                      const tokenForDirectPatch = githubTokenRef.current;
                      if (!agentReady && tokenForDirectPatch && validation.canWrite === true) {
                        const patchScopeKey = validationRepoScopeKey;
                        clearPatchEvidence();
                        const directPatchResult = await buildDirectPatchPlanWithContentLoad({
                          repoContext: {
                            owner: chatRepoSnapshot.owner,
                            name: chatRepoSnapshot.repo,
                            branch: chatRepoSnapshot.branch,
                            filePaths: chatRepoSnapshot.filePaths ?? [],
                          },
                          instruction: pendingWriteIntent,
                          githubAccessReady: true,
                          token: tokenForDirectPatch,
                          fetcher: globalThis.fetch,
                        });

                        if (!isCurrentRepoScope(patchScopeKey)) {
                          appendActionEvent(buildBlockedActionEvent({
                            route: 'direct-github-patch',
                            label: 'Patch-Ergebnis verworfen',
                            detail: 'Das Repo oder der Branch hat sich während der Patch-Erzeugung geändert.',
                            kind: 'blocked',
                          }));
                          return;
                        }

                        if ('result' in directPatchResult && directPatchResult.result.ok) {
                          appendActionEvent({
                            kind: 'route_selected',
                            route: 'direct-github-patch',
                            label: 'Direct GitHub Patch Route gewählt',
                            detail: `Zieldatei: ${directPatchResult.result.targetPath}`,
                            state: 'running',
                          });
                          appendActionEvent({
                            kind: 'done',
                            route: 'direct-github-patch',
                            label: 'Patch-Vorschau generiert',
                            detail: directPatchResult.result.patchSummary,
                            state: 'done',
                          });
                          appendChatLine({
                            role: 'assistant',
                            text: `Direct GitHub Patch Route verfügbar für ${directPatchResult.result.targetPath}.\n\nPatch-Vorschlag:\n${directPatchResult.result.patchSummary}\n\nNächste Aktion: ${directPatchResult.result.nextAction === 'preview_diff' ? 'Diff-Vorschau prüfen' : 'Draft PR erstellen'}`,
                          });
                          stageGeneratedPatch({
                            path: directPatchResult.result.targetPath,
                            proposedContent: directPatchResult.result.proposedContent,
                            baseContent: directPatchResult.result.baseContent,
                            summary: directPatchResult.result.patchSummary,
                          });
                          setLastAnswerWasLocal(true);
                          addLog('info', 'Pending write intent resumed through Direct GitHub Patch Route', 'router');
                          return;
                        }

                        if ('capability' in directPatchResult && !directPatchResult.capability.available) {
                          appendActionEvent(buildBlockedActionEvent({
                            route: 'direct-github-patch',
                            label: 'Direct Patch nicht verfügbar',
                            detail: directPatchResult.capability.reason,
                            kind: 'patch_blocked',
                          }));
                          appendChatLine({
                            role: 'assistant',
                            text: `Der GitHub-Zugang ist bereit, aber Direct GitHub Patch ist für diesen Auftrag nicht verfügbar.\nGrund: ${directPatchResult.capability.reason}\n\nSovereignAgent Runtime ist nicht verbunden. Es wurde noch keine Datei geändert.`,
                          });
                          addLog('warn', 'Pending write intent direct patch unavailable: ' + directPatchResult.capability.reason, 'router');
                          return;
                        }

                        // Runtime-Truth: Handle Direct Patch failure (result.ok === false)
                        if ('result' in directPatchResult && !directPatchResult.result.ok) {
                          const failureResult = directPatchResult.result;
                          const errorMessage = 'reason' in failureResult ? failureResult.reason : 'Direct Patch fehlgeschlagen';
                          appendActionEvent({
                            kind: 'failed',
                            route: 'direct-github-patch',
                            label: 'Direct Patch fehlgeschlagen',
                            detail: errorMessage,
                            state: 'failed',
                          });
                          appendChatLine({
                            role: 'assistant',
                            text: `Direct GitHub Patch fehlgeschlagen: ${errorMessage}`,
                          });
                          addLog('error', 'Pending write intent direct patch failed: ' + errorMessage, 'router');
                          return;
                        }
                      }

                      appendActionEvent(buildBlockedActionEvent({
                        route: 'github-patch',
                        label: 'Patch/Draft-PR Route blockiert',
                        detail: agentReady ? 'Executor ist für diesen Auftrag nicht startklar.' : 'Sovereign Agent Runtime ist nicht verbunden.',
                        kind: 'patch_blocked',
                      }));
                      appendChatLine({
                        role: 'assistant',
                        text: agentReady
                          ? 'Der GitHub-Zugang ist bereit, aber die Patch/Draft-PR Route ist gerade blockiert. Es wurde noch keine Datei geändert.'
                          : 'Der GitHub-Zugang ist bereit, aber weder Direct GitHub Patch noch Sovereign Agent Runtime ist für diesen Auftrag verfügbar. Es wurde noch keine Datei geändert.',
                      });
                      return;
                    }

                    void startAgentFromText(pendingWriteIntent);
                  }}
                  onDismiss={() => {
                    setShowGitHubAccessOverride(false);
                    appendActionEvent(buildLocalRuntimeResultEvent({
                      label: 'GitHub-Zugangsfläche geschlossen',
                      detail: 'Die manuell geöffnete Zugangsfläche wurde geschlossen; kein Zugangsstatus wurde verändert.',
                    }));
                  }}
                />
              )}

              {/* ── Issue #426: Worker Blocker Card */}
              {workerBlocker && (
                <WorkerBlockerCard
                  blocker={workerBlocker}
                  onRetryWithMessage={(msg) => {
                    setWorkerBlocker(null);
                    appendActionEvent(buildLocalRuntimeResultEvent({
                      label: 'Retry gestartet',
                      detail: 'Worker-Blocker-Karte hat den letzten Request erneut an die echte Worker-Route übergeben.',
                    }));
                    addLog(
                      "info",
                      "Worker retry with message from card",
                      "router",
                    );
                    retrySubmit(msg, { ignoreExistingWorkerBlocker: true });
                  }}
                  onExplain={() => {
                    const explanation = explainDevChatWorkerDiagnostic(
                      workerBlocker.diagnostic,
                    );
                    appendChatLine({ role: "assistant", text: explanation });
                  }}
                  onAgentInstead={(msg) => {
                    void startAgentFromText(msg);
                  }}
                  userMessage={lastWorkerRequestMessage ?? undefined}
                />
              )}

              {/* ── Issue #431: Draft PR Card */}
              {scopedAgentJob?.draftPrUrl && (
                <DraftPrCard
                  url={scopedAgentJob.draftPrUrl}
                  changedFiles={scopedAgentJob.changedFiles || []}
                  onOpenBrowser={() =>
                    window.open(scopedAgentJob.draftPrUrl, "_blank")
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
              deriveBudFromLedger(budgetLedger),
            )}
            onSignalClick={(prompt) => setWishText(prompt)}
          />
          <div style={{ height: 12 }} />
        </div>
      )}
      </div>

      {/* COMPOSER — only in chat view, v3 verbatim */}
      {isChat && (
        <>
          {/* ── Issue #453: LauncherTaskbar — offene Tools als Chips */}
          <LauncherTaskbar />
          {/* ── Issue #445 + #452: SovereignToolLauncher — quick-action "+" launcher + Sovereign Launcher */}
          <SovereignToolLauncher
            runtimeContext={{
              repoReady: effectiveRepoReady,
              repoFileCount: effectiveRepoReady && chatRepoSnapshot
                ? chatRepoSnapshot.files.filter((entry) => entry.type === 'blob').length
                : 0,
              hasDiffEvidence: Boolean(
                patchDiffReport ||
                (scopedAgentJob?.changedFiles?.length ?? 0) > 0,
              ),
              githubAccessState: effectiveGitHubAccessState,
              executorAvailable: sovereignAgentStartAvailable,
              executorActive: scopedAgentIsRunning,
              hasExecutorMission: Boolean(wishText.trim()),
              executorIntent,
              runtimeLogCount: runtimeEvidenceLog.length,
            }}
            onSelect={handleCompactToolSelect}
            onBlockedSelect={handleCompactToolSelect}
            onOpenLauncher={useLauncherStore.getState().openMenu}
          />
          <ActionSuggestionStrip
            actions={SOVEREIGN_PRESET_ACTIONS}
            repoReady={effectiveRepoReady}
            githubWriteReady={githubWriteAllowed}
            agentReady={agentReady ?? false}
            disabled={localRepoLoading || chatResponseBusy || isPublishing}
            onSelect={handlePresetActionSelect}
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

      {/* BOTTOM TAB BAR — Chat + Inspector toggle; technical modules live behind Inspector */}
      <BottomTabBar
        activeTab={activeTab}
        onChatClick={() => switchTab("chat")}
        inspectorOpen={showInspector}
        onToggleInspector={() => setShowInspector((v) => !v)}
      />

      {/* SOVEREIGN LAUNCHER — App-Grid Overlay + Window Host (Issues #452, #453) */}
      <LauncherProvider value={{ geminiApiKey: readGeminiApiKeyFromStorage() }}>
        <LauncherMenu />
        <LauncherWindowHost />
      </LauncherProvider>

      {/* OVERLAYS — v3 verbatim */}
      {showRuntimeSheet && (
        <RuntimeSheet
          sources={runtimeSources}
          current={runtimeSource}
          onClose={() => setShowRuntime(false)}
        />
      )}
      {showRepoSetup && (
        <CompactRepoSetupSheet
          value={repoSetupUrl}
          busy={localRepoLoading}
          error={repoSetupError ?? chatRepoError}
          onChange={(value) => {
            setRepoSetupUrl(value);
            setRepoSetupError(null);
            setChatRepoError(null);
          }}
          onLoad={handleRepoSetupLoad}
          onClose={() => setShowRepoSetup(false)}
        />
      )}
      {showRuntimeEvidenceLogs && (
        <RuntimeEvidenceLogSheet
          entries={runtimeEvidenceLog}
          onClose={() => setShowRuntimeEvidenceLogs(false)}
        />
      )}
      {showPatchDiffEvidence && patchDiffReport && (
        <PatchDiffEvidenceSheet
          report={patchDiffReport}
          confirmed={patchConfirmed}
          onConfirm={() => {
            setPatchConfirmed(true);
            appendActionEvent(buildLocalRuntimeResultEvent({
              label: 'Patch bestätigt',
              detail: `${stagedChanges.length} staged Dateiänderung(en) wurden vom Nutzer geprüft und bestätigt.`,
            }));
          }}
          onClose={() => setShowPatchDiffEvidence(false)}
        />
      )}
      {showRepoExplorer && chatRepoSnapshot && effectiveRepoReady && (
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
          onOpenAllTools={() => {
            appendActionEvent(buildLocalRuntimeResultEvent({
              label: 'Tool-Launcher geöffnet',
              detail: 'Das Seitenmenü hat den registrierten Sovereign Launcher geöffnet.',
            }));
            useLauncherStore.getState().openMenu();
          }}
          onOpenRepo={() => handleCompactToolSelect('repo')}
          onOpenRuntimeLogs={() => handleCompactToolSelect('runtime_logs')}
          onOpenGithubAccess={() => handleCompactToolSelect('github_access')}
          onSelectPreset={handlePresetActionSelect}
          onDraftPrAction={handleSideMenuDraftPrAction}
          draftPrDecision={sideMenuDraftPrDecision}
          shareDecision={sideMenuShareDecision}
          chatRepoSnapshot={chatRepoSnapshot}
          githubAccessState={effectiveGitHubAccessState}
          onCancelAgent={handleSideMenuCancelAgent}
          agentIsRunning={scopedAgentIsRunning}
          palStats={palStats}
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
      {showAgentBriefing && agentConfig && (
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
          </div>
        </div>
      )}
    </section>

      {/* Issue #459: Auth modals */}
      {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
      {showProfile && (
        <UserProfile
          onClose={() => setShowProfile(false)}
          onBuyCredits={() => { setShowProfile(false); setShowPaywall(true); }}
        />
      )}

      {/* Paywall Modal — Credit Packages from Backend */}
      <PaywallModal isOpen={showPaywall} onClose={() => setShowPaywall(false)} />

      {/* Sovereign Skill Scanner — /scan-skills opens this */}
      {showSkillScan && (
        <SkillScanPanel
          onClose={() => setShowSkillScan(false)}
          onInstalled={(slug) => {
            appendChatLine({
              role: "assistant",
              text: `✅ Skill \`/${slug}\` installiert. Tippe \`/${slug}\` um ihn zu nutzen.`,
            });
          }}
        />
      )}
    </>
  );
}

export default BuilderContainer;
