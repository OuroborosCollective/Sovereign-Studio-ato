Warning: truncated output (original token count: 67254)
Total output lines: 7101

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
  SOVEREIGN_WORKER_BASE,
  SOVEREIGN_WORKER_CHAT,
  SOVEREIGN_WORKER_HEALTH,
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
  type DevChatWorkerIntentKind,
  type DevChatWorkerMessage,
} from "../runtime/devChatWorkerBridge";
import {
  fetchSovereignDirectLlmInterpretation,
  SOVEREIGN_DIRECT_LLM_CHAT,
} from "../runtime/sovereignDirectLlmIntentRuntime";
import {
  buildToolchainAutoContext,
  formatToolchainAutoContext,
} from "../runtime/toolchainAutoCallingRuntime";
import {
  fetchOpenPrReviewEvidence,
  formatOpenPrReviewEvidence,
} from "../runtime/githubOpenPrReviewRuntime";
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
import { DraftPrActionPreview } from "../components/DraftPrActionPreview";
import { RuntimeEvidenceLogSheet } from "../components/RuntimeEvidenceLogSheet";
import { TestRunnerResultCard } from "../components/TestRunnerResultCard";
import { AutoCodeReviewCard } from "../components/AutoCodeReviewCard";
import { FileContentPreviewSheet } from "../components/FileContentPreviewSheet";
import { PromptLibraryPanel } from "../components/PromptLibraryPanel";
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
import {
  downloadSessionMarkdown,
  formatPersistedSessionAge,
  getOrCreateCurrentSession,
  saveSession,
  type PersistedSession,
} from "../runtime/sessionPersistenceRuntime";
import { runTests, type TestRunnerResult } from "../runtime/testRunnerRuntime";
import {
  requestAutoCodeReview,
  type AutoCodeReviewResult,
} from "../runtime/autoCodeReviewRuntime";
import { createRepoFilePrompt } from "../runtime/repoTreeExplorerRuntime";
import {
  fetchFileContent,
  type FileContentResult,
} from "../runtime/fileContentBrowserRuntime";
import {
  isNearBottom as isScrollNearBottom,
  shouldAutoScroll,
  shouldShowUnreadBadge,
} from "../runtime/scrollLockBehavior";
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
  buildOfflineCapabilityLanguageEvidence,
} from "../runtime/sovereignCapabilityRouter";
import type { CapabilityRouterInput } from "../runtime/sovereignCapabilityRouter";
import type {
  SovereignAgentConfig,
  SovereignAgentJobSnapshot,
} from "../runtime/sovereignAgentRuntime";
import type { SovereignPatternLearningEvidence } from "../runtime/sovereignAgentClient";
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
  classifyOfflineSovereignExecutorIntent,
  type SovereignExecutorIntentKind,
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
  readonly expectedHeadSha?: string;
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
  patternLearningEvidence?: SovereignPatternLearningEvidence;
  agentJobStatus?: string;
  agentIsRunning?: boolean;
  onStartAgent?: (mission: string, input?: {
    readonly repoUrl: string;
    readonly branch?: string;
    readonly expectedHeadSha?: string;
    readonly githubAccessToken?: string;
  }) => void | Promise<void>;
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

function mapInterpretedIntentToExecutorIntent(
  intent: DevChatWorkerIntentKind | undefined,
): SovereignExecutorIntentKind | null {
  switch (intent) {
    case 'status':
      return 'status';
    case 'free_chat':
    case 'workflow_watch':
      return 'question';
    case 'direct_patch':
      return 'direct_patch';
    case 'code_execution':
    case 'repair_workflow':
      return 'code_execution';
    case 'draft_pr':
      return 'draft_pr';
    default:
      return null;
  }
}

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
import { buildGeneratedFileDiffReportFromUnifiedDiff, type GeneratedFileDiffReport } from "../runtime/generatedFileDiffPreview";
import { requestSemanticDiffNarration, narrativeMap, type SemanticDiffNarrationResult } from "../runtime/semanticDiffNarratorRuntime";
import { fetchCommitsSince, type ChangelogGenerationResult } from "../runtime/changelogRuntime";
import { requestMissionValidation, type MissionValidationResult } from "../runtime/missionValidatorRuntime";
import { MissionValidatorCard } from "../components/MissionValidatorCard";
import { ChangelogPreviewCard } from "../components/ChangelogPreviewCard";
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
import { buildExplicitSkillMission } from '../../toolchain/skillRuntime';
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
                minHeight: 44,
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
            width: 44,
            height: 44,
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
                {palTier.toUpperCase()} · zuletzt
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
              width: 44, height: 44, borderRadius: '50%',
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
            minHeight: 44,
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
            minWidth: 44,
            minHeight: 44,
            padding: 0,
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
              height: 44,
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
              width: 44,
              height: 44,
              padding: 0,
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
      <div style={{ padding: "4px 16px", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center" }}>
        <FileBadge path={msg.path} file={msg.file} onOpenFile={onOpenFile} />
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
…37254 tokens truncated…hot ? `${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo}` : null,
      branch: chatRepoSnapshot?.branch ?? null,
      githubWriteReady: githubWriteAllowed,
      agentReady: agentReady ?? false,
    });
    const gate = evaluateSovereignPresetActionGate(action, {
      repoReady: effectiveRepoReady,
      githubWriteReady: githubWriteAllowed,
      agentReady: agentReady ?? false,
    });

    appendChatLine({ role: 'user', text: submitted });
    appendActionEvent(buildInputReceivedEvent(submitted));

    if (!gate.canStart) {
      if (action.requiresRepo && !effectiveRepoReady) {
        pendingWriteIntentRef.current = submitted;
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
      setWishText('');

      if (action.id === 'open_pr_review' && chatRepoSnapshot) {
        setChatResponseBusy(true);
        const review = await fetchOpenPrReviewEvidence(chatRepoSnapshot);
        setChatResponseBusy(false);
        if (!review.ok || !review.evidence) {
          const detail = review.error || 'Read-only PR-Evidence ist nicht verfügbar.';
          appendActionEvent(buildBlockedActionEvent({
            route: 'toolchain',
            label: 'Offene PRs konnten nicht gelesen werden',
            detail,
            kind: 'failed',
          }));
          appendChatLine({
            role: 'assistant',
            text: `PR-Review blockiert: ${detail}\nEs wurde kein GitHub-Schreibzugang angefordert, kein Executor gestartet und kein LLM-Credit verbraucht.`,
          });
          addLog('warn', `Open PR read-only review failed: ${detail}`, 'router');
          return;
        }

        appendActionEvent({
          kind: 'context_collected',
          route: 'toolchain',
          label: 'Offene PRs read-only geprüft',
          detail: `${review.evidence.openPrCount} offene PR(s) mit Merge-/Check-Evidence gelesen.`,
          state: 'done',
        });
        appendChatLine({
          role: 'assistant',
          text: formatOpenPrReviewEvidence(review.evidence),
        });
        setLastAnswerWasLocal(true);
        addLog('info', `Open PR review completed read-only: ${review.evidence.openPrCount} PR(s)`, 'router');
        return;
      }

      await _processSubmit(submitted, { inputAlreadyRecorded: true });
      return;
    }

    appendActionEvent(buildRouteSelectionEvent({
      route: 'agent',
      reason: `${action.label} benötigt einen echten Repository-Executor; Browser-ARE und lokale Code-Synthese werden übersprungen.`,
      state: 'running',
    }));
    addLog('info', `Reviewable preset routed directly to repository agent: ${action.id}`, 'router');
    setWishText('');
    await startAgentFromText(submitted, 'code_execution');
  };

  const handlePresetActionSelect = (actionId: SovereignPresetActionId) => {
    void runSerializedSubmit(() => processPresetActionSelect(actionId));
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
      appendRuntimeNotice(`${decision.reason} ${decision.nextAction}`);
      return;
    }
    if (decision.surface === 'github-status') {
      appendChatLine({
        role: 'system',
        text: effectiveGitHubAccessState === 'ready'
          ? 'GitHub-Zugang ist validiert. Secret-Werte werden weder angezeigt noch im Chat gespeichert.'
          : 'GitHub-Zugang wird bereits geprüft. Es wurde keine zweite Validierung gestartet.',
      });
      return;
    }
    if (decision.surface === 'executor-status') {
      appendRuntimeNotice(`${decision.reason} ${decision.nextAction}`);
      return;
    }
    if (decision.surface === 'executor-request') {
      void startAgentFromText(wishText.trim(), 'code_execution');
      return;
    }
    if (decision.surface === 'runtime-logs') {
      setShowRuntimeEvidenceLogs(true);
      return;
    }
    if (decision.surface === 'blocked') {
      appendRuntimeNotice(`${decision.reason} Nächste Aktion: ${decision.nextAction}`);
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
      appendRuntimeNotice(`Agent-Abbruch konnte nicht angefragt werden. Grund: ${message}`);
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

    requestDraftPrActionPreview();
  };

  const selectedSlashCommand =
    slashMatches[selectedSlashIndex] ?? slashMatches[0];
  const submitSelectedSlashCommand = (command: SlashCommandDefinition) => {
    const clean = wishText.trimStart();
    const argument = clean.startsWith(command.cmd)
      ? clean.slice(command.cmd.length).trim()
      : "";
    const submitted = argument ? `${command.cmd} ${argument}` : command.cmd;
    void runSerializedSubmit(async () => {
      setWishText("");
      setSlashMenuDismissed(false);
      await _processSubmit(submitted);
    });
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
            setUserScrolledAway(!isScrollNearBottom(el));
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
              {testRunnerBusy && (
                <div role="status" style={{ margin: '8px 12px', padding: 10, border: `1px solid ${C.sky}44`, borderRadius: 10, color: C.sky }}>
                  Echte Workspace-Tests laufen…
                </div>
              )}
              {testRunnerResult && (
                <TestRunnerResultCard
                  result={testRunnerResult}
                  onRepair={(prompt) => setWishText(prompt)}
                />
              )}
              {autoCodeReviewBusy && (
                <div role="status" style={{ margin: '8px 12px', padding: 10, border: `1px solid ${C.violet}44`, borderRadius: 10, color: C.violet }}>
                  Auto Code Review läuft über den aufgelösten OpenRouter-/FreeLLM-Pfad…
                </div>
              )}
              {autoCodeReviewResult && (
                <AutoCodeReviewCard
                  result={autoCodeReviewResult}
                  onCancel={() => setWishText('Behebe die blockierenden Auto-Code-Review-Findings im echten Workspace, führe die relevanten Tests erneut aus und bereite danach nur einen Draft PR vor.')}
                />
              )}
              <SovereignActionStreamPanel stream={actionStream} />

              {/* ── Issue #520 + #522: Integration Intent Draft Card — runtime-contracted routing */}
              {hasPendingDraft(intentDraftState) && (() => {
                const draft = intentDraftState.draft;
                
                // Build Capability Registry from runtime truth (no tokens, no fakes)
                const capabilities = buildSovereignToolCapabilityRegistry({
                  repoReady: effectiveRepoReady,
                  githubAccessState: effectiveGitHubAccessState,
                  githubTokenPresent: Boolean(githubTokenRef.current),
                  directPatchSupported: false,
                  agentConfigured: sovereignAgentStartAvailable,
                  workerAvailable: !workerBlocker,
                  workspaceConfigured: sovereignAgentStartAvailable,
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
                const canExecute = capabilities.agent.canStart;
                const confirmCheck = canConfirmIntegrationIntentDraft(draft, gateSnapshot);

                return (
                  <IntegrationIntentDraftCard
                    draft={draft}
                    gateSnapshot={gateSnapshot}
                    canConfirm={effectiveRepoReady && canExecute}
                    confirmBlocker={!effectiveRepoReady ? confirmCheck.blocker : undefined}
                    onConfirm={() => {
                      // Use Runtime Bridge for route decision
                      const intent = mapInterpretedIntentToExecutorIntent(draft.intentKind)
                        ?? 'unknown';
                      const bridgeDecision = decideSovereignExecutorBridgeRoute({
                        intent,
                        taskComplexity: intent === 'direct_patch' ? 'simple' : intent === 'code_execution' ? 'complex' : 'unknown',
                        capabilities,
                        workspaceScope: workspaceScope ?? undefined,
                        candidatePath: undefined,
                      });

                      // Preserve the exact LLM-understood mission for execution and
                      // later evidence-gated learning. A PR URL is only context; the
                      // pattern cache requires accepted server/vector evidence.
                      const confirmedMission = collapseRepeatedAnalyzedMission(
                        buildAnalyzedMission({
                          wish: draft.originalText,
                          repoReady: effectiveRepoReady,
                          repoReason: effectiveRepoReason,
                        }),
                      );
                      if (lastMissionRef.current !== confirmedMission) {
                        emitMissionChange(confirmedMission);
                      }

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
                            role: 'system',
                            text: `Runtime-Aktion bestätigt.\n\nRoute: Sovereign Internal Operator\nErgebnis bleibt Draft-PR-only: erst Patch/Diff prüfen, dann Draft PR.\nKein Auto-Merge.`,
                          });
                          addLog('info', `Integration via Sovereign Internal Operator bridge: ${bridgeDecision.reason}`, 'router');
                          setTimeout(() => setIntentDraftState({ status: 'idle' }), 100);
                          return;
                        } else {
                          // Internal operator blocked
                          appendRuntimeNotice(`Runtime-Aktion blockiert.\n\nGrund: ${bridgeDecision.reason}`);
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
                          appendRuntimeNotice('GitHub-Schreibzugang wird benötigt.\nBitte Zugang unten einrichten.');
                          break;

                        case 'direct_patch':
                          if (!sovereignAgentStartAvailable || !onStartAgent) {
                            appendActionEvent(buildBlockedActionEvent({
                              route: 'agent-job',
                              label: 'Backend-Workspace-Executor nicht verfügbar',
                              detail: 'Der bestätigte Direct-Patch-Auftrag darf nicht im Browser ausgeführt werden.',
                              kind: 'patch_blocked',
                            }));
                            appendRuntimeNotice('Direct Patch blockiert: Ein bestätigter backend-eigener Workspace-Executor ist erforderlich. Der Browser hat keine Repository-Datei gelesen und keinen Patch erzeugt.');
                            break;
                          }
                          addLog('info', `Integration delegated to backend workspace: ${decision.reason}`, 'router');
                          void startAgentFromText(draft.originalText, 'code_execution');
                          break;

                        case 'sovereign-agent':
                          // Sovereign Agent route — ONLY with validated GitHub write
                          if (!githubWriteAllowed) {
                            // Defensive: block and open access gate while preserving
                            // the confirmed original intent for state-driven resume.
                            appendActionEvent(buildRouteBlockedEvent('GitHub-Zugang erforderlich'));
                            pendingWriteIntentRef.current = draft.originalText;
                            setShowGitHubAccessOverride(true);
                            appendRuntimeNotice('Sovereign Agent Runtime benötigt GitHub-Schreibzugang.\nBitte Zugang unten einrichten.');
                            break;
                          }
                          addLog('info', `Integration confirmed: ${decision.reason}`, 'router');
                          void startAgentFromText(draft.originalText, intent);
                          break;

                        case 'workspace':
                          // Workspace route detected but not yet connected — honest block
                          appendRuntimeNotice(`Workspace-Route blockiert: noch nicht verbunden.\n\nGrund: ${decision.reason}`);
                          break;

                        case 'worker_chat':
                          // Worker Chat — advisory only, no write success
                          appendRuntimeNotice('Runtime-Route: Worker Chat für die vom LLM erkannte Beratungsabsicht.');
                          break;

                        case 'local_status':
                          // Status query — answer from runtime state
                          break;

                        case 'blocked':
                        default:
                          // Honest block with reason
                          appendRuntimeNotice(`Runtime-Aktion blockiert.\n\nGrund: ${decision.reason}`);
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
                      appendRuntimeNotice('Runtime-Aktion bestätigt, aber blockiert.\nGitHub-Schreibzugang wird benötigt.\nBitte Zugang unten einrichten.');
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
                      appendRuntimeNotice('Runtime-Aktionsentwurf verworfen. Bitte formuliere den Auftrag neu.');
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
                    appendRuntimeNotice('Token wurde übernommen. GitHub-Zugang wird jetzt geprüft. Bitte Zwischenablage auf Android leeren, falls das Token kopiert wurde.');

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
                      appendRuntimeNotice(`GitHub-Zugangsprüfung fehlgeschlagen: ${validation.error || 'unbekannter Fehler'}`);
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

                    const pendingWriteIntent = pendingOnlineExecutionRef.current?.text
                      ?? pendingWriteIntentRef.current;
                    if (!pendingWriteIntent) {
                      appendRuntimeNotice('GitHub-Zugang ist bereit. Der Zugangswert wird nicht im Chat gespeichert. Wenn er in einem Screen Recording oder Clipboard-Verlauf sichtbar war, bitte rotieren.');
                      return;
                    }

                    appendRuntimeNotice('GitHub-Zugang ist bereit. Der vorgemerkte Auftrag wird nach dem bestätigten Runtime-State automatisch über dieselbe Routing-Pipeline fortgesetzt. Der Zugangswert wird nicht im Chat gespeichert.');
                    addLog('info', 'GitHub access confirmed; pending intent awaits state-driven resume', 'router');
                  }}
                  onDismiss={() => {
                    pendingOnlineExecutionRef.current = null;
                    pendingWriteIntentRef.current = null;
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
                  onLogin={() => setShowLogin(true)}
                  onExplain={() => {
                    const explanation = explainDevChatWorkerDiagnostic(
                      workerBlocker.diagnostic,
                    );
                    appendRuntimeNotice(explanation);
                  }}
                  onAgentInstead={(msg) => {
                    void startAgentFromText(msg, 'code_execution');
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
              {shouldShowUnreadBadge(userScrolledAway, unseenCount > 0) && (
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
      {missionValidationPending && (
        <MissionValidatorCard
          result={missionValidationPending.result}
          onEdit={() => {
            setWishText(`${missionValidationPending.mission}\n\nBitte ergänzen:\n${missionValidationPending.result.questions.map((question) => `- ${question}`).join('\n')}`);
            setMissionValidationPending(null);
          }}
          onContinue={() => {
            const pending = missionValidationPending;
            missionValidationBypassRef.current = pending.mission;
            setMissionValidationPending(null);
            void startAgentFromText(pending.mission, pending.intent);
          }}
        />
      )}
      {changelogResult && (
        <ChangelogPreviewCard
          result={changelogResult}
          onClose={() => setChangelogResult(null)}
          onUseAsMission={(markdown) => {
            setWishText(`Aktualisiere CHANGELOG.md mit diesem evidenzbasierten Eintrag:\n\n${markdown}`);
            setChangelogResult(null);
          }}
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
      {showPromptLibrary && (
        <PromptLibraryPanel
          onSelectTemplate={(prompt) => setWishText(prompt)}
          onClose={() => setShowPromptLibrary(false)}
        />
      )}
      {filePreviewPath && (
        <FileContentPreviewSheet
          filePath={filePreviewPath}
          result={filePreviewResult}
          loading={filePreviewLoading}
          onClose={() => {
            setFilePreviewPath(null);
            setFilePreviewResult(null);
            setFilePreviewLoading(false);
          }}
          onSendToChat={(prompt) => {
            setWishText(prompt);
            setFilePreviewPath(null);
            setFilePreviewResult(null);
          }}
        />
      )}
      {showDraftPrActionPreview && chatRepoSnapshot && (
        <DraftPrActionPreview
          repoUrl={chatRepoSnapshot.repoUrl}
          branch={chatRepoSnapshot.branch}
          expectedHeadSha={chatRepoSnapshot.headSha}
          mission={lastMissionRef.current.trim() || mission.trim() || 'Create a reviewed Draft PR.'}
          changedFileCount={stagedChanges.length || (scopedAgentJob?.changedFiles?.length ?? 0)}
          evidenceSource={
            stagedChanges.length > 0 && (scopedAgentJob?.changedFiles?.length ?? 0) > 0
              ? 'mixed'
              : stagedChanges.length > 0
                ? 'staged'
                : 'agent'
          }
          onCancel={() => setShowDraftPrActionPreview(false)}
          onConfirm={() => {
            setShowDraftPrActionPreview(false);
            appendActionEvent({
              kind: 'agent_job_requested',
              route: 'github-patch',
              label: 'Draft-PR-Übergabe ausdrücklich bestätigt',
              detail: 'Die Runtime führt jetzt ihren serverseitigen Repository-, Diff-, Review- und Evidence-Gate aus.',
              state: 'queued',
            });
            void publishConfirmedDraftPr();
          }}
        />
      )}
      {showPatchDiffEvidence && patchDiffReport && (
        <PatchDiffEvidenceSheet
          report={patchDiffReport}
          confirmed={patchConfirmed}
          narratives={narrativeMap(semanticDiffResult)}
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
              appendRuntimeNotice("Chat in Zwischenablage kopiert.");
            } else if (result === "failed") {
              appendRuntimeNotice("Chat konnte nicht geteilt werden.");
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
            appendRuntimeNotice(`✅ Skill \`/${slug}\` installiert. Tippe \`/${slug}\` um ihn zu nutzen.`);
          }}
        />
      )}
    </>
  );
}

export default BuilderContainer;
