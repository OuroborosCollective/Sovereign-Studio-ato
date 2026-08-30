import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
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
} from "../runtime/builderContainerHelpers";
import { deriveBuilderContainerState } from "../runtime/builderContainerRuntime";
import { resolveDraftPrBuildStatus } from "../runtime/draftPrBuildStatusRuntime";
import { getSovereignContainerContract } from "../runtime/sovereignContainerContracts";
import {
  SOVEREIGN_ACTION_ANALYZE_MISSION,
  SOVEREIGN_ACTION_DRAFT_PR,
  SOVEREIGN_ACTION_REPAIR_LOG,
} from "../runtime/sovereignActionContracts";
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
  fetchSovereignLlmRouteCatalog,
  parseDevChatGithubUrl,
  streamDevChatWorkerReply,
  summarizeDevChatRepoSnapshot,
  type DevChatRepoSnapshot,
  type DevChatWorkerDiagnostic,
  type DevChatWorkerHealthResult,
  type DevChatWorkerIntentKind,
  type DevChatWorkerMessage,
  type SovereignLlmRouteOption,
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
  appendMissionInput,
  downloadSessionMarkdown,
  formatPersistedSessionAge,
  getOrCreateCurrentSession,
  loadSession,
  sessionMessageToChatLine,
  type PersistedSession,
} from "../runtime/sessionPersistenceRuntime";
import {
  projectMonitorCommunicationLine,
  projectSituationalChatLine,
} from "../runtime/situationalBubbleRuntime";
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
import {
  resolveSovereignAgentConfig,
  type SovereignAgentConfig,
  type SovereignAgentJobSnapshot,
  type SovereignLiveProjection,
  type SovereignWorkspaceEvidenceAnchor,
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
  transitionChecksRunning,
  transitionCommitCreated,
  transitionDraftPrReady,
  transitionBlocked,
  transitionFailed,
  type AgentWorkSnapshot,
} from "../runtime/agentWorkRuntime";
import { AgentWorkTimeline } from "../components/AgentWorkTimeline";
import { AgentEventStream } from "../components/AgentEventStream";
import {
  MonitorCommunicationDock,
  type MonitorCommunicationEntry,
} from "../components/MonitorCommunicationDock";
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
  createStructuredIntegrationIntentDraft,
  buildDraftCreatedEvent,
  buildDraftConfirmedEvent,
  buildDraftRejectedEvent,
  buildDraftRephrasedEvent,
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
import {
  classifyOfflineSovereignExecutorIntent,
  resolveOfflineMachineExecutorIntent,
  type SovereignExecutorIntentKind,
} from "../runtime/sovereignExecutorRuntime";

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
  agentProjections?: readonly SovereignLiveProjection[];
  agentEvidenceAnchors?: readonly SovereignWorkspaceEvidenceAnchor[];
  desktopFrame?: {
    readonly jobId: string;
    readonly url: string;
    readonly frameHash: string;
    readonly observedAt: number;
  } | null;
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
  buildLocalStatusAnswer,
  buildRuntimeConfidence,
  buildWorkerBlockerAnswer,
  buildWorkerMessages,
  composerRouteHint,
  confidenceLabel,
  createChatLineId,
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

function buildExplicitRuntimeCapabilityLanguageEvidence(input: {
  readonly text: string;
  readonly intent: SovereignExecutorIntentKind;
  readonly repositoryUrl: boolean;
  readonly safeAnalysisPreset: boolean;
  readonly retryControl: boolean;
}): CapabilityRouterInput['language'] {
  if (input.repositoryUrl) {
    return {
      intent: 'load_repo',
      complexity: 'simple',
      explicitAgentRequest: false,
      source: 'explicit_runtime_action',
    };
  }
  if (input.safeAnalysisPreset) {
    return {
      intent: 'free_chat',
      complexity: 'simple',
      explicitAgentRequest: false,
      source: 'explicit_runtime_action',
    };
  }
  if (input.retryControl) {
    return {
      intent: 'free_chat',
      complexity: 'simple',
      explicitAgentRequest: false,
      source: 'explicit_runtime_action',
    };
  }

  const explicitAgentRequest = /^\s*\/agent(?:\s|$)/i.test(input.text);
  switch (input.intent) {
    case 'status':
      return { intent: 'status_question', complexity: 'simple', explicitAgentRequest: false, source: 'explicit_runtime_action' };
    case 'question':
      return { intent: 'free_chat', complexity: 'simple', explicitAgentRequest: false, source: 'explicit_runtime_action' };
    case 'direct_patch':
      return { intent: 'direct_patch', complexity: 'simple', explicitAgentRequest: false, source: 'explicit_runtime_action' };
    case 'code_execution':
      return { intent: 'code_generation', complexity: 'complex', explicitAgentRequest: explicitAgentRequest || /^\s*\/code(?:\s|$)/i.test(input.text), source: 'explicit_runtime_action' };
    case 'draft_pr':
      return { intent: 'draft_pr', complexity: 'complex', explicitAgentRequest: true, source: 'explicit_runtime_action' };
    default:
      return { intent: 'unknown', complexity: 'unknown', explicitAgentRequest: false, source: 'explicit_runtime_action' };
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

// ─────────────────────────────────────────────────────────────
// HELPERS — extracted to builderContainerHelpers.ts
// appendOption, normalizeMissionText, collapseRepeatedAnalyzedMission,
// isAnalyzedMission, missionToWishText, buildAnalyzedMission,
// safeHttpsUrl, splitFilePath, buildOutcomeHints, deriveAgentStatus, fmtTime
// ─────────────────────────────────────────────────────────────

// Intent detection from workerIntentDetector module
import { buildExecutorStatusAnswer } from "../runtime/workerIntentDetector";
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
              Monitor
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
              minWidth: 44,
              minHeight: 44,
              padding: 0,
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
              PAL Verlauf
            </div>
            <div
              style={{ fontFamily: "monospace", fontSize: 10, color: C.green }}
            >
              {palStats.total} belegte {palStats.total === 1 ? "Entscheidung" : "Entscheidungen"}
            </div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: C.textMuted,
              }}
            >
              Referenzschätzung: {palStats.savings}% ggü. Faktor 30 · {DEV_CHAT_WORKER_MODELS.length} Modelle konfiguriert
            </div>
          </div>
        )}

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
            Werkzeuge
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {[
              { label: "⬡ Alle Tools", status: "öffnen", action: onOpenAllTools },
              { label: chatRepoSnapshot ? "⎇ Repo öffnen" : "⎇ Repo laden", status: chatRepoSnapshot ? "bereit" : "einrichten", action: onOpenRepo },
              { label: "≡ Runtime Logs", status: "belegte Ereignisse", action: onOpenRuntimeLogs },
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
            🔍 Auftrag analysieren
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

// BottomTabBar — Monitor is the permanent primary destination. The communication
// dock is embedded in that surface; there is no user-facing fallback Chat mode.
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
  const isMonitor = activeTab === "chat";
  const primaryIcon = "▣";
  const primaryLabel = "MONITOR";
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
        aria-current={isMonitor ? "page" : undefined}
        aria-label="Live Monitor"
        data-testid="primary-surface-tab"
        data-primary-surface="desktop-monitor"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 3,
          background: isMonitor ? `${C.sky}08` : "transparent",
          border: "none",
          borderTop: `2px solid ${isMonitor ? C.sky : "transparent"}`,
          cursor: "pointer",
          padding: "4px 2px",
          minWidth: 0,
        }}
      >
        <span style={{ fontSize: 15, color: isMonitor ? C.sky : C.textMuted }}>{primaryIcon}</span>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 7.5,
            color: isMonitor ? C.sky : C.textMuted,
            letterSpacing: 0.3,
          }}
        >
          {primaryLabel}
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
  agentProjections,
  agentEvidenceAnchors,
  desktopFrame,
  patternLearningEvidence,
  agentJobStatus,
  agentIsRunning,
  onStartAgent,
  onCancelAgent,
  publishedPrUrl,
}: BuilderContainerProps) {
  // ── Original v3 state (verbatim)
  const [patternMemoryStore, setPatternMemoryStore] = useState<PatternMemoryStore>(() => loadPatternMemoryStoreFromStorage());
  const [wishText, setWishText] = useState(() => missionToWishText(mission));
  const [showRuntimeSheet, setShowRuntime] = useState(false);
  const [showSideMenu, setShowSide] = useState(false);
  const [showRepoExplorer, setShowRepoExplorer] = useState(false);
  const [showPromptLibrary, setShowPromptLibrary] = useState(false);
  const [filePreviewPath, setFilePreviewPath] = useState<string | null>(null);
  const [filePreviewResult, setFilePreviewResult] = useState<FileContentResult | null>(null);
  const [filePreviewLoading, setFilePreviewLoading] = useState(false);
  const [filePreviewBindingKey, setFilePreviewBindingKey] = useState<string | null>(null);
  const filePreviewRequestGenerationRef = useRef(0);
  const [testRunnerResult, setTestRunnerResult] = useState<TestRunnerResult | null>(null);
  const [testRunnerBusy, setTestRunnerBusy] = useState(false);
  const [autoCodeReviewResult, setAutoCodeReviewResult] = useState<AutoCodeReviewResult | null>(null);
  const [autoCodeReviewBusy, setAutoCodeReviewBusy] = useState(false);
  const [showRepoSetup, setShowRepoSetup] = useState(false);
  const [repoSetupUrl, setRepoSetupUrl] = useState('');
  const [repoSetupError, setRepoSetupError] = useState<string | null>(null);
  const [showRuntimeEvidenceLogs, setShowRuntimeEvidenceLogs] = useState(false);
  const [showPatchDiffEvidence, setShowPatchDiffEvidence] = useState(false);
  const [showDraftPrActionPreview, setShowDraftPrActionPreview] = useState(false);
  const [patchDiffReport, setPatchDiffReport] = useState<GeneratedFileDiffReport | null>(null);
  const [showAgentBriefing, setOHB] = useState(false);
  const [chatRepoSnapshot, setChatRepo] = useState<DevChatRepoSnapshot | null>(
    null,
  );
  const [chatRepoError, setChatRepoError] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatLine[]>([]);
  const [chatResponseBusy, setChatResponseBusy] = useState(false);
  const [, setStreamingText] = useState<string | null>(null);
  const [workerBlocker, setWorkerBlocker] =
    useState<WorkerRuntimeBlocker | null>(null);
  const [workerHealthEvidence, setWorkerHealthEvidence] =
    useState<DevChatWorkerHealthResult | null>(null);
  const [lastWorkerRequestMessage, setLastWorkerRequestMessage] = useState<string | null>(null);
  const [patchPreviewReady, setPatchPreviewReady] = useState(false);
  const [patchConfirmed, setPatchConfirmed] = useState(false);
  const [semanticDiffResult, setSemanticDiffResult] = useState<SemanticDiffNarrationResult | null>(null);
  const [changelogResult, setChangelogResult] = useState<ChangelogGenerationResult | null>(null);
  const [missionValidationPending, setMissionValidationPending] = useState<{ readonly mission: string; readonly intent: SovereignExecutorIntentKind; readonly result: MissionValidationResult } | null>(null);
  const missionValidationBypassRef = useRef<string | null>(null);
  const [stagedChanges, setStagedChanges] = useState<SovereignStagedChange[]>([]);
  const [, setLastAnswerWasLocal] = useState(false);
  const [localRepoLoading, setRepoLoading] = useState(false);
  const lastMissionRef = useRef(mission);
  const ignoreNextMissionSyncRef = useRef(false);
  const chatLineIndexRef = useRef(0);
  const persistedSessionRef = useRef<PersistedSession | null>(null);
  const hydratedSessionScopeRef = useRef<string | null>(null);
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
  const [llmRouteOptions, setLlmRouteOptions] = useState<readonly SovereignLlmRouteOption[]>([]);
  const [selectedLlmRouteId, setSelectedLlmRouteId] = useState("");
  const [llmRouteCatalogError, setLlmRouteCatalogError] = useState<string | null>(null);
  const { credits } = useCreditGuard();
  // ── Issue #459: User auth state
  const { user: authUser, refreshUser } = useUserStore();
  const [showLogin, setShowLogin]     = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showPaywall, setShowPaywall] = useState(false);
  useEffect(() => { refreshUser(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!authUser?.id) {
      setLlmRouteOptions([]);
      setLlmRouteCatalogError(null);
      return;
    }

    const controller = new AbortController();
    let active = true;
    void fetchSovereignLlmRouteCatalog(controller.signal, 'picker')
      .then((routes) => {
        if (!active) return;
        setLlmRouteOptions(routes);
        setLlmRouteCatalogError(null);
      })
      .catch((error) => {
        if (!active || controller.signal.aborted) return;
        setLlmRouteOptions([]);
        setLlmRouteCatalogError(error instanceof Error ? error.message : 'Routenkatalog nicht verfügbar.');
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [authUser?.id]);

  // ── Sovereign App Toolchain — auto-load after login
  const {
    loadTools: loadToolchain,
    getToolContext,
    loaded: toolchainLoaded,
    loading: toolchainLoading,
    error: toolchainError,
  } = useToolchainStore();
  useEffect(() => {
    if (authUser && !toolchainLoaded) { loadToolchain(); }
  }, [authUser, toolchainLoaded, loadToolchain]);

  // ── Sovereign Skill System — auto-load + dynamic slash commands
  const {
    loadSkills,
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
      skill_id: s.skill_id,
      source_sha: s.source_sha,
      content_sha256: s.content_sha256,
    })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [installedSkills],
  );
  const [statusLogs, setStatusLogs] = useState<
    Array<{ ts: string; level: string; msg: string; tabId: string }>
  >([]);

  const currentRepoScopeKey = useMemo(
    () => buildRepoEvidenceScopeKey(chatRepoSnapshot),
    [chatRepoSnapshot],
  );
  const currentRepositoryTargetKey = useMemo(
    () => buildRepositoryTargetKey(chatRepoSnapshot),
    [chatRepoSnapshot],
  );
  const currentFilePreviewBindingKey = useMemo(
    () => currentRepositoryTargetKey && chatRepoSnapshot?.headSha
      ? `${currentRepositoryTargetKey}@${chatRepoSnapshot.headSha.toLowerCase()}`
      : null,
    [chatRepoSnapshot?.headSha, currentRepositoryTargetKey],
  );
  const scopedPublishedPrUrl = useMemo(
    () => selectRepositoryScopedPullRequestUrl(publishedPrUrl, currentRepositoryTargetKey),
    [currentRepositoryTargetKey, publishedPrUrl],
  );
  const scopedAgentJob = useMemo(
    () => selectRepoScopedAgentJob(agentJob, chatRepoSnapshot),
    [chatRepoSnapshot, agentJob],
  );
  const scopedDesktopFrame = desktopFrame?.jobId === scopedAgentJob?.jobId
    ? desktopFrame
    : null;
  const scopedAgentEvidenceAnchors = scopedAgentJob?.jobId && scopedAgentJob.workspaceId
    ? (agentEvidenceAnchors ?? []).filter((anchor) => (
        anchor.jobId === scopedAgentJob.jobId
        && anchor.workspaceId === scopedAgentJob.workspaceId
      ))
    : [];
  const githubAccessApiBase = useMemo(
    () => agentConfig?.agentApiUrl || resolveSovereignAgentConfig().agentApiUrl || SOVEREIGN_WORKER_BASE,
    [agentConfig],
  );
  const scopedAgentIsRunning = Boolean(
    scopedAgentJob
    && ['queued', 'provisioning', 'running', 'validating'].includes(scopedAgentJob.status),
  );
  const scopedAgentProjections = useMemo(
    () => scopedAgentJob?.jobId && scopedAgentJob.workspaceId
      ? (agentProjections ?? []).filter((projection) => (
          projection.jobId === scopedAgentJob.jobId
          && projection.workspaceId === scopedAgentJob.workspaceId
        ))
      : [],
    [agentProjections, scopedAgentJob?.jobId, scopedAgentJob?.workspaceId],
  );
  // The workspace monitor is the permanent primary product surface. Runtime
  // projections and desktop frames enrich it when available; they never decide
  // whether the user is sent back to a legacy chat screen.
  const liveMonitorPrimary = activeTab === 'chat';
  // Keep LLM/user communication stable while a job starts, projections rotate or
  // desktop evidence refreshes. Only account/repository scope changes reset it.
  const monitorAccountKey = authUser?.id ?? 'guest';
  const monitorScopeKey = currentRepoScopeKey ?? 'unbound';
  const previousMonitorBindingRef = useRef({
    accountKey: monitorAccountKey,
    scopeKey: monitorScopeKey,
  });
  const [monitorCommunication, setMonitorCommunication] = useState<MonitorCommunicationEntry[]>([]);
  const monitorCommunicationSequenceRef = useRef(0);
  const appendMonitorCommunication = useCallback((
    kind: MonitorCommunicationEntry['kind'],
    text: string,
    id?: string,
  ) => {
    const clean = text.trim();
    if (!clean) return;
    monitorCommunicationSequenceRef.current += 1;
    const entry: MonitorCommunicationEntry = {
      id: id ?? `monitor-communication-${monitorCommunicationSequenceRef.current}`,
      kind,
      text: clean,
      createdAt: Date.now(),
    };
    setMonitorCommunication((previous) => {
      if (previous.some((existing) => existing.id === entry.id)) return previous;
      return [...previous.slice(-11), entry];
    });
  }, []);
  useEffect(() => {
    const previous = previousMonitorBindingRef.current;
    const next = { accountKey: monitorAccountKey, scopeKey: monitorScopeKey };
    previousMonitorBindingRef.current = next;
    const preserveFirstRepositoryBinding = previous.accountKey === next.accountKey
      && previous.scopeKey === 'unbound'
      && next.scopeKey !== 'unbound';
    if (preserveFirstRepositoryBinding) return;
    setMonitorCommunication([]);
    monitorCommunicationSequenceRef.current = 0;
  }, [monitorAccountKey, monitorScopeKey]);

  // ── Issue #443: GitHub Access State
  const [githubAccessState, setGitHubAccessState] = useState<GitHubAccessSnapshot>(
    createGitHubAccessSnapshot(),
  );
  const [validatedGitHubTargetKey, setValidatedGitHubTargetKey] = useState<string | null>(null);
  const pendingWriteIntentRef = useRef<string | null>(null);
  // Read-only presets can wait only for repository evidence. Keep them separate
  // from write intents so an unrelated repo load can never wake a stale write.
  const pendingRepoIntentRef = useRef<string | null>(null);
  const pendingOnlineExecutionRef = useRef<{
    readonly text: string;
    readonly intent: 'code_execution' | 'draft_pr';
  } | null>(null);
  const submitInFlightRef = useRef(false);
  const startAgentInFlightRef = useRef(false);
  const publishDraftPrInFlightRef = useRef(false);
  const pendingResumeRetryRef = useRef(false);
  const [pendingResumeRetrySequence, setPendingResumeRetrySequence] = useState(0);
  const currentRepoScopeKeyRef = useRef<string | null>(currentRepoScopeKey);
  currentRepoScopeKeyRef.current = currentRepoScopeKey;
  const isCurrentRepoScope = useCallback(
    (scopeKey: string | null) => Boolean(scopeKey && currentRepoScopeKeyRef.current === scopeKey),
    [],
  );
  const currentRepositoryTargetKeyRef = useRef<string | null>(currentRepositoryTargetKey);
  currentRepositoryTargetKeyRef.current = currentRepositoryTargetKey;
  const validatedGitHubWriteEvidenceRef = useRef<{
    readonly targetKey: string;
    readonly snapshot: GitHubAccessSnapshot;
  } | null>(null);
  const repositoryReadScopeRef = useRef<{
    readonly targetKey: string;
    readonly revision: string;
    readonly scope: string;
  } | null>(null);
  const currentRepositoryRevisionRef = useRef(
    chatRepoSnapshot?.headSha?.toLowerCase() ?? '',
  );
  currentRepositoryRevisionRef.current = chatRepoSnapshot?.headSha?.toLowerCase() ?? '';
  const hasCurrentGitHubWriteEvidence = useCallback(() => {
    const targetKey = currentRepositoryTargetKeyRef.current;
    const evidence = validatedGitHubWriteEvidenceRef.current;
    return Boolean(
      targetKey
      && evidence
      && evidence.targetKey === targetKey
      && canPerformGitHubWrite(evidence.snapshot)
    );
  }, []);
  const githubWriteAllowed = Boolean(
    currentRepositoryTargetKey
    && validatedGitHubTargetKey === currentRepositoryTargetKey
    && canPerformGitHubWrite(githubAccessState),
  ) || hasCurrentGitHubWriteEvidence();
  const effectiveGitHubAccessState = githubAccessState.state === 'ready' && !githubWriteAllowed
    ? 'missing'
    : githubAccessState.state;
  const effectiveGitHubAccessSnapshot = useMemo(
    () => effectiveGitHubAccessState === githubAccessState.state
      ? githubAccessState
      : createGitHubAccessSnapshot(),
    [effectiveGitHubAccessState, githubAccessState],
  );
  
  // Temporary compatibility bridge: the token remains memory-only and may be
  // forwarded to the backend executor. Browser-side repository reads, patch
  // generation and GitHub writes are forbidden.
  const githubTokenRef = useRef<string | null>(null);
  const previousFilePreviewBindingRef = useRef<string | null>(null);
  useEffect(() => {
    const nextBinding = currentRepositoryTargetKey && chatRepoSnapshot?.headSha
      ? `${currentRepositoryTargetKey}@${chatRepoSnapshot.headSha.toLowerCase()}`
      : null;
    if (previousFilePreviewBindingRef.current === nextBinding) return;
    previousFilePreviewBindingRef.current = nextBinding;
    repositoryReadScopeRef.current = null;
    filePreviewRequestGenerationRef.current += 1;
    setFilePreviewPath(null);
    setFilePreviewResult(null);
    setFilePreviewLoading(false);
    setFilePreviewBindingKey(null);
  }, [chatRepoSnapshot?.headSha, currentRepositoryTargetKey]);
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
    // Explorer visibility is reset at the explicit repository replacement point.
    // Derived scope effects must not race a user click that opens the inspector.
    setAgentWorkSnapshot(createIdleSnapshot(`sovereign-${Date.now()}`));

    const accessMatchesCurrentRepo = Boolean(
      currentRepositoryTargetKey
      && validatedGitHubTargetKey === currentRepositoryTargetKey,
    );
    if (!accessMatchesCurrentRepo) {
      githubTokenRef.current = null;
      // Preserve an unscoped blocked intent across the first successful repo
      // load. A pending intent from an already-scoped previous repo is stale.
      if (previousScopeKey) {
        pendingWriteIntentRef.current = null;
        pendingRepoIntentRef.current = null;
        pendingOnlineExecutionRef.current = null;
      }
      validatedGitHubWriteEvidenceRef.current = null;
      repositoryReadScopeRef.current = null;
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
        const resolvedBranch = scopedAgentJob.branchName;
        if (snap.state === 'executor_running' && resolvedBranch) {
          snap = transitionBranchCreated(snap, resolvedBranch);
        }
        if (snap.state === 'branch_created' || snap.state === 'commit_created') {
          snap = transitionChecksRunning(snap);
        }
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

  const [actionStream, setActionStream] = useState(() => createSovereignActionStreamState());
  const appendActionEvent = useCallback((event: SovereignActionEventInput) => {
    setActionStream((current) => appendSovereignActionEvent(current, event));
  }, []);

  const githubCredentialValidationGenerationRef = useRef(0);
  const validateCurrentRepoGithubCredential = useCallback(async (
    token: string | undefined,
    maskedToken: string,
    source: 'oauth-session' | 'manual-pat',
  ): Promise<boolean> => {
    const validationGeneration = ++githubCredentialValidationGenerationRef.current;
    const validationTargetKey = currentRepositoryTargetKey;
    const validationRepoScopeKey = currentRepoScopeKey;
    const validationRepoSnapshot = chatRepoSnapshot;
    if (!validationTargetKey || !validationRepoScopeKey || !validationRepoSnapshot) {
      setGitHubAccessState(failGitHubAccessValidation(maskedToken, 'Revisionsgebundener Repository-Scope fehlt für GitHub-Zugangsprüfung.'));
      setValidatedGitHubTargetKey(null);
      if (source === 'manual-pat') githubTokenRef.current = null;
      return false;
    }

    validatedGitHubWriteEvidenceRef.current = null;
    repositoryReadScopeRef.current = null;
    setValidatedGitHubTargetKey(null);
    setGitHubAccessState(startGitHubAccessValidation(maskedToken));
    appendActionEvent({
      kind: 'route_selected',
      route: 'github-access',
      label: source === 'oauth-session'
        ? 'GitHub OAuth-Session wird geprüft'
        : 'GitHub-Zugang wird geprüft',
      detail: 'Backend prüft Credential, Repository, Branch und erwarteten Head ohne Credential-Readback.',
      state: 'running',
    });

    const validation = await validateGitHubTokenForRepo(
      token,
      {
        repository: validationRepoSnapshot.repoUrl,
        branch: validationRepoSnapshot.branch,
        expectedBaseSha: validationRepoSnapshot.headSha,
      },
      globalThis.fetch,
      githubAccessApiBase,
    );

    // A newer OAuth/PAT attempt for the same repository owns the state now.
    // Stale completions must not clear or replace its credential evidence.
    if (githubCredentialValidationGenerationRef.current !== validationGeneration) return false;

    if (
      currentRepositoryTargetKeyRef.current !== validationTargetKey
      || !isCurrentRepoScope(validationRepoScopeKey)
    ) {
      validatedGitHubWriteEvidenceRef.current = null;
      repositoryReadScopeRef.current = null;
      setGitHubAccessState(createGitHubAccessSnapshot());
      setValidatedGitHubTargetKey(null);
      if (source === 'manual-pat') githubTokenRef.current = null;
      appendActionEvent(buildBlockedActionEvent({
        route: 'github-access',
        label: 'GitHub-Zugangsprüfung verworfen',
        detail: 'Das Repo-Ziel hat sich während der Validierung geändert. Der alte Prüferfolg wurde nicht übernommen.',
        kind: 'blocked',
      }));
      return false;
    }

    const validatedRepositoryReadScope = (
      validation.repositoryReadScope
      && validation.repositoryRevision === validationRepoSnapshot.headSha.toLowerCase()
    ) ? {
        targetKey: validationTargetKey,
        revision: validation.repositoryRevision,
        scope: validation.repositoryReadScope,
      } : null;
    repositoryReadScopeRef.current = validatedRepositoryReadScope;

    if (!validation.ok) {
      validatedGitHubWriteEvidenceRef.current = null;
      setGitHubAccessState(failGitHubAccessValidation(
        maskedToken,
        validation.error || 'GitHub-Zugangsprüfung fehlgeschlagen.',
      ));
      setValidatedGitHubTargetKey(null);
      if (source === 'manual-pat') {
        githubTokenRef.current = validatedRepositoryReadScope ? token || null : null;
      }
      appendActionEvent(buildBlockedActionEvent({
        route: 'github-access',
        label: source === 'oauth-session'
          ? 'GitHub OAuth reicht für dieses Repo nicht aus'
          : 'GitHub-Zugang fehlgeschlagen',
        detail: validation.error || 'GitHub-Zugangsprüfung fehlgeschlagen.',
        kind: 'failed',
      }));
      return false;
    }

    const readySnapshot = completeGitHubAccessValidation(maskedToken);
    validatedGitHubWriteEvidenceRef.current = {
      targetKey: validationTargetKey,
      snapshot: readySnapshot,
    };
    repositoryReadScopeRef.current = validatedRepositoryReadScope;
    setGitHubAccessState(readySnapshot);
    setValidatedGitHubTargetKey(validationTargetKey);
    setPendingResumeRetrySequence((sequence) => sequence + 1);
    githubTokenRef.current = source === 'manual-pat' ? token || null : null;
    appendActionEvent({
      kind: 'done',
      route: 'github-access',
      label: 'GitHub-Zugang bereit',
      detail: source === 'oauth-session'
        ? 'Serverseitig gespeichertes OAuth-Credential und Repo-Schreibzugriff wurden bestätigt; kein Token wurde an den Browser zurückgegeben.'
        : 'Ephemeres Credential und effektiver Repo-Schreibzugriff wurden serverseitig bestätigt.',
      state: 'done',
    });
    return true;
  }, [
    appendActionEvent,
    chatRepoSnapshot,
    currentRepoScopeKey,
    currentRepositoryTargetKey,
    githubAccessApiBase,
    isCurrentRepoScope,
  ]);

  const oauthValidationAttemptRef = useRef<{
    readonly targetKey: string;
    readonly attempts: number;
    readonly triggerSequence: number;
  } | null>(null);
  const oauthValidationRetryTimerRef = useRef<number | null>(null);
  const [oauthValidationRetrySequence, setOauthValidationRetrySequence] = useState(0);
  useEffect(() => () => {
    if (oauthValidationRetryTimerRef.current !== null) {
      window.clearTimeout(oauthValidationRetryTimerRef.current);
      oauthValidationRetryTimerRef.current = null;
    }
  }, []);
  useEffect(() => {
    if (!authUser?.githubId || !currentRepositoryTargetKey || !chatRepoSnapshot?.headSha) {
      oauthValidationAttemptRef.current = null;
      if (oauthValidationRetryTimerRef.current !== null) {
        window.clearTimeout(oauthValidationRetryTimerRef.current);
        oauthValidationRetryTimerRef.current = null;
      }
      return;
    }
    if (githubWriteAllowed || githubAccessState.state === 'validating') return;

    let attempt = oauthValidationAttemptRef.current;
    if (!attempt || attempt.targetKey !== currentRepositoryTargetKey) {
      if (oauthValidationRetryTimerRef.current !== null) {
        window.clearTimeout(oauthValidationRetryTimerRef.current);
        oauthValidationRetryTimerRef.current = null;
      }
      attempt = { targetKey: currentRepositoryTargetKey, attempts: 0, triggerSequence: -1 };
    }
    if (attempt.attempts >= 2 || attempt.triggerSequence === oauthValidationRetrySequence) return;

    const validationTargetKey = currentRepositoryTargetKey;
    oauthValidationAttemptRef.current = {
      targetKey: validationTargetKey,
      attempts: attempt.attempts + 1,
      triggerSequence: oauthValidationRetrySequence,
    };
    const validationPromise = validateCurrentRepoGithubCredential(undefined, 'OAuth', 'oauth-session');
    const oauthValidationGeneration = githubCredentialValidationGenerationRef.current;
    void validationPromise.then((validated) => {
      const latestAttempt = oauthValidationAttemptRef.current;
      if (validated) {
        if (oauthValidationRetryTimerRef.current !== null) {
          window.clearTimeout(oauthValidationRetryTimerRef.current);
          oauthValidationRetryTimerRef.current = null;
        }
        return;
      }
      if (
        !latestAttempt
        || latestAttempt.targetKey !== validationTargetKey
        || githubCredentialValidationGenerationRef.current !== oauthValidationGeneration
        || latestAttempt.attempts >= 2
        || currentRepositoryTargetKeyRef.current !== validationTargetKey
        || oauthValidationRetryTimerRef.current !== null
      ) return;
      oauthValidationRetryTimerRef.current = window.setTimeout(() => {
        oauthValidationRetryTimerRef.current = null;
        setOauthValidationRetrySequence((sequence) => sequence + 1);
      }, 750);
    });
  }, [
    authUser?.githubId,
    chatRepoSnapshot?.headSha,
    currentRepositoryTargetKey,
    githubAccessState.state,
    githubWriteAllowed,
    oauthValidationRetrySequence,
    validateCurrentRepoGithubCredential,
  ]);
  const inspectionEvidence = useSovereignToolInspectionStore((store) => store.evidence);
  const completedInspectionEvidenceRef = useRef<Partial<Record<SovereignToolInspectionId, number>>>({});
  const sovereignAgentStartAvailable = Boolean(agentReady && onStartAgent);
  // The explicit Executor shortcut is itself the action signal. The unfinished
  // composer text is never semantically classified by the runtime.
  const executorIntent: SovereignExecutorIntentKind = wishText.trim() ? 'code_execution' : 'unknown';
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
        actionEvents: actionStream.events,
        workerBlocker,
        chatRepoError,
        agentJob: scopedAgentJob,
        publishedPrUrl: scopedPublishedPrUrl,
        githubState: effectiveGitHubAccessState,
        agentConfigured: sovereignAgentStartAvailable,
        patchRouteAvailable: false,
      }),
    [
      statusLogs,
      actionStream.events,
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
    async (path: string) => {
      const cleanPath = path.trim();
      if (!cleanPath) return;
      const requestGeneration = ++filePreviewRequestGenerationRef.current;
      const requestRepoScopeKey = currentRepoScopeKey;
      const requestTargetKey = currentRepositoryTargetKey;
      const requestRevision = chatRepoSnapshot?.headSha?.toLowerCase() ?? '';
      const requestBindingKey = currentFilePreviewBindingKey;
      const readScopeEvidence = repositoryReadScopeRef.current;
      const repositoryReadScope = (
        readScopeEvidence
        && requestTargetKey
        && readScopeEvidence.targetKey === requestTargetKey
        && readScopeEvidence.revision === requestRevision
      ) ? readScopeEvidence.scope : undefined;

      setWishText(createRepoFilePrompt(cleanPath));
      setShowRepoExplorer(false);
      setFilePreviewPath(cleanPath);
      setFilePreviewResult(null);
      setFilePreviewLoading(true);
      setFilePreviewBindingKey(requestBindingKey);
      const result = await fetchFileContent({
        jobId: scopedAgentJob?.status === 'cleaned' ? '' : scopedAgentJob?.jobId ?? '',
        workspaceUsable: scopedAgentJob?.status !== 'cleaned',
        backendBase: SOVEREIGN_WORKER_BASE,
        filePath: cleanPath,
        repoOwner: chatRepoSnapshot?.owner,
        repoName: chatRepoSnapshot?.repo,
        repoRevision: chatRepoSnapshot?.headSha,
        repositoryReadScope,
        githubAccessToken: githubTokenRef.current ?? undefined,
      });
      if (
        filePreviewRequestGenerationRef.current !== requestGeneration
        || currentRepoScopeKeyRef.current !== requestRepoScopeKey
        || currentRepositoryRevisionRef.current !== requestRevision
      ) return;
      setFilePreviewResult(result);
      setFilePreviewLoading(false);
      addLog(
        result.status === 'loaded' ? 'info' : 'warn',
        result.status === 'loaded'
          ? `Workspace file loaded: ${cleanPath} · ${result.sizeBytes} bytes`
          : `Workspace file preview blocked: ${cleanPath} · ${result.error}`,
        'router',
      );
    },
    [
      addLog,
      chatRepoSnapshot?.headSha,
      chatRepoSnapshot?.owner,
      chatRepoSnapshot?.repo,
      currentFilePreviewBindingKey,
      currentRepoScopeKey,
      currentRepositoryTargetKey,
      scopedAgentJob?.jobId,
      scopedAgentJob?.status,
    ],
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
      const candidate: ChatLine = {
        ...line,
        id: line.id ?? createChatLineId(line.role, chatLineIndexRef.current),
        createdAt,
      };
      const committed = projectSituationalChatLine(candidate);
      const monitorLine = projectMonitorCommunicationLine(candidate);
      if (monitorLine) {
        appendMonitorCommunication(
          monitorLine.role === 'user'
            ? 'user'
            : monitorLine.role === 'system'
              ? 'runtime'
              : 'communicate',
          monitorLine.text,
          `monitor:${monitorLine.id}`,
        );
      }
      if (!committed) return;
      setChatHistory((previous) => [...previous, committed]);
    },
    [appendMonitorCommunication],
  );

  const appendRuntimeNotice = useCallback((text: string) => {
    appendChatLine({
      role: 'system',
      text,
      monitorProjection: {
        schemaVersion: 'sovereign.monitor-communication-projection.v1',
        sourceKind: 'RUNTIME_NOTICE',
        authority: 'CONVERSATION_ONLY',
        authoritative: false,
      },
    });
  }, [appendChatLine]);

  const appendGuardedWorkerText = useCallback((text: string) => {
    const claimCheck = checkChatClaim(text, agentWorkSnapshot);
    const guardedText = claimCheck.allowed || !claimCheck.honestFallback
      ? text
      : `${text}\n\n_[Sovereign: ${claimCheck.honestFallback}]_`;
    if (!claimCheck.allowed && claimCheck.violations.length > 0) {
      addLog('warn', `chatClaimGuard: ${claimCheck.violations.join(', ')}`, 'router');
    }
    appendChatLine({
      role: 'assistant',
      text: guardedText,
      monitorProjection: {
        schemaVersion: 'sovereign.monitor-communication-projection.v1',
        sourceKind: 'LLM_RESPONSE',
        authority: 'CONVERSATION_ONLY',
        authoritative: false,
      },
    });
  }, [addLog, agentWorkSnapshot, appendChatLine]);

  const persistMissionInput = useCallback(async (text: string): Promise<boolean> => {
    if (!authUser) {
      setShowLogin(true);
      appendActionEvent(buildBlockedActionEvent({
        route: 'runtime',
        label: 'Mission nicht gespeichert',
        detail: 'Eine bestätigte Sitzung ist für die reale PostgreSQL-Persistenz erforderlich.',
        kind: 'blocked',
      }));
      return false;
    }

    const repositoryIdentity = chatRepoSnapshot?.repoUrl ?? 'UNBOUND';
    const repositoryBranch = chatRepoSnapshot?.branch ?? 'main';
    try {
      const normalizedRepository = repositoryIdentity.replace(/\.git$/i, '');
      let session = persistedSessionRef.current;
      if (
        !session
        || session.repoUrl !== normalizedRepository
        || session.repoBranch !== repositoryBranch
      ) {
        session = await getOrCreateCurrentSession(
          SOVEREIGN_WORKER_BASE,
          repositoryIdentity,
          repositoryBranch,
        );
      }
      const persisted = await appendMissionInput(
        SOVEREIGN_WORKER_BASE,
        session,
        text,
      );
      const message = persisted.messages.at(-1);
      if (!message) throw new Error('persisted mission readback missing');
      persistedSessionRef.current = persisted;
      appendChatLine(sessionMessageToChatLine(message));
      return true;
    } catch {
      appendActionEvent(buildBlockedActionEvent({
        route: 'runtime',
        label: 'Mission nicht gespeichert',
        detail: 'Der PostgreSQL-Commit oder sein typisierter Readback ist nicht verfügbar.',
        kind: 'blocked',
      }));
      addLog('warn', 'Mission persistence blocked; no localStorage fallback was used.', 'router');
      return false;
    }
  }, [
    addLog,
    appendActionEvent,
    appendChatLine,
    authUser,
    chatRepoSnapshot,
  ]);

  const recordOnlineLanguageObservation = useCallback(async (input: {
    readonly prompt: string;
    readonly response: string;
    readonly modelId: string;
    readonly intent: DevChatWorkerIntentKind;
  }): Promise<void> => {
    if (!authUser || !input.response.trim()) return;
    try {
      const inference = await evaluateAreInference({
        prompt: input.prompt,
        repository: buildAreRepositoryState({
          owner: chatRepoSnapshot?.owner,
          repo: chatRepoSnapshot?.repo,
          branch: chatRepoSnapshot?.branch,
          repositoryRevision: chatRepoSnapshot?.treeSha,
          files: chatRepoSnapshot?.files ?? [],
        }),
        onlineAvailable: true,
        limit: 5,
      });
      const transition = emitAreStateTransition(arePreviousStateRef.current, inference);
      arePreviousStateRef.current = {
        stateHash: inference.stateHash,
        state: inference.state,
      };
      if (transition.changed) {
        addLog(
          'info',
          `ARE-State geändert: ${transition.changeKinds.join(', ')} · ${transition.currentStateHash.slice(0, 12)}`,
          'pattern',
        );
      }

      const quarantine = await quarantineAreResponse({
        prompt: input.prompt,
        response: input.response,
        stateHash: inference.stateHash,
        adapter: inference.adapter,
        modelId: input.modelId,
        metadata: {
          repository: currentRepositoryTargetKey,
          intent: input.intent,
          source: 'direct_openrouter_freellm_language_observation',
          knowledgeIds: inference.selectedKnowledgeIds,
          patternIds: inference.selectedPatternIds,
        },
      });
      appendActionEvent({
        kind: 'context_collected',
        route: 'runtime',
        label: quarantine.duplicate
          ? 'Online-Beobachtung bereits quarantänisiert'
          : 'Online-Beobachtung quarantänisiert',
        detail: quarantine.learningState === 'pending_evidence'
          ? 'Noch kein gelerntes Muster: Der Kandidat wartet auf akzeptierte Runtime-Evidence.'
          : `Bestehender evidenzgeprüfter Zustand: ${quarantine.candidate.status}.`,
        state: 'done',
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendActionEvent(buildBlockedActionEvent({
        route: 'runtime',
        label: 'Online-Lernbeobachtung nicht gespeichert',
        detail: message,
        kind: 'failed',
      }));
      addLog('warn', `ARE Online-Beobachtung fehlgeschlagen: ${message}`, 'pattern');
    }
  }, [
    addLog,
    appendActionEvent,
    authUser,
    chatRepoSnapshot,
    currentRepositoryTargetKey,
  ]);

  useEffect(() => {
    if (!authUser || !chatRepoSnapshot || !currentRepoScopeKey) {
      persistedSessionRef.current = null;
      hydratedSessionScopeRef.current = null;
      return;
    }

    const authenticatedScope = `${String((authUser as { id?: string }).id ?? '')}:${currentRepoScopeKey}`;
    if (hydratedSessionScopeRef.current === authenticatedScope) return;
    hydratedSessionScopeRef.current = authenticatedScope;
    let cancelled = false;

    void (async () => {
      try {
        const resolved = await getOrCreateCurrentSession(
          SOVEREIGN_WORKER_BASE,
          chatRepoSnapshot.repoUrl,
          chatRepoSnapshot.branch,
        );
        const session = await loadSession(
          SOVEREIGN_WORKER_BASE,
          resolved.sessionId,
        );
        if (cancelled) return;
        persistedSessionRef.current = session;
        chatLineIndexRef.current = session.messages.length;
        const restored = session.messages.map(sessionMessageToChatLine);
        setChatHistory(restored);
        const restoredMonitorEntries = restored
          .map(projectMonitorCommunicationLine)
          .filter((line): line is ChatLine => line !== null)
          .slice(-12)
          .map((line, index): MonitorCommunicationEntry => ({
            id: `restored-monitor-${line.id || index}`,
            kind: line.role === 'user' ? 'user' : line.role === 'system' ? 'runtime' : 'communicate',
            text: line.text,
            createdAt: line.createdAt,
          }));
        setMonitorCommunication((previous) => {
          const byId = new Map<string, MonitorCommunicationEntry>();
          [...restoredMonitorEntries, ...previous].forEach((entry) => byId.set(entry.id, entry));
          return [...byId.values()]
            .sort((left, right) => left.createdAt - right.createdAt)
            .slice(-12);
        });

        addLog(
          'info',
          `PostgreSQL bubble session restored: ${session.messageCount} message(s)`,
          'sys',
        );
        if (session.messageCount > 0) {
          const age = formatPersistedSessionAge(session);
          if (age.isStale) {
            appendRuntimeNotice(`Warnung: Die wiederhergestellte Session ist älter als 3 Tage (Alter: ${age.text}) und möglicherweise nicht mehr mit dem aktuellen Codebase-Stand synchron.`);
          } else {
            appendRuntimeNotice(`Session erfolgreich wiederhergestellt (Alter: ${age.text}).`);
          }
        }
      } catch {
        if (cancelled) return;
        persistedSessionRef.current = null;
        setChatHistory([]);
        addLog('warn', 'PostgreSQL bubble persistence is unavailable; no local fallback was used.', 'sys');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [addLog, authUser, chatRepoSnapshot, currentRepoScopeKey]);

  // ── Issue #447: Project only server-accepted learning evidence into local cache
  usePatternMemoryStore({
    agentWorkSnapshot,
    patternMemoryStore,
    setPatternMemoryStore,
    mission,
    repoOwner: chatRepoSnapshot?.owner ?? '',
    repoName: chatRepoSnapshot?.repo ?? '',
    appendChatLine,
    learningEvidence: patternLearningEvidence,
    publishedPrUrl: scopedPublishedPrUrl,
  });

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
      ? "LLM Runtime antwortet"
      : scopedAgentJob
        ? agentJobStatus?.trim() || "Sovereign Agent Runtime arbeitet"
        : "Runtime arbeitet"
    : workerBlocker
      ? `blocked · ${workerBlocker.diagnostic.status ? `Worker HTTP ${workerBlocker.diagnostic.status}` : "Worker blockiert"}`
      : effectiveRepoReady
        ? "idle · Repo-Kontext bereit"
        : "idle · Repo fehlt";
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
  const workerHealthReady = workerHealthEvidence?.ok === true;
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
      ? "LLM Runtime blockiert"
      : workerSourceTier === "unknown"
        ? "LLM Runtime nicht geprüft"
        : "LLM Runtime",
    tier: workerSourceTier,
    description: workerBlocker
      ? workerBlocker.message
      : workerSourceTier === "unknown"
        ? "Noch keine Health- oder Response-Evidence für diese Sitzung."
        : `${SOVEREIGN_DIRECT_LLM_CHAT} · direkter OpenRouter-/FreeLLM-Transport`,
    available: !workerBlocker && (workerHealthReady || workerResponseReady),
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

  // Mission sync effect. Order matters: the ignore flag must be consumed BEFORE
  // lastMissionRef.current is synced to the prop, otherwise an internal
  // emitMissionChange can be followed by a stale reset of the ref that breaks the
  // dedup gate in startAgentFromText.
  useEffect(() => {
    if (mission === lastMissionRef.current) return;
    if (ignoreNextMissionSyncRef.current) {
      ignoreNextMissionSyncRef.current = false;
      return;
    }
    lastMissionRef.current = mission;
    if (wishText.trim() || chatHistory.length > 0) return;
    setWishText(missionToWishText(mission));
  }, [chatHistory.length, mission, wishText]);

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
  const startAgentFromText = async (
    text: string,
    interpretedIntent: SovereignExecutorIntentKind,
  ): Promise<boolean> => {
    const intent = interpretedIntent;
    if (!effectiveRepoReady || !chatRepoSnapshot) {
      // Preserve the exact execution request across the repo gate. Loading the
      // repository is only a prerequisite; it must not erase the user's job.
      if (!pendingOnlineExecutionRef.current) pendingWriteIntentRef.current = text;
      appendActionEvent(buildBlockedActionEvent({ route: 'agent-job', label: 'Sovereign Agent Start blockiert', detail: 'Kein vollständiger Builder-Repo-Snapshot vorhanden; Auftrag für Wiederaufnahme vorgemerkt.', kind: 'blocked' }));
      setShowRepoSetup(true);
      appendRuntimeNotice('Executor blockiert: Bitte zuerst den Repository-Snapshot über das Repo-Setup laden. Der Auftrag bleibt für die automatische Wiederaufnahme vorgemerkt.');
      return false;
    }
    if (intent !== 'code_execution' && intent !== 'draft_pr') {
      appendActionEvent(buildBlockedActionEvent({ route: 'agent-job', label: 'Sovereign Agent Start blockiert', detail: 'Kein bestätigter Code- oder Draft-PR-Ausführungsauftrag.', kind: 'blocked' }));
      appendRuntimeNotice('Executor blockiert: Die strukturierte Intent-Evidence erlaubt keinen Code- oder Draft-PR-Start.');
      return false;
    }
    if (!(githubWriteAllowed || hasCurrentGitHubWriteEvidence())) {
      appendActionEvent({ kind: 'github_access_required', route: 'github-access', label: 'Executor braucht GitHub-Zugang', detail: 'Ausführungsauftrag erkannt, aber GitHub-Schreibzugang ist nicht validiert.', state: 'blocked' });
      if (!pendingOnlineExecutionRef.current) pendingWriteIntentRef.current = text;
      setShowGitHubAccessOverride(true);
      appendRuntimeNotice('GitHub-Zugang fehlt. Executor-Aktion blockiert: Vor dem Start muss der GitHub-Schreibzugang im sicheren Feld validiert werden.');
      return false;
    }

    const bypassPreflight = missionValidationBypassRef.current === text;
    if (bypassPreflight) {
      missionValidationBypassRef.current = null;
    } else {
      const validation = await requestMissionValidation(text);
      if (!validation.specificEnough) {
        setMissionValidationPending({ mission: text, intent, result: validation });
        appendActionEvent(buildBlockedActionEvent({
          route: 'agent-job',
          label: 'Mission Pre-flight Warnung',
          detail: `Spezifität ${validation.score}/100. Nutzerentscheidung vor Start erforderlich.`,
          kind: 'blocked',
        }));
        return false;
      }
    }
    setMissionValidationPending(null);

    const clean = collapseRepeatedAnalyzedMission(
      buildAnalyzedMission({
        wish: text,
        repoReady: true,
        repoReason: effectiveRepoReason,
      }),
    );
    if (lastMissionRef.current !== clean) {
      emitMissionChange(clean);
    }

    if (!onStartAgent) {
      appendActionEvent(buildBlockedActionEvent({
        route: 'agent-job',
        label: 'Executor-Start blockiert',
        detail: 'Kein bestätigter Produkt-Executor ist für diesen Auftrag verdrahtet.',
        kind: 'blocked',
      }));
      appendRuntimeNotice('Ausführungsauftrag kann nicht ausgeführt werden: Es ist kein bestätigter Produkt-Executor verbunden. Es wurde kein Job gestartet und keine Datei geändert.');
      addLog('error', 'Execution blocked: missing product executor callback', 'router');
      return false;
    }

    if (startAgentInFlightRef.current) {
      addLog('info', 'Agent start ignored while another start is in flight', 'router');
      return false;
    }
    startAgentInFlightRef.current = true;

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
        expectedHeadSha: chatRepoSnapshot.headSha,
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
      appendRuntimeNotice(`Sovereign Agent Runtime konnte nicht gestartet werden.
Grund: ${message}
Es wurde kein Job gestartet und keine Datei geändert.`);
      addLog('error', `Sovereign Agent start failed: ${message}`, 'router');
      return false;
    } finally {
      startAgentInFlightRef.current = false;
    }
  };

  const startAgentFromApprovedDraft = async (
    draft: IntegrationIntentDraft,
    interpretedIntent: 'code_execution' | 'draft_pr',
  ): Promise<boolean> => {
    const executionMission = draft.executionMission;
    const executionTarget = draft.executionTarget;
    if (
      draft.intentSource !== 'online_llm'
      || !executionMission
      || executionMission !== draft.originalText.trim()
      || !executionTarget
    ) {
      appendActionEvent(buildBlockedActionEvent({
        route: 'agent-job',
        label: 'Freigabevertrag ungültig',
        detail: 'Vorschau und Executor-Auftrag sind nicht identisch.',
        kind: 'blocked',
      }));
      appendRuntimeNotice('Start blockiert: Der freigegebene Auftrag ist nicht unverändert ausführbar.');
      return false;
    }
    if (!effectiveRepoReady || !chatRepoSnapshot) {
      setShowRepoSetup(true);
      appendRuntimeNotice('Start blockiert: Repository-Snapshot fehlt. Der Auftrag bleibt zur Freigabe sichtbar.');
      return false;
    }
    const targetStillMatches = (
      executionTarget.repoUrl === chatRepoSnapshot.repoUrl
      && executionTarget.branch === chatRepoSnapshot.branch
      && executionTarget.expectedHeadSha === chatRepoSnapshot.headSha.toLowerCase()
    );
    if (!targetStillMatches) {
      appendActionEvent(buildBlockedActionEvent({
        route: 'repo',
        label: 'Freigabe durch Repository-Drift abgelaufen',
        detail: 'Repository, Branch oder HEAD unterscheiden sich von der sichtbaren Vorschau.',
        kind: 'blocked',
      }));
      appendRuntimeNotice('Start blockiert: Repository-Stand hat sich geändert. Auftrag bitte erneut prüfen und freigeben.');
      return false;
    }
    if (!(githubWriteAllowed || hasCurrentGitHubWriteEvidence())) {
      setShowGitHubAccessOverride(true);
      appendActionEvent({
        kind: 'github_access_required',
        route: 'github-access',
        label: 'GitHub-Zugang erforderlich',
        detail: 'Zugang öffnen ist keine Aktionsfreigabe; der Auftrag bleibt ausstehend.',
        state: 'blocked',
      });
      return false;
    }
    if (!onStartAgent) {
      appendRuntimeNotice('Start blockiert: Kein bestätigter Workspace-Executor ist verbunden.');
      return false;
    }
    if (startAgentInFlightRef.current) {
      addLog('info', 'Approved draft start ignored while another start is in flight', 'router');
      return false;
    }

    setMissionValidationPending(null);
    if (lastMissionRef.current !== executionMission) {
      emitMissionChange(executionMission);
    }
    startAgentInFlightRef.current = true;
    clearPatchEvidence();
    appendActionEvent({
      kind: 'agent_job_requested',
      route: 'agent-job',
      label: 'Freigegebener Repository-Auftrag angefragt',
      detail: `Exakter Vorschautext wird an ${executionTarget.repoUrl}#${executionTarget.branch}@${executionTarget.expectedHeadSha} übergeben.`,
      state: 'queued',
    });

    try {
      await onStartAgent(executionMission, {
        repoUrl: executionTarget.repoUrl,
        branch: executionTarget.branch,
        expectedHeadSha: executionTarget.expectedHeadSha,
        githubAccessToken: githubTokenRef.current || undefined,
      });
      appendRuntimeNotice('Start angefragt. Ergebnis bleibt Draft PR; kein Auto-Merge.');
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
      appendRuntimeNotice(`Start fehlgeschlagen: ${message}`);
      return false;
    } finally {
      startAgentInFlightRef.current = false;
    }
  };


  const publishConfirmedDraftPr = async (): Promise<void> => {
    if (publishDraftPrInFlightRef.current) {
      addLog('info', 'Draft-PR publish ignored while another publish is in flight', 'router');
      return;
    }
    publishDraftPrInFlightRef.current = true;
    try {
      await publishConfirmedDraftPrInner();
    } finally {
      publishDraftPrInFlightRef.current = false;
    }
  };

  const publishConfirmedDraftPrInner = async (): Promise<void> => {
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
      appendRuntimeNotice('Draft PR blockiert: Es gibt noch keine bestätigte Änderung mit Runtime-Evidence.');
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

    if (scopedAgentJob?.jobId) {
      setAutoCodeReviewBusy(true);
      const review = await requestAutoCodeReview({
        jobId: scopedAgentJob.jobId,
        backendBase: SOVEREIGN_WORKER_BASE,
      });
      setAutoCodeReviewResult(review);
      setAutoCodeReviewBusy(false);
      if (review.decision === 'blocked_high') {
        appendActionEvent(buildBlockedActionEvent({
          route: 'agent-job',
          label: 'Draft PR durch Auto Code Review blockiert',
          detail: review.summary + (review.error ? ` Blocker: ${review.error}` : ''),
          kind: 'blocked',
        }));
        appendRuntimeNotice(review.summary);
        return;
      }
      if (review.decision === 'blocked_unavailable') {
        appendActionEvent(buildBlockedActionEvent({
          route: 'agent-job',
          label: 'UI-Review nicht verfügbar; Server-Gate bleibt autoritativ',
          detail: review.summary + (review.error ? ` Blocker: ${review.error}` : ''),
          kind: 'blocked',
        }));
      } else {
        appendActionEvent({
          kind: 'done',
          route: 'agent-job',
          label: 'Auto Code Review bestanden',
          detail: `${review.resolvedTransport} · ${review.modelUsed} · ${review.mediumCount} MEDIUM · ${review.lowCount} LOW`,
          state: 'done',
        });
      }
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
        expectedHeadSha: chatRepoSnapshot.headSha,
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
      appendRuntimeNotice(`Draft-PR-Übergabe fehlgeschlagen. Grund: ${message}`);
    }
  };

  const requestDraftPrActionPreview = () => {
    const hasStagedChanges = stagedChanges.length > 0;
    const hasAgentEvidence = Boolean(
      scopedAgentJob?.jobId && (scopedAgentJob.changedFiles?.length ?? 0) > 0,
    );
    if (
      !chatRepoSnapshot
      || !currentRepoScopeKey
      || (!hasStagedChanges && !hasAgentEvidence)
      || (hasStagedChanges && !patchConfirmed)
    ) {
      void publishConfirmedDraftPr();
      return;
    }

    setShowDraftPrActionPreview(true);
    appendActionEvent({
      kind: 'route_selected',
      route: 'github-patch',
      label: 'Draft-PR-Aktion zur Bestätigung bereit',
      detail: 'Die konkrete Repository-, Head- und Evidence-Vorschau wird vor der externen Draft-PR-Aktion angezeigt.',
      state: 'queued',
    });
  };

  const handleSubmit = async () => {
    const submittedText = wishText.trim();
    if (!submittedText || localRepoLoading || chatResponseBusy || isPublishing)
      return;
    void runSerializedSubmit(async () => {
      setWishText("");
      await _processSubmit(submittedText);
    });
  };

  // Retry submit with a specific message (used by WorkerBlockerCard and Banner)
  const retrySubmit = async (
    message: string,
    options: {
      readonly ignoreExistingWorkerBlocker?: boolean;
      readonly resumePendingIntent?: boolean;
    } = {},
  ) => {
    if (localRepoLoading || chatResponseBusy || isPublishing) return;
    void runSerializedSubmit(async () => {
      setWishText("");
      await _processSubmit(message, options);
    });
  };

  const _processSubmit = async (
    submittedText: string,
    options: {
      readonly ignoreExistingWorkerBlocker?: boolean;
      readonly resumePendingIntent?: boolean;
      readonly inputAlreadyRecorded?: boolean;
    } = {},
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

    // Exact machine controls are already typed. Let them continue to the
    // LLM-first/degraded executor boundary instead of treating them as unknown
    // generic slash commands. No free-language inference occurs here.
    const explicitRuntimeIntent = classifyOfflineSovereignExecutorIntent(submittedText);

    // ── Issue #428: Slash command handling
    if (submittedText.startsWith("/") && explicitRuntimeIntent === 'unknown') {
      const parsedSlash = parseSlashCommand(submittedText, skillSlashCommands);
      if (!parsedSlash) {
        appendRuntimeNotice(`Unbekannter Befehl. Verfügbare: ${[...SOVEREIGN_SLASH_COMMANDS, ...skillSlashCommands].map((c) => c.cmd).join(", ")}`);
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
        requestDraftPrActionPreview();
        return;
      }
      if (command.action === "repo") {
        if (!argument) {
          appendRuntimeNotice("Verwendung: /repo <GitHub-URL>");
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
        appendRuntimeNotice("Primary-Ansicht geleert. Der append-only PostgreSQL-Verlauf und Workflowzustand bleiben unverändert.");
        return;
      }
      if (command.action === "test") {
        if (!scopedAgentJob?.jobId) {
          appendRuntimeNotice('Test-Runner blockiert: Es gibt keinen echten Agent-Workspace-Job. Starte zuerst einen Repository-Auftrag.');
          return;
        }
        setTestRunnerBusy(true);
        const result = await runTests({
          jobId: scopedAgentJob.jobId,
          backendBase: SOVEREIGN_WORKER_BASE,
          testPath: argument || undefined,
        });
        setTestRunnerResult(result);
        setTestRunnerBusy(false);
        appendActionEvent({
          kind: result.status === 'passed' ? 'done' : result.status === 'failed' ? 'failed' : 'blocked',
          route: 'runtime',
          label: result.status === 'passed' ? 'Workspace-Tests bestanden' : 'Workspace-Testlauf beendet',
          detail: result.summary,
          state: result.status === 'passed' ? 'done' : result.status === 'failed' ? 'failed' : 'blocked',
        });
        addLog(result.status === 'passed' ? 'info' : 'warn', result.summary, 'orchestr');
        return;
      }
      if (command.action === "templates") {
        setShowPromptLibrary(true);
        return;
      }
      if (command.action === "export") {
        const current = persistedSessionRef.current;
        if (!current) {
          appendRuntimeNotice('Export blockiert: Für die aktuelle Ansicht existiert noch keine repo-gebundene Sitzung.');
          return;
        }
        const outcome = downloadSessionMarkdown(current);
        appendRuntimeNotice(outcome === 'downloaded'
          ? 'Sitzung als Markdown exportiert. Secret-Muster wurden im Export redigiert.'
          : 'Sitzungsexport ist in dieser Umgebung nicht verfügbar.');
        return;
      }
      if (command.action === "diff") {
        if (!scopedAgentJob?.jobId) {
          appendRuntimeNotice('Diff-Narrator blockiert: Es gibt keinen echten Agent-Workspace-Job.');
          return;
        }
        const result = await requestSemanticDiffNarration(scopedAgentJob.jobId);
        setSemanticDiffResult(result);
        if (!result.diffText.trim()) {
          appendRuntimeNotice(`Diff-Narrator ohne echte Diff-Evidence: ${result.error || 'kein Workspace-Diff'}`);
          return;
        }
        const report = buildGeneratedFileDiffReportFromUnifiedDiff(result.diffText);
        setPatchDiffReport(report);
        setPatchConfirmed(false);
        setShowPatchDiffEvidence(true);
        appendRuntimeNotice(result.ok
          ? `Semantic Diff Narrator: ${result.narratives.length} Datei-Erklärung(en) aus echter Workspace-Diff-Evidence.`
          : `Workspace-Diff geöffnet; Modell-Narration nicht verfügbar: ${result.error || 'unbekannter Blocker'}`);
        return;
      }
      if (command.action === "changelog") {
        if (!scopedAgentJob?.jobId) {
          appendRuntimeNotice('Changelog blockiert: Es gibt keinen echten Agent-Workspace-Job.');
          return;
        }
        const result = await fetchCommitsSince(scopedAgentJob.jobId, argument ? Number(argument) || 30 : 30);
        if (!result.ok) {
          appendRuntimeNotice(`Changelog blockiert: ${result.error || 'keine echte Git-Evidence'}`);
          return;
        }
        setChangelogResult(result);
        appendRuntimeNotice(`Changelog aus ${result.commitCount} realen Commit(s) erzeugt · Quelle ${result.source}.`);
        return;
      }
      if (command.action === "skills") {
        const active = installedSkills.filter((s) => s.is_active);
        if (active.length === 0) {
          appendRuntimeNotice("Keine Skills installiert. Nutze /scan-skills <owner/repo> um Skills aus einem Repo zu importieren.");
        } else {
          appendRuntimeNotice([
              `**${active.length} installierte Skills:**`,
              ...active.map((s) => `• \`/${s.slug}\` — ${s.description}`),
              "",
              "Tipp: /scan-skills <owner/repo> für mehr Skills.",
            ].join("\n"));
        }
        return;
      }
      if (command.action === "scan-skills") {
        setShowSkillScan(true);
        return;
      }
      if (command.action === "skill-run" && command.adapted_prompt) {
        triggerHaptic("light");
        if (!(await persistMissionInput(submittedText))) return;
        appendActionEvent({
          kind: 'route_selected',
          route: 'runtime',
          label: `Expliziter Skill gewählt: /${command.cmd.replace(/^\/+/, '')}`,
          detail: 'Der installierte Workflow wird über die normale Sovereign-Routing- und Evidence-Pipeline ausgeführt.',
          state: 'running',
        });
        const skillMission = buildExplicitSkillMission({
          name: command.label,
          slug: command.cmd,
          adaptedPrompt: command.adapted_prompt,
          argument,
          skillId: command.skill_id,
          sourceSha: command.source_sha,
          contentSha256: command.content_sha256,
        });
        await _processSubmit(skillMission, { inputAlreadyRecorded: true });
        return;
      }
    }

    // Haptic feedback for send (Issue #429)
    triggerHaptic("light");

    if (!options.resumePendingIntent && !options.inputAlreadyRecorded) {
      if (!(await persistMissionInput(submittedText))) return;
      appendActionEvent(buildInputReceivedEvent(submittedText));
    }

    // Natural language goes to the online LLM first. Deterministic parsing is
    // reserved strictly for exact machine controls, repository URLs and
    // machine-generated preset markers. Free user language is never reinterpreted
    // by browser heuristics when the online LLM is unavailable.
    const isSafeAnalysisPreset = submittedText.includes('Preset-Ausführungsmodus: safe_analysis');
    const isReviewableExecutionPreset =
      submittedText.includes('Risiko: reviewable_patch')
      || submittedText.includes('Risiko: executor_required');
    const directRepoUrl = parseDevChatGithubUrl(submittedText);
    // "Retry" is an exact UI control, not natural language. It replays the
    // last correlated request through the real pipeline and must never spend a
    // second interpretation call merely to understand the control itself.
    const isExactRetryControl = submittedText.trim().toLocaleLowerCase('de-DE') === 'retry';
    const shouldUseOnlineLanguageUnderstanding =
      !options.resumePendingIntent &&
      !isSafeAnalysisPreset &&
      !isReviewableExecutionPreset &&
      !directRepoUrl &&
      !isExactRetryControl;

    if (isReviewableExecutionPreset) {
      appendActionEvent(buildRouteSelectionEvent({
        route: 'sovereign-agent',
        reason: 'Vorgemerktes Review-Preset wird direkt über den Repository-Executor wiederaufgenommen; Browser-ARE wird nicht verwendet.',
        state: 'running',
      }));
      const started = await startAgentFromText(submittedText, 'code_execution');
      if (started) {
        appendRuntimeNotice('Der vorgemerkte Preset-Auftrag wurde an den revisionsgebundenen Repository-Executor übergeben. Ergebnis bleibt Draft PR; kein Auto-Merge.');
      }
      return;
    }

    // ── Issue #522 P2 Fix 2 & 3: Offline/local fallback routing
    // Status, diagnostic, and retry intents must be handled locally FIRST.
    // They should NOT create an integration draft card.
    // Order matters: local routes > createIntegrationIntentDraft > capability router

    // P2 Fix 2: Status questions - answered locally from runtime state
    if (!shouldUseOnlineLanguageUnderstanding && explicitRuntimeIntent === 'status') {
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
      appendRuntimeNotice(statusAnswer);
      setLastAnswerWasLocal(true);
      appendActionEvent(buildLocalRuntimeResultEvent({
        label: 'Status-Frage',
        detail: 'Lokale Antwort aus Runtime-State',
      }));
      addLog('info', 'Issue #522 P2 Fix 2: Status question handled locally - no draft created', 'router');
      return;
    }

    // P2 Fix 2: Worker retry intents - clear blocker and trigger real retry
    // Runtime-Truth: Retry must produce Action → Request → Response, not just UI reset
    if (isExactRetryControl && routingWorkerBlocker) {
      if (lastWorkerRequestMessage) {
        // Real retry: re-submit the last request through the full pipeline
        setWorkerBlocker(null);
        appendRuntimeNotice('Worker-Blocker zurückgesetzt. Retry wird ausgeführt...');
        appendActionEvent(buildLocalRuntimeResultEvent({
          label: 'Retry gestartet',
          detail: 'Worker-Blocker zurückgesetzt; letzter Request wird erneut ausgeführt',
        }));
        addLog('info', 'Issue #522 P2 Fix 2: Retry intent triggers real retry via retrySubmit', 'router');
        await _processSubmit(lastWorkerRequestMessage, { ignoreExistingWorkerBlocker: true });
        return;
      } else {
        // Honest state: no prior request to retry
        appendRuntimeNotice('Worker-Blocker zurückgesetzt. Es gibt keinen vorherigen Request zum Wiederholen.');
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

    if (isExactRetryControl && !routingWorkerBlocker) {
      appendRuntimeNotice('Retry ist ein exakter Runtime-Befehl, aber es gibt keinen aktiven korrelierten Blocker zum Wiederholen. Es wurde kein LLM-Aufruf gestartet.');
      appendActionEvent(buildLocalRuntimeResultEvent({
        label: 'Retry ohne Ziel',
        detail: 'Kein aktiver korrelierter Blocker; keine Aktion ausgeführt.',
      }));
      return;
    }

    // Online-first language understanding: the LLM interprets natural language;
    // the application remains the sole authority for capabilities, execution and success.
    // Local token classifiers are used only when the online interpreter is unavailable.
    if (shouldUseOnlineLanguageUnderstanding) {
      if (!authUser) {
        appendActionEvent(buildBlockedActionEvent({
          route: 'worker',
          label: 'Anmeldung für Online-Sprachdeutung erforderlich',
          detail: 'Der geschützte OpenRouter-/FreeLLM-Backendpfad wurde ohne bestätigte Session nicht aufgerufen.',
          kind: 'blocked',
        }));
        appendRuntimeNotice('Für die Online-Sprachdeutung ist eine bestätigte Anmeldung erforderlich. Es wurde kein LLM-Aufruf gesendet und kein Credit abgezogen.');
        setShowLogin(true);
        return;
      }

      let onlineAreInference: AreInferenceResult | null = null;
      let onlineHealth: DevChatWorkerHealthResult | null = null;

      const routeDecision = palRoute(
        submittedText,
        chatHistory.length + 1,
        chatRepoSnapshot?.fileCount ?? 0,
        palDecisions,
      );
      const selectedInterpretationRoute = selectedLlmRouteId
        ? llmRouteOptions.find((route) => route.id === selectedLlmRouteId)
        : undefined;
      const requestedInterpretationModel = selectedLlmRouteId || routeDecision.modelId;
      const requestedInterpretationLabel = selectedLlmRouteId
        ? selectedInterpretationRoute
          ? `${selectedInterpretationRoute.provider} · ${selectedInterpretationRoute.label}`
          : `Backend-Route ${selectedLlmRouteId}`
        : routeDecision.modelLabel;
      const interpreterOnline = true;
      let interpretationResult: Awaited<ReturnType<typeof fetchSovereignDirectLlmInterpretation>>;

      if (interpreterOnline) {
        // LLM billing is owned by /api/llm/chat. Free routes reserve zero credits;
        // paid OpenRouter routes are reserved and settled from real provider
        // evidence there. A client-side pre-charge would bypass the free revolver
        // and is forbidden by the current backend billing contract.
        if (!selectedLlmRouteId) {
          setPalDecisions((previous) => [...previous.slice(-99), routeDecision]);
          setBudgetLedger((previous) => recordRouteUsage(previous, routeDecision.tier));
        } else {
          addLog('info', `Manuelle LLM-Route → ${requestedInterpretationLabel} · Intent`, 'router');
        }
        if (!routingWorkerBlocker || options.ignoreExistingWorkerBlocker) {
          setLastWorkerRequestMessage(submittedText);
        }
        setChatResponseBusy(true);
        appendActionEvent(buildWorkerRequestEvent(`${requestedInterpretationLabel} · Intent`));

        interpretationResult = await fetchSovereignDirectLlmInterpretation({
          preferredModel: requestedInterpretationModel,
          text: submittedText,
          repoContext: chatRepoSnapshot
            ? `${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo}#${chatRepoSnapshot.branch} · ${chatRepoSnapshot.fileCount} files`
            : undefined,
          runtimeContext: [
            `repo_ready=${effectiveRepoReady}`,
            `github_write_ready=${githubWriteAllowed}`,
            `github_access_state=${effectiveGitHubAccessState}`,
            `agent_state=${scopedAgentJob?.status ?? agentWorkSnapshot.state}`,
            `changed_files=${scopedAgentJob?.changedFiles?.length ?? 0}`,
            `draft_pr_ready=${Boolean(scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl)}`,
            `patch_preview_ready=${patchPreviewReady}`,
            `patch_confirmed=${patchConfirmed}`,
            `worker_health=${onlineHealth?.ok === true ? 'ready' : onlineHealth?.ok === false ? 'blocked' : 'unknown'}`,
          ].join('\n'),
        });
        setChatResponseBusy(false);
      } else {
        interpretationResult = {
          ok: false,
          error: onlineHealth?.error || 'Strukturierte Online-Aktionsroute ist nicht erreichbar.',
          diagnostic: {
            route: SOVEREIGN_WORKER_CHAT,
            model: requestedInterpretationModel,
            messageCount: 0,
            status: onlineHealth?.status,
            scope: 'network',
            canClientFix: false,
            nextAction: 'Online-Aktionsroute prüfen; keine lokale Sprachdeutung oder Ausführung starten.',
          },
        };
      }

      if (interpretationResult.ok && interpretationResult.interpretation) {
        const interpretation = interpretationResult.interpretation;
        // A successful advisory/status interpretation does not prove that the
        // previously failed correlated request was repaired. Only a successful
        // actionable request or an explicit retry may clear that blocker.
        if (interpretation.mode === 'action' || options.ignoreExistingWorkerBlocker) {
          setWorkerBlocker(null);
          setLastWorkerRequestMessage(null);
        }
        appendActionEvent(buildWorkerResponseEvent());
        appendActionEvent({
          kind: 'capability_checked',
          route: 'runtime',
          label: 'Online-Intent-Evidence empfangen',
          detail: `${interpretation.intent} · confidence=${interpretation.confidence.toFixed(2)} · model=${interpretation.model}`,
          state: 'done',
        });

        const actionableIntent = mapInterpretedIntentToExecutorIntent(interpretation.intent);
        const isAction = interpretation.mode === 'action'
          && actionableIntent !== null
          && actionableIntent !== 'question'
          && actionableIntent !== 'status';

        if (!isAction) {
          appendRuntimeNotice(interpretation.assistantText);
          appendActionEvent({
            kind: 'capability_checked',
            route: 'runtime',
            label: 'Gegenfrage erforderlich',
            detail: 'Der strukturierte Codeauftragsvertrag enthält noch keinen ausführbaren Auftrag.',
            state: 'blocked',
          });
          return;
        }

        const draft = chatRepoSnapshot
          ? createStructuredIntegrationIntentDraft(
              submittedText,
              {
                intentKind: interpretation.intent,
                confidence: interpretation.confidence,
                model: interpretation.model,
                actionTitle: interpretation.actionTitle,
              },
              {
                repoUrl: chatRepoSnapshot.repoUrl,
                branch: chatRepoSnapshot.branch,
                expectedHeadSha: chatRepoSnapshot.headSha,
              },
            )
          : null;
        if (!draft) {
          const clarification = effectiveRepoReady && chatRepoSnapshot
            ? `Welche konkrete Änderung soll ich in ${chatRepoSnapshot.owner}/${chatRepoSnapshot.repo} vorbereiten, und welches Ergebnis soll ich danach prüfen?`
            : 'Welches Repository soll ich ändern, und was soll danach konkret anders sein?';
          appendRuntimeNotice(clarification);
          appendActionEvent({
            kind: 'blocked',
            route: 'runtime',
            label: 'Codeauftrag unvollständig',
            detail: 'Keine Ausführung; konkrete Gegenfrage angezeigt.',
            state: 'blocked',
          });
          return;
        }

        appendActionEvent(buildDraftCreatedEvent(draft));
        setIntentDraftState({ status: 'pending', draft });
        appendRuntimeNotice(`Freigabe erforderlich: ${draft.title}`);
        addLog('info', `Structured code action ready for review: ${draft.title} · model=${interpretation.model}`, 'router');
        return;
      }

      if (!routingWorkerBlocker || options.ignoreExistingWorkerBlocker) {
        setLastWorkerRequestMessage(submittedText);
      }
      const diagnostic = interpretationResult.diagnostic;
      if (diagnostic?.scope === 'authentication' && diagnostic.status === 401) {
        await refreshUser();
        setShowLogin(true);
      }
      const health: DevChatWorkerHealthResult = onlineHealth ?? {
        ok: false,
        route: SOVEREIGN_WORKER_HEALTH,
        status: diagnostic?.status,
        error: interpretationResult.error || diagnostic?.nextAction,
      };
      const offlineMachineIntent = resolveOfflineMachineExecutorIntent(explicitRuntimeIntent);
      if (offlineMachineIntent) {
        setWorkerHealthEvidence(health);
        addLog(
          'warn',
          'Online code-action contract unavailable; exact typed machine control routed to bounded executor.',
          'router',
        );
        await startAgentFromText(submittedText, offlineMachineIntent);
        return;
      }
      setWorkerHealthEvidence(health);
      const blocker: WorkerRuntimeBlocker = {
        message: interpretationResult.error || 'Strukturierter Codeauftrag nicht verfügbar.',
        diagnostic: diagnostic ?? {
          route: SOVEREIGN_WORKER_CHAT,
          model: requestedInterpretationModel,
          messageCount: 0,
          scope: 'worker_runtime',
          canClientFix: false,
          nextAction: 'Strukturierte Aktionsroute prüfen.',
        },
        health,
        createdAt: Date.now(),
      };
      setWorkerBlocker(blocker);
      const diagnosticText = [
        interpretationResult.error,
        diagnostic?.bodySnippet,
        diagnostic?.nextAction,
      ].filter(Boolean).join(' ');
      const clarification = !effectiveRepoReady
        ? 'Welches Repository soll ich ändern?'
        : diagnostic?.status === 428
          ? 'Die gewählte Route benötigt eine Kostenfreigabe. Soll ich die Freigabevorschau öffnen?'
          : selectedLlmRouteId && /nicht.*(vertrag|route)|not_supported|keine explizit freigegebene route/i.test(diagnosticText)
            ? 'Die fixierte Route unterstützt sichere Codeaufträge nicht. Welche verifizierte Route soll ich verwenden?'
            : 'Die sichere Online-Aktionsroute ist blockiert. Soll ich denselben Auftrag mit Auto/Revolver erneut versuchen?';
      appendRuntimeNotice(clarification);
      appendActionEvent({
        kind: 'blocked',
        route: 'worker',
        label: 'Codeauftragsvertrag blockiert',
        detail: interpretationResult.error || 'Keine gültige strukturierte Aktionsantwort.',
        state: 'blocked',
      });
      addLog('warn', 'Structured code action unavailable; no provider prose or offline interpretation accepted.', 'router');
      return;
    }

    // ── Issue #502: Sovereign Capability Router
    // Central routing decision using real runtime state.
    // BuilderContainer shows the decision; it does not create it.
    const capabilityRouterInput: CapabilityRouterInput = {
      language: buildExplicitRuntimeCapabilityLanguageEvidence({
        text: submittedText,
        intent: explicitRuntimeIntent,
        repositoryUrl: Boolean(directRepoUrl),
        safeAnalysisPreset: isSafeAnalysisPreset,
        retryControl: isExactRetryControl,
      }),
      repoReady: effectiveRepoReady,
      githubAccessState: effectiveGitHubAccessState,
      agentReady: agentReady ?? false,
      directGitHubPatchReady: false,
      workspaceReady: false, // Workspace executor not yet integrated
      hasActiveWorkerBlocker: Boolean(routingWorkerBlocker),
      hasPackage: Boolean(scopedAgentJob?.changedFiles?.length),
      hasDraft: Boolean(scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl),
      hasWorkflowReport: Boolean(agentWorkSnapshot.commitSha),
    };
    const capabilityDecision = decideSovereignCapabilityRoute(capabilityRouterInput);

    // Emit the runtime-typed action event. Capability routes are mapped to the
    // canonical Action Stream route vocabulary inside the router runtime.
    const routeActionEvent = buildCapabilityRouteActionEvent(
      capabilityDecision,
      agentWorkSnapshot.traceId,
      agentWorkSnapshot.events.length,
    );
    appendActionEvent(routeActionEvent);

    // A queued prerequisite is not execution permission. Log the concrete phase
    // so `allowed=true` can never look like success next to package_required.
    const capabilityPhase = capabilityDecision.blocker
      ? capabilityDecision.allowed
        ? 'queued_prerequisite'
        : 'blocked'
      : capabilityDecision.allowed
        ? 'executable'
        : 'blocked';
    addLog(
      "info",
      `Capability Router: route=${capabilityDecision.route} phase=${capabilityPhase} blocker=${capabilityDecision.blocker ?? 'none'} next=${capabilityDecision.nextAction}`,
      "router",
    );

    // ── Issue #502: Blocked capability decisions stop legacy routing.
    // Recoverable blockers persist the original intent and wait for real repo
    // or GitHub-access evidence before the same pipeline is resumed.
    if (!capabilityDecision.allowed) {
      if (capabilityDecision.blocker === 'repo_missing') {
        pendingWriteIntentRef.current = submittedText;
        setRepoSetupError(null);
        setShowRepoSetup(true);
        appendRuntimeNotice(`Route blockiert: ${capabilityDecision.reason}\nDas Repo-Setup wurde geöffnet; der Auftrag bleibt für die Wiederaufnahme vorgemerkt.`);
        addLog("warn", "Capability Router blocked: repo missing; intent persisted", "router");
        return;
      }
      if (capabilityDecision.blocker === 'github_access_missing') {
        pendingWriteIntentRef.current = submittedText;
        setShowGitHubAccessOverride(true);
        appendRuntimeNotice(`Route blockiert: ${capabilityDecision.reason}\nDer Auftrag bleibt vorgemerkt und wird erst nach bestätigter GitHub-API-Evidence fortgesetzt.`);
        addLog("warn", "Capability Router blocked: GitHub access missing; intent persisted", "router");
        return;
      }
      if (capabilityDecision.blocker === 'github_access_validating') {
        pendingWriteIntentRef.current = submittedText;
        appendRuntimeNotice(`Route blockiert: ${capabilityDecision.reason}\nDer Auftrag bleibt bis zum Ergebnis der laufenden Zugangsprüfung vorgemerkt.`);
        addLog("info", "Capability Router waiting for GitHub validation; intent persisted", "router");
        return;
      }
      // Unknown intents fail closed. The Worker must not invent a route for an
      // input that the capability runtime could not classify.
      if (capabilityDecision.blocker === 'unsupported_intent') {
        appendRuntimeNotice(`Route blockiert: ${capabilityDecision.reason}`);
        addLog("warn", "Capability Router: unsupported intent blocked; no Worker call", "router");
        return;
      }
      // Default: Block with clear message
      else {
        const blockerMessage = capabilityDecision.blocker
          ? `Route blockiert: ${capabilityDecision.reason}`
          : `Auftrag nicht erlaubt: ${capabilityDecision.reason}`;
        appendRuntimeNotice(blockerMessage);
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
        appendRuntimeNotice(statusAnswer);
        setLastAnswerWasLocal(true);
        addLog('info', 'Capability Router: local-runtime-answer terminal decision completed', 'router');
        return;
      }
      addLog("info", `Capability Router: terminal decision (${String(capabilityDecision.route)}), routing complete`, "router");
      return;
    }

    const advisoryWorkerRoute = capabilityDecision.route === 'worker-chat'
      && capabilityDecision.capability === 'free_chat';

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
        setValidatedGitHubTargetKey(null);
        setGitHubAccessState(createGitHubAccessSnapshot());
        setActionStream(createSovereignActionStreamState());
        setStatusLogs([]);
        setWorkerBlocker(null);
        setLastWorkerRequestMessage(null);
        setLastAnswerWasLocal(false);
        // Repository replacement is the causal point that invalidates an open
        // explorer. Closing here prevents the later scope effect from racing a
        // file-badge click rendered from the newly loaded snapshot.
        setShowRepoExplorer(false);
        setChatRepo(result.snapshot);
        triggerHaptic("medium");
        const summary = summarizeDevChatRepoSnapshot(result.snapshot);
        appendActionEvent(buildRepoLoadedEvent(summary));
        appendRuntimeNotice(`Repo geladen. ${summary}\nTop-Level: ${result.snapshot.dirs.join(" · ") || "keine Top-Level-Ordner erkannt"}\nDer Repo-Snapshot bleibt Runtime-Kontext und wird nicht in die Eingabezeile geschrieben.`);
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
      appendRuntimeNotice(`Repo-Laden blockiert: ${errorText}`);
      return;
    }

    // From this point onward the browser may only execute a route that was
    // already typed by an exact runtime control/preset. It must never recover
    // an execution intent by inspecting the wording of free user language.
    if (!advisoryWorkerRoute) {
      const typedExecutorIntent: SovereignExecutorIntentKind | null =
        capabilityDecision.capability === 'draft_pr'
          ? 'draft_pr'
          : capabilityDecision.capability === 'code_patch_plan'
            || capabilityDecision.capability === 'isolated_workspace'
            ? 'code_execution'
            : capabilityDecision.capability === 'direct_github_patch'
              ? 'direct_patch'
              : null;

      if (
        capabilityDecision.allowed
        && capabilityDecision.route === 'sovereign-agent'
        && (typedExecutorIntent === 'code_execution' || typedExecutorIntent === 'draft_pr')
      ) {
        const started = await startAgentFromText(submittedText, typedExecutorIntent);
        if (started) {
          appendRuntimeNotice('Der exakt typisierte Runtime-Befehl wurde an den Repository-Executor übergeben. Erfolg bleibt bis zu bestätigter Runtime-Evidence offen; Ergebnis bleibt Draft PR.');
        }
        return;
      }

      appendRuntimeNotice(`Runtime-Aktion nicht ausgeführt: ${capabilityDecision.reason}. Nächste Aktion: ${capabilityDecision.nextAction}. Freie Sprache wurde nicht lokal interpretiert.`);
      return;
    }

    // ── Aufgabe 2: Local completion-status questions
    // NOTE: Handled earlier in the flow (see Issue #522 P2 Fix 2 above)
    // to ensure status questions don't create integration drafts.

    // Exact typed runtime commands returned above. This continuation is advisory-only:
    // natural language stays on the LLM route and cannot be reinterpreted by browser/runtime heuristics.

    // ── Aufgabe 6: Write-intent result gate. GitHub write access is verified
    // above, but a mere Worker text response still must not be treated as
    // "done" — the result gate (sovereignActionStreamRuntime) requires a
    // patch/diff, Draft PR, or an explicit blocked/access_required state
    // before the write intent can be considered resolved.

    // ARE is evaluated before credit deduction and before any online call.
    // Reference knowledge includes uploaded PDFs; experience remains a separate,
    // evidence-accepted memory. No local synthesis capability is claimed yet.
    let areInferenceResult: AreInferenceResult | null = null;
    let referenceKnowledgeContext = '';
    let experiencePatternContext = '';
    if (authUser) {
      try {
        const workerHealthForInference = await fetchDevChatWorkerHealth();
        setWorkerHealthEvidence(workerHealthForInference);
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
          appendRuntimeNotice('ARE-Lokalroute blockiert: Im Builder ist noch kein bestätigter lokaler Code-Ausführungsadapter verbunden. Es wurde kein Credit abgezogen und kein Online-Call gestartet.');
          return;
        }
        if (areInferenceResult.decision === 'blocked') {
          appendActionEvent(buildBlockedActionEvent({
            route: 'runtime',
            label: 'ARE-Inferenz blockiert',
            detail: areInferenceResult.reasons.join(' · '),
            kind: 'blocked',
          }));
          appendRuntimeNotice('ARE-Inferenz blockiert: Die App ist offline und es ist noch kein belastbarer lokaler Code-Synthese-Adapter installiert. PDF- und Erfahrungswissen bleiben erhalten; es wurde kein Credit abgezogen und kein Online-Call gestartet.');
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
        appendRuntimeNotice(`ARE-Inferenz ist nicht verfügbar. Der Auftrag wurde vor Credit-Abzug und Online-Call gestoppt.\nGrund: ${message}`);
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

    // Route selection is followed directly by /api/llm/chat. The backend owns
    // free-vs-paid selection and provider-evidence settlement; the Android/Web
    // client must never pre-charge an abstract Sovereign alias.
    const d = palRoute(
      submittedText,
      chatHistory.length + 1,
      chatRepoSnapshot?.fileCount ?? 0,
      palDecisions,
    );
    const selectedChatRoute = selectedLlmRouteId
      ? llmRouteOptions.find((route) => route.id === selectedLlmRouteId)
      : undefined;
    const requestedChatModel = selectedLlmRouteId || d.modelId;
    const requestedChatLabel = selectedLlmRouteId
      ? selectedChatRoute
        ? `${selectedChatRoute.provider} · ${selectedChatRoute.label}`
        : `Backend-Route ${selectedLlmRouteId}`
      : d.modelLabel;

    if (!selectedLlmRouteId) {
      setPalDecisions((prev) => [...prev.slice(-99), d]);
      setBudgetLedger((prev) => recordRouteUsage(prev, d.tier));
      addLog("info", `PAL → ${d.tier} · ${d.modelLabel}`, "sys");
    } else {
      addLog('info', `Manuelle LLM-Route → ${requestedChatLabel}`, 'router');
    }
    appendActionEvent(buildWorkerRequestEvent(requestedChatLabel));

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
          model: requestedChatModel,
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
      let textToAppend = fullText;
      
      if (streamFallbackMetadata?.fallbackUsed) {
        textToAppend += `\n\n_Hinweis: ${streamFallbackMetadata.preferredModel} war nicht erreichbar, Antwort kam von ${streamFallbackMetadata.actualModel}._`;
      }

      appendGuardedWorkerText(textToAppend);
      await quarantineOnlineAnswer(fullText, streamFallbackMetadata?.actualModel ?? requestedChatModel);
      return;
    }

    const fallback = streamDiagnostic
      ? null
      : await fetchDevChatWorkerReply({
          model: requestedChatModel,
          messages: workerMessages,
        });

    if (fallback?.ok && fallback.content) {
      setWorkerBlocker(null);
      appendActionEvent(buildWorkerResponseEvent());
      let textToAppend = fallback.content;

      if (fallback.fallbackUsed) {
        textToAppend += `\n\n_Hinweis: ${fallback.preferredModel} war nicht erreichbar, Antwort kam von ${fallback.actualModel}._`;
      }

      appendGuardedWorkerText(textToAppend);
      await quarantineOnlineAnswer(fallback.content, fallback.actualModel ?? requestedChatModel);
      return;
    }

    const health = await fetchDevChatWorkerHealth();
    setWorkerHealthEvidence(health);
    const diagnostic = streamDiagnostic ??
      fallback?.diagnostic ?? {
        route: SOVEREIGN_WORKER_CHAT,
        model: requestedChatModel,
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
    appendRuntimeNotice(buildWorkerBlockerAnswer({
        blocker,
        repoReady: effectiveRepoReady,
        chatRepoSnapshot,
        agentReady,
      }));
    addLog(
      "error",
      `Worker blocked · ${diagnostic.scope}${diagnostic.status ? ` · HTTP ${diagnostic.status}` : ""}`,
      "router",
    );
  };

  const runSerializedSubmit = async (
    submit: () => Promise<void>,
    options: { readonly retryPendingOnReject?: boolean } = {},
  ): Promise<boolean> => {
    if (submitInFlightRef.current) {
      if (options.retryPendingOnReject) pendingResumeRetryRef.current = true;
      addLog('info', 'Submit ignored while another route is active', 'router');
      return false;
    }

    submitInFlightRef.current = true;
    try {
      await submit();
      return true;
    } finally {
      submitInFlightRef.current = false;
      if (pendingResumeRetryRef.current) {
        pendingResumeRetryRef.current = false;
        setPendingResumeRetrySequence((sequence) => sequence + 1);
      }
    }
  };

  useEffect(() => {
    const pendingOnlineExecution = pendingOnlineExecutionRef.current;
    const pendingWriteIntent = pendingWriteIntentRef.current;
    const pendingRepoIntent = pendingRepoIntentRef.current;
    if ((!pendingOnlineExecution && !pendingWriteIntent && !pendingRepoIntent) || !effectiveRepoReady) return;
    if (localRepoLoading || chatResponseBusy || isPublishing) return;
    // Write/executor work wakes only when its OWN write gate is proven. A repo
    // load or unrelated LLM reply must never resume a stale mutation request.
    if ((pendingOnlineExecution || pendingWriteIntent) && !(githubWriteAllowed || hasCurrentGitHubWriteEvidence())) {
      setShowGitHubAccessOverride(true);
      return;
    }

    void runSerializedSubmit(async () => {
      const currentOnlineExecution = pendingOnlineExecutionRef.current;
      const currentPendingWriteIntent = pendingWriteIntentRef.current;
      const currentPendingRepoIntent = pendingRepoIntentRef.current;
      if (!currentOnlineExecution && !currentPendingWriteIntent && !currentPendingRepoIntent) return;

      pendingOnlineExecutionRef.current = null;
      pendingWriteIntentRef.current = null;
      pendingRepoIntentRef.current = null;
      setShowGitHubAccessOverride(false);
      appendActionEvent({
        kind: 'route_selected',
        route: 'runtime',
        label: 'Blockierter Auftrag wird wiederaufgenommen',
        detail: currentPendingRepoIntent
          ? 'Der benötigte Repository-Snapshot ist jetzt belegt.'
          : 'Repository und Schreibzugang sind jetzt durch Runtime-Evidence belegt.',
        state: 'running',
      });
      addLog('info', 'Pending intent resumed only after its required runtime gate changed', 'router');
      if (currentOnlineExecution) {
        const started = await startAgentFromText(currentOnlineExecution.text, currentOnlineExecution.intent);
        if (!started && !(githubWriteAllowed || hasCurrentGitHubWriteEvidence())) {
          pendingOnlineExecutionRef.current = currentOnlineExecution;
        }
        return;
      }
      const currentIntent = currentPendingWriteIntent ?? currentPendingRepoIntent;
      if (currentIntent) await _processSubmit(currentIntent, { resumePendingIntent: true });
    }, { retryPendingOnReject: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveRepoReady, githubWriteAllowed, hasCurrentGitHubWriteEvidence, localRepoLoading, chatResponseBusy, isPublishing, pendingResumeRetrySequence]);

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
    void runSerializedSubmit(() => _processSubmit(clean));
  };

  const processPresetActionSelect = async (actionId: SovereignPresetActionId) => {
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

    if (!(await persistMissionInput(submitted))) return;
    appendActionEvent(buildInputReceivedEvent(submitted));

    if (!gate.canStart) {
      if (action.requiresRepo && !effectiveRepoReady) {
        if (action.requiresGithubWrite) pendingWriteIntentRef.current = submitted;
        else pendingRepoIntentRef.current = submitted;
        setRepoSetupError(null);
        setShowRepoSetup(true);
        appendActionEvent(buildBlockedActionEvent({
          route: 'repo',
          label: `Preset wartet auf Repo: ${action.shortLabel}`,
          detail: `${gate.reason} ${gate.nextAction}`,
          kind: 'blocked',
        }));
        appendRuntimeNotice(`${action.icon} ${action.label}
Status: ${gate.reason}
Das echte Repo-Setup wurde geöffnet.`);
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
        appendRuntimeNotice(
          `${action.icon} ${action.label}\nStatus: ${gate.reason}\nDer Auftrag wartet auf bestätigten GitHub-Schreibzugang.`,
        );
        addLog('warn', `Preset write action blocked: GitHub access gate opened for ${action.id}`, 'router');
        return;
      }

      appendActionEvent(buildBlockedActionEvent({
        route: action.requiresRepo ? 'repo' : 'runtime',
        label: `Preset blockiert: ${action.shortLabel}`,
        detail: `${gate.reason} ${gate.nextAction}`,
        kind: action.requiresGithubWrite ? 'access_required' : 'blocked',
      }));
      appendRuntimeNotice([
          `${action.icon} ${action.label}`,
          `Status: ${gate.reason}`,
          `Nächste Aktion: ${gate.nextAction}`,
        ].join('\n'));
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
          appendRuntimeNotice(`PR-Review blockiert: ${detail}\nEs wurde kein GitHub-Schreibzugang angefordert, kein Executor gestartet und kein LLM-Credit verbraucht.`);
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
        appendRuntimeNotice(formatOpenPrReviewEvidence(review.evidence));
        setLastAnswerWasLocal(true);
        addLog('info', `Open PR review completed read-only: ${review.evidence.openPrCount} PR(s)`, 'router');
        return;
      }

      await _processSubmit(submitted, { inputAlreadyRecorded: true });
      return;
    }

    appendActionEvent(buildRouteSelectionEvent({
      route: 'sovereign-agent',
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
      appendRuntimeNotice(effectiveGitHubAccessState === 'ready'
          ? 'GitHub-Zugang ist validiert. Secret-Werte werden weder angezeigt noch im Chat gespeichert.'
          : 'GitHub-Zugang wird bereits geprüft. Es wurde keine zweite Validierung gestartet.');
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
  const showAgentEventStream = liveMonitorPrimary || agentWorkSnapshot.state !== 'idle' || scopedAgentIsRunning;
  const agentEventStream = showAgentEventStream ? (
    <AgentEventStream
      snapshot={agentWorkSnapshot}
      job={scopedAgentJob}
      projections={scopedAgentProjections}
      evidenceAnchors={scopedAgentEvidenceAnchors}
      onCancel={onCancelAgent}
      onOpenDraftPr={
        (() => {
          const rawUrl = scopedAgentJob?.draftPrUrl ?? agentWorkSnapshot.draftPrUrl;
          const safeUrl = rawUrl ? safeHttpsUrl(rawUrl) : null;
          return safeUrl ? () => window.open(safeUrl, '_blank', 'noopener,noreferrer') : undefined;
        })()
      }
      onOpenFile={openRepoExplorerFromFileBadge}
      primaryMonitor={liveMonitorPrimary}
      desktopFrame={scopedDesktopFrame}
    />
  ) : null;
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
      data-layout={liveMonitorPrimary ? "live-desktop-monitor-primary" : "monitor-inspector-modules"}
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
          <div
            role="region"
            aria-label="Sovereign Live Desktop Monitor"
            data-testid="sovereign-live-monitor-primary"
            data-primary-surface="desktop-monitor"
            style={{
              flex: 1,
              minWidth: 0,
              minHeight: 0,
              overflowX: "hidden",
              overflowY: "auto",
              overscrollBehavior: "contain",
              background: C.bg,
              display: "flex",
              flexDirection: "column",
            }}
          >
            {agentEventStream}
            <LauncherTaskbar />
            <div
              data-testid="monitor-action-controls"
              style={{
                flexShrink: 0,
                borderTop: `1px solid ${C.border}`,
                background: C.surface,
              }}
            >
              <ActionSuggestionStrip
                actions={SOVEREIGN_PRESET_ACTIONS}
                repoReady={effectiveRepoReady}
                githubWriteReady={githubWriteAllowed}
                agentReady={agentReady ?? false}
                disabled={localRepoLoading || chatResponseBusy || isPublishing}
                onSelect={handlePresetActionSelect}
              />
            </div>
            <div
              data-testid="monitor-runtime-action-trace"
              style={{
                flexShrink: 0,
                maxHeight: 132,
                overflowY: 'auto',
                borderTop: actionStream.events.length ? `1px solid ${C.border}` : undefined,
                background: C.bg,
              }}
            >
              <SovereignActionStreamPanel stream={actionStream} maxEvents={12} />
            </div>
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
            {hasPendingDraft(intentDraftState) && (() => {
              const draft = intentDraftState.draft;
              const mappedIntent = mapInterpretedIntentToExecutorIntent(draft.intentKind);
              const executionIntent: 'code_execution' | 'draft_pr' = mappedIntent === 'draft_pr'
                ? 'draft_pr'
                : 'code_execution';
              const gateSnapshot: IntegrationIntentDraftGateSnapshot = {
                repoReady: effectiveRepoReady,
                githubWriteReady: githubWriteAllowed,
                directPatchReady: false,
                agentReady: sovereignAgentStartAvailable,
              };
              return (
                <IntegrationIntentDraftCard
                  draft={draft}
                  gateSnapshot={gateSnapshot}
                  canConfirm={effectiveRepoReady && githubWriteAllowed && sovereignAgentStartAvailable}
                  confirmBlocker={!effectiveRepoReady
                    ? 'Repository-Snapshot fehlt.'
                    : !sovereignAgentStartAvailable
                      ? 'Backend-Workspace-Executor ist nicht verbunden.'
                      : undefined}
                  onConfirm={() => {
                    appendActionEvent(buildDraftConfirmedEvent(draft));
                    setIntentDraftState({ status: 'confirmed', draft });
                    void startAgentFromApprovedDraft(draft, executionIntent)
                      .finally(() => setIntentDraftState({ status: 'idle' }));
                  }}
                  onConfirmWithGitHubAccess={() => {
                    setShowGitHubAccessOverride(true);
                    appendActionEvent({
                      kind: 'github_access_required',
                      route: 'github-access',
                      label: 'GitHub-Zugang geöffnet',
                      detail: 'Nur der Zugang wird geprüft; der Repository-Auftrag bleibt unbestätigt.',
                      state: 'blocked',
                    });
                  }}
                  onRephrase={() => {
                    appendActionEvent(buildDraftRephrasedEvent(draft));
                    setWishText(draft.rephrasedText);
                    setIntentDraftState({ status: 'idle' });
                  }}
                  onReject={() => {
                    appendActionEvent(buildDraftRejectedEvent());
                    setIntentDraftState({ status: 'idle' });
                    appendRuntimeNotice('Runtime-Aktionsentwurf verworfen.');
                  }}
                />
              );
            })()}
            <MonitorCommunicationDock
              value={wishText}
              onChange={setWishText}
              onSubmit={() => { void handleSubmit(); }}
              disabled={submitDisabled}
              busy={localRepoLoading || chatResponseBusy || isPublishing}
              runtimeStatus={workStateStatus}
              entries={monitorCommunication}
              routeOptions={llmRouteOptions}
              selectedRouteId={selectedLlmRouteId}
              onRouteChange={(routeId) => {
                setSelectedLlmRouteId(routeId);
                addLog(
                  'info',
                  routeId ? `LLM Route manuell fixiert: ${routeId}` : 'LLM Route auf Auto/PAL zurückgesetzt',
                  'router',
                );
              }}
              routeCatalogError={llmRouteCatalogError}
              runtimeMood={agentStatus === 'error' ? '🛟⚠️' : runtimeThinkingActive ? '🤖💭' : '😊✨'}
              onOpenFlow={() => handleCompactToolSelect('runtime_logs')}
              onRequestIdea={() => {
                triggerHaptic('light');
                onGenerateIdeas();
              }}
              onOpenToolchain={() => {
                appendActionEvent(buildLocalRuntimeResultEvent({
                  label: 'Toolchain geöffnet',
                  detail: 'Registriertes Toolchain-Panel geöffnet; kein Tool automatisch ausgeführt.',
                }));
                useLauncherStore.getState().launchTool('sovereign-toolchain');
              }}
              toolchainState={!authUser
                ? 'unavailable'
                : toolchainLoading
                  ? 'checking'
                  : toolchainLoaded
                    ? 'ready'
                    : toolchainError
                      ? 'blocked'
                      : 'unavailable'}
              toolsLauncher={(
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
              )}
              routeHint={selectedLlmRouteId
                ? `Fixiert auf Backend-Route ${selectedLlmRouteId} · kein stiller Modell-Fallback`
                : composerRouteHint({
                    draft: wishText,
                    workerBlocked,
                    agentDisabled,
                  })}
              onKeyDown={handleComposerKeyDown}
              slashMenu={showSlashCommands ? (
                <SlashCommandMenu
                  commands={slashMatches}
                  selectedIndex={selectedSlashIndex}
                  onSelect={submitSelectedSlashCommand}
                />
              ) : null}
            />
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
            {!githubWriteAllowed && (scopedAgentJob?.status === 'running' || isPublishing || showGitHubAccessOverride) && (
              <GitHubAccessCard
                snapshot={effectiveGitHubAccessSnapshot}
                onProvideToken={async (token) => {
                  const formatResult = validateGitHubTokenFormat(token);
                  if (!formatResult.isValid) {
                    setGitHubAccessState(failGitHubAccessValidation('', formatResult.error || 'Ungültiges Format'));
                    setValidatedGitHubTargetKey(null);
                    githubTokenRef.current = null;
                    return;
                  }
                  appendRuntimeNotice('Ephemeres GitHub-Credential übernommen. Die Backend-Prüfung läuft; der Wert wird weder in Kommunikation noch Logs gespeichert.');
                  const ready = await validateCurrentRepoGithubCredential(
                    token,
                    formatResult.maskedToken,
                    'manual-pat',
                  );
                  if (!ready) return;
                  const pendingWriteIntent = pendingOnlineExecutionRef.current?.text
                    ?? pendingWriteIntentRef.current;
                  appendRuntimeNotice(pendingWriteIntent
                    ? 'GitHub-Zugang ist bereit. Der vorgemerkte Auftrag wird erst durch den bestätigten Gate-State fortgesetzt.'
                    : 'GitHub-Zugang ist bereit. Der Zugangswert bleibt ausschließlich im Speicher dieser Sitzung.');
                }}
                onDismiss={() => {
                  pendingOnlineExecutionRef.current = null;
                  pendingWriteIntentRef.current = null;
                  setShowGitHubAccessOverride(false);
                  appendActionEvent(buildLocalRuntimeResultEvent({
                    label: 'GitHub-Zugangsfläche geschlossen',
                    detail: 'Die sichere Zugangsfläche wurde geschlossen; kein Zugangsstatus wurde erfunden.',
                  }));
                }}
              />
            )}
            {workerBlocker && (
              <WorkerBlockerCard
                blocker={workerBlocker}
                onRetryWithMessage={(msg) => {
                  setWorkerBlocker(null);
                  appendActionEvent(buildLocalRuntimeResultEvent({
                    label: 'Retry gestartet',
                    detail: 'Die Monitor-Recovery hat den korrelierten Originalrequest erneut an die echte LLM-Route übergeben.',
                  }));
                  retrySubmit(msg, { ignoreExistingWorkerBlocker: true });
                }}
                onExplain={() => appendRuntimeNotice(explainDevChatWorkerDiagnostic(workerBlocker.diagnostic))}
                onLogin={() => setShowLogin(true)}
                onAgentInstead={(msg) => { void startAgentFromText(msg, 'code_execution'); }}
                userMessage={lastWorkerRequestMessage ?? undefined}
              />
            )}
            {scopedAgentJob?.draftPrUrl && (
              <DraftPrCard
                url={scopedAgentJob.draftPrUrl}
                changedFiles={scopedAgentJob.changedFiles || []}
                buildStatus={resolveDraftPrBuildStatus({ draftPrUrl: scopedAgentJob.draftPrUrl })}
                onOpenBrowser={() => {
                  const safeUrl = safeHttpsUrl(scopedAgentJob.draftPrUrl);
                  if (safeUrl) window.open(safeUrl, '_blank', 'noopener,noreferrer');
                }}
                onDiscussInChat={() => setWishText('Erkläre mir die Änderungen im Draft PR.')}
              />
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
      {filePreviewPath && filePreviewBindingKey && filePreviewBindingKey === currentFilePreviewBindingKey && (
        <FileContentPreviewSheet
          filePath={filePreviewPath}
          result={filePreviewResult}
          loading={filePreviewLoading}
          onClose={() => {
            filePreviewRequestGenerationRef.current += 1;
            setFilePreviewPath(null);
            setFilePreviewResult(null);
            setFilePreviewLoading(false);
            setFilePreviewBindingKey(null);
          }}
          onSendToChat={(prompt) => {
            filePreviewRequestGenerationRef.current += 1;
            setWishText(prompt);
            setFilePreviewPath(null);
            setFilePreviewResult(null);
            setFilePreviewLoading(false);
            setFilePreviewBindingKey(null);
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
