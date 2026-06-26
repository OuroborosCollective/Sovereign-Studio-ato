import './runtime-adapter';
import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { buildGitHubHeaders, stripTokenFromText } from './features/github/githubAuthSession';
import { parseGithubRepoUrl } from './features/github/utils';
import { publishPackageAsDraftPr } from './features/github/githubPackagePublisher';
import { learnSolutionPattern } from './features/product/runtime/solutionPatternMemory';
import { useGithubRepo } from './features/github/hooks/useGithubRepo';
import { GeneratedFileDiffPreviewPanel } from './features/product/components/GeneratedFileDiffPreviewPanel';
import { GeneratedFileReviewPanel } from './features/product/components/GeneratedFileReviewPanel';
import { RemoteMemoryContainer } from './features/product/containers/RemoteMemoryContainer';
import { BuilderContainer } from './features/product/containers/BuilderContainer';
import { RepoInsightPanelBridge } from './features/product/components/RepoInsightPanelBridge';
import { WorkflowContainer } from './features/product/containers/WorkflowContainer';
import { RepoSnapshotContainer } from './features/product/containers/RepoSnapshotContainer';
import { TelemetryContainer } from './features/product/containers/TelemetryContainer';
import { PatternMemoryContainer } from './features/product/containers/PatternMemoryContainer';
import { RepoFileIntegrityMatrix } from './features/product/components/RepoFileIntegrityMatrix';
import { RepoReadinessPanel } from './features/product/components/RepoReadinessPanel';
import { RuntimeValidationCoveragePanel } from './features/product/components/RuntimeValidationCoveragePanel';
import { ScanFindingRegistryPanel } from './features/product/components/ScanFindingRegistryPanel';
import { SequentialRuntimePanel } from './features/product/components/SequentialRuntimePanel';
import { SovereignHealthPanel } from './features/product/components/SovereignHealthPanel';
import { ModelHealthPanel } from './features/product/components/ModelHealthPanel';
import { ChatRuntimePanel } from './features/product/components/ChatRuntimePanel';
import { LlmAdapterProvider, useAllLlmAdapters } from './features/product/contexts/LlmAdapterContext';
import { SovereignTabErrorBoundary } from './features/product/components/SovereignTabErrorBoundary';
import { SettingsModal } from './features/product/components/SettingsModal';
import { useUserApiKeys } from './features/product/hooks/useUserApiKeys';
import type { UserApiKeys } from './features/product/components/UserKeyManager';
import {
  createOpenHandsEnterpriseClient,
  type OpenHandsEnterpriseClientOptions,
} from './features/product/runtime/openhandsEnterpriseClient';
import {
  resolveOpenHandsEnterpriseConfig,
  createOpenHandsIdleSnapshot,
  summarizeOpenHandsJob,
  type OpenHandsJobSnapshot,
} from './features/product/runtime/openhandsEnterpriseRuntime';
import {
  AUTOMATION_MODE_LABELS,
  buildAutomationRunKey,
  decideSovereignAutomation,
  describeAutomationMode,
  type SovereignAutomationMode,
} from './features/product/runtime/sovereignAutomationMode';
import {
  decideSovereignAutoView,
  type SovereignAutoViewTab,
} from './features/product/runtime/sovereignAutoViewRouter';
import {
  buildGeneratedFileDiffReport,
  type SourceFileSnapshot,
} from './features/product/runtime/generatedFileDiffPreview';
import { assertGeneratedFileReviewSafe, reviewGeneratedFiles } from './features/product/runtime/generatedFileReview';
import { assertCanPublishPackage } from './features/product/runtime/appPublishRuntime';
import { buildRuntimeValidationCoverageReport } from './features/product/runtime/runtimeValidationCoverage';
import {
  applyScanFindings,
  collectRepoPathFindings,
  createScanFindingRegistry,
  summarizeScanFindingRegistry,
} from './features/product/runtime/scanFindingRegistry';
import { applyWorkflowScanAndBuildGate } from './features/product/runtime/scanFindingWorkflowBridge';
import {
  createExternalMemorySyncConfig,
  type ExternalMemorySyncConfig,
} from './features/product/runtime/externalMemorySync';
import {
  createSolutionPatternStore,
  type SolutionPatternStore,
} from './features/product/runtime/solutionPatternMemory';
import {
  clearSolutionPatternStore,
  loadSolutionPatternStore,
  saveSolutionPatternStore,
} from './features/product/runtime/solutionPatternPersistence';
import {
  createSequentialRuntimeState,
  finishSequentialStep,
  startSequentialStep,
  type SequentialRuntimeState,
  type SequentialRuntimeStep,
  type SequentialStartOptions,
} from './features/product/runtime/sequentialRuntimeGuard';
import { buildSovereignHealthReport } from './features/product/runtime/sovereignHealth';
import {
  createSessionMemorySnapshot,
  formatSessionMemoryAge,
  loadSessionMemory,
  saveSessionMemory,
} from './features/product/runtime/sovereignSessionMemory';
import {
  appendTelemetryEvent,
  createInitialTelemetryState,
  createTelemetryEvent,
} from './features/product/runtime/sovereignTelemetry';
import {
  buildSovereignPackageFromRepoFiles,
  buildSovereignPackageFromRepoFilesWithLlm,
  summarizeSovereignPackage,
} from './features/product/runtime/sovereignPackageFromRepoFiles';
import { buildSovereignMemoryContext } from './features/product/runtime/sovereignMemoryContext';
import { buildWorkflowRepairPlan } from './features/product/runtime/workflowRepairPlan';
import { fetchWorkflowWatchReport, type WorkflowWatchReport } from './features/product/runtime/workflowWatch';
import type { SovereignImplementationPackage } from './features/product/runtime/sovereignRuntime';
import { UserSession } from './shared/types/user';
import { makeId } from './shared/utils/crypto';
import { LoginView } from './components/LoginView';
import { deriveCoachStateFromRuntime, useCoachRuntimeBridge } from './features/product/hooks/useCoachRuntimeBridge';
import { useSetupState, publishSetupStateToWindow } from './features/github/hooks/useSetupState';
import { wallClockMs } from './mobile-operator-coach';
import {
  SOVEREIGN_PRODUCT_TEMPLATE,
} from './features/product/runtime/sovereignProductTemplate';
import {
  SOVEREIGN_APP_CLASSES,
  getSovereignTabStyle,
} from './features/product/runtime/sovereignStyleContract';
import {
  createSovereignTestId,
} from './features/product/runtime/sovereignComponentContracts';

type SovereignTab = 'monitor' | SovereignAutoViewTab;

const DEFAULT_MISSION = 'README + Update History';
const AUTO_STEP_DELAY_MS = 5000;
const USER_NAVIGATION_OVERRIDE_MS = 30_000;

// Tabs are derived from the Product Template as the single source of truth.
// This ensures the app shell always matches the product contract.
// Each tab object includes contract-bound styling and accessibility properties.
const tabs: Array<{
  id: SovereignTab;
  label: string;
  cssClass: string;
  activeCssClass: string;
  dataRole: string;
  ariaLabel: string;
  mobilePriority: number;
  testId: string;
}> = SOVEREIGN_PRODUCT_TEMPLATE.tabs
  .filter((tab) => tab.userVisible)
  .map((tab) => {
    const style = getSovereignTabStyle(tab.id);
    return {
      id: tab.id as SovereignTab,
      label: tab.label,
      cssClass: style.cssClass,
      activeCssClass: style.activeCssClass,
      dataRole: style.dataRole,
      ariaLabel: style.ariaLabel,
      mobilePriority: style.mobilePriority,
      testId: createSovereignTestId('tabbar', tab.id),
    };
  });

const automationModes: SovereignAutomationMode[] = ['manual', 'auto-review', 'full-auto-draft-pr'];
const PRIMARY_TAB_IDS = new Set<SovereignTab>(SOVEREIGN_PRODUCT_TEMPLATE.primaryFlow as SovereignTab[]);
const SIDE_TAB_IDS = new Set<SovereignTab>(SOVEREIGN_PRODUCT_TEMPLATE.sideTabs as SovereignTab[]);
const DIAGNOSTIC_TAB_IDS = new Set<SovereignTab>(SOVEREIGN_PRODUCT_TEMPLATE.diagnosticTabs as SovereignTab[]);
const primaryTabs = tabs.filter((tab) => PRIMARY_TAB_IDS.has(tab.id));
const sideTabs = tabs.filter((tab) => SIDE_TAB_IDS.has(tab.id));
const diagnosticTabs = tabs.filter((tab) => DIAGNOSTIC_TAB_IDS.has(tab.id));

// Start tab is derived from the Product Template contract.
const startTab: SovereignTab = SOVEREIGN_PRODUCT_TEMPLATE.startTab as SovereignTab;

function decodeBase64Utf8(value: string): string {
  const binary = atob(value.replace(/\s/g, ''));
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function encodeGitHubContentPath(path: string): string {
  return path.split('/').map((part) => encodeURIComponent(part)).join('/');
}

function normalizeMission(value: string): string {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : DEFAULT_MISSION;
}

function createSafeSolutionPatternStore(): SolutionPatternStore {
  return createSolutionPatternStore();
}

function loadSafeSolutionPatternStore(): SolutionPatternStore {
  if (typeof window === 'undefined') return createSafeSolutionPatternStore();

  try {
    const result = loadSolutionPatternStore(window.localStorage);
    return Array.isArray(result.store.patterns) ? result.store : createSafeSolutionPatternStore();
  } catch {
    return createSafeSolutionPatternStore();
  }
}

function formatSolutionPatternHints(store: SolutionPatternStore): string {
  const safePatterns = Array.isArray(store.patterns) ? store.patterns : [];

  const patterns = safePatterns
    .filter((pattern) => pattern.status === 'active')
    .sort((a, b) => b.successfulUses - a.successfulUses || b.updatedAt - a.updatedAt)
    .slice(0, 5);

  if (!patterns.length) return '';

  return [
    'Remote Aha Memory:',
    ...patterns.map((pattern) => `- ${pattern.category} ${pattern.fileExtension}: ${pattern.solutionSummary}`),
  ].join('\n');
}

const App: React.FC = () => {
  const [user, setUser] = useState<UserSession | null>(null);
  const [mission, setMission] = useState(DEFAULT_MISSION);
  const [sovereignSummary, setSovereignSummary] = useState('Noch kein Sovereign-Paket erzeugt.');
  const [sovereignPreview, setSovereignPreview] = useState('');
  const [lastPackage, setLastPackage] = useState<SovereignImplementationPackage | null>(null);
  const [lastPackageKey, setLastPackageKey] = useState('');
  const [lastDraftCommitSha, setLastDraftCommitSha] = useState('');
  const [lastDraftBranch, setLastDraftBranch] = useState('');
  const [lastDraftPackageKey, setLastDraftPackageKey] = useState('');
  const [workflowReport, setWorkflowReport] = useState<WorkflowWatchReport | null>(null);
  const [diffSources, setDiffSources] = useState<SourceFileSnapshot[]>([]);
  const [isLoadingDiffSources, setIsLoadingDiffSources] = useState(false);
  const [isWatchingWorkflow, setIsWatchingWorkflow] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [activeTab, setActiveTab] = useState<SovereignTab>(startTab);
  const [telemetryExpanded, setTelemetryExpanded] = useState(true);
  const [telemetry, setTelemetry] = useState(() => createInitialTelemetryState());
  const [scanRegistry, setScanRegistry] = useState(() => createScanFindingRegistry());
  const [solutionPatternStore, setSolutionPatternStore] = useState(loadSafeSolutionPatternStore);
  const [remoteMemoryConfig, setRemoteMemoryConfig] = useState<ExternalMemorySyncConfig>(() => ({
    ...createExternalMemorySyncConfig(),
    gatewayUrl: '',
    workspaceId: 'Pattern',
    collectionName: 'sovereign_logic_patterns',
    contributorId: 'sovereign-local-install',
    allowSelfHostedHttp: false,
  }));

  const sequentialRuntimeRef = useRef<SequentialRuntimeState>(createSequentialRuntimeState());
  const [sequentialRuntime, setSequentialRuntime] = useState(() => sequentialRuntimeRef.current);
  const [automationMode, setAutomationMode] = useState<SovereignAutomationMode>('manual');
  const [lastAutoRunKey, setLastAutoRunKey] = useState('');
  const [automationStatus, setAutomationStatus] = useState('Manual mode is active.');
  const [planningConfirmed, setPlanningConfirmed] = useState(false);

  // OpenHands Enterprise state
  const openhandsConfig = useMemo(() => resolveOpenHandsEnterpriseConfig(), []);
  const openhandsClient = useMemo(() => 
    openhandsConfig.ready ? createOpenHandsEnterpriseClient({ config: openhandsConfig }) : null,
    [openhandsConfig]
  );
  const [openhandsJob, setOpenhandsJob] = useState<OpenHandsJobSnapshot>(createOpenHandsIdleSnapshot());
  const [openhandsJobId, setOpenhandsJobId] = useState<string | null>(null);
  const [isPollingOpenHands, setIsPollingOpenHands] = useState(false);
  const lastAutoViewReasonRef = useRef('');
  const recentUserInteractionUntil = useRef(0);
  const autoStepReadyAtRef = useRef(0);
  const autoStepTimerRef = useRef<number | null>(null);

  const githubRepoState = useGithubRepo();
  const setupState = useSetupState(githubRepoState);
  const { userApiKeys, setUserKeys } = useUserApiKeys();

  const [showSettings, setShowSettings] = useState(false);

  const {
    repoUrl,
    setRepoUrl,
    repoBranch,
    setRepoBranch,
    githubToken,
    setGithubToken,
    repoStatus,
    isRepoBusy,
    repoFiles,
    repoSnapshotStatus,
    loadRepoTree,
    restoreRepoSnapshot,
    clearRepoSnapshot,
  } = setupState;

  // Publish Setup State to window for Coach consumption
  useEffect(() => {
    if (typeof window === 'undefined') return;
    publishSetupStateToWindow(setupState);
  }, [setupState]);

  // ⚡ Bolt: Memoize safe arrays to prevent redundant recalculations in dependent hooks
  const safeRepoFiles = useMemo(() => Array.isArray(repoFiles) ? repoFiles : [], [repoFiles]);
  const safeDiffSources = useMemo(() => Array.isArray(diffSources) ? diffSources : [], [diffSources]);
  const runtimeBusy = Boolean(sequentialRuntime.activeStep);
  const currentMission = normalizeMission(mission);

  // ⚡ Bolt: Memoize expensive derived state and orchestration keys to prevent lag during mission input
  // and redundant processing during automation runs.
  const packageInputKey = useMemo(() => buildAutomationRunKey({
    mode: 'manual',
    repoUrl,
    repoBranch,
    mission: currentMission,
    repoFileCount: safeRepoFiles.length,
  }), [repoUrl, repoBranch, currentMission, safeRepoFiles.length]);
  const automationRunKey = useMemo(() => buildAutomationRunKey({
    mode: automationMode,
    repoUrl,
    repoBranch,
    mission: currentMission,
    repoFileCount: safeRepoFiles.length,
  }), [automationMode, repoUrl, repoBranch, currentMission, safeRepoFiles.length]);
  const hasFreshPackage = Boolean(lastPackage && lastPackageKey === packageInputKey);
  const latestGeneratedReview = useMemo(() => lastPackage ? reviewGeneratedFiles(lastPackage.files) : null, [lastPackage]);
  const diffReport = useMemo(() => lastPackage ? buildGeneratedFileDiffReport(lastPackage.files, safeDiffSources) : null, [lastPackage, safeDiffSources]);
  const repairPlan = useMemo(() => buildWorkflowRepairPlan({ report: workflowReport }), [workflowReport]);
  const healthReport = useMemo(() => buildSovereignHealthReport({
    repoFiles: safeRepoFiles,
    generatedFileReview: latestGeneratedReview,
    workflowWatch: workflowReport,
    telemetry,
  }), [safeRepoFiles, latestGeneratedReview, workflowReport, telemetry]);
  const coverageReport = useMemo(() => buildRuntimeValidationCoverageReport(), []);
  const solutionPatternHints = useMemo(() => formatSolutionPatternHints(solutionPatternStore), [solutionPatternStore]);
  const activePatternCount = useMemo(() => Array.isArray(solutionPatternStore.patterns)
    ? solutionPatternStore.patterns.filter((pattern) => pattern.status === 'active').length
    : 0, [solutionPatternStore.patterns]);

  // Coach-State aus echtem Runtime ableiten - für mobile-operator-coach
  const coachState = useMemo(() => deriveCoachStateFromRuntime(
    sequentialRuntime,
    repoSnapshotStatus.ready,
    Boolean(lastPackage),
    workflowReport?.status,
    isPublishing,
    isWatchingWorkflow,
    activePatternCount > 0
  ), [sequentialRuntime, repoSnapshotStatus.ready, lastPackage, workflowReport?.status, isPublishing, isWatchingWorkflow, activePatternCount]);

  // Expose Coach-State für mobile-operator-coach
  useCoachRuntimeBridge({ coachState });

  // ⚡ Bolt: Stabilize telemetry callback identity to prevent cascading re-renders in diagnostic components
  const pushTelemetry = useCallback((
    stage: Parameters<typeof createTelemetryEvent>[0],
    level: Parameters<typeof createTelemetryEvent>[1],
    label: string,
    message: string,
    details?: Parameters<typeof createTelemetryEvent>[4],
  ) => {
    setTelemetry((state) => appendTelemetryEvent(state, createTelemetryEvent(stage, level, label, message, details)));
  }, [setTelemetry]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const result = saveSolutionPatternStore(window.localStorage, solutionPatternStore);
    if (!result.ok) pushTelemetry('memory', 'warning', 'aha-memory:persist-failed', result.summary);
    // Store persistence follows solutionPatternStore changes only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [solutionPatternStore]);

  const handleUserTabClick = (tab: SovereignTab) => {
    recentUserInteractionUntil.current = wallClockMs() + USER_NAVIGATION_OVERRIDE_MS;
    setActiveTab(tab);
  };

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const handleGuideCommand = (event: Event): void => {
      const detail = (event as CustomEvent<{ type?: string; targetTab?: SovereignTab | null }>).detail;
      if (!detail) return;

      if (detail.type === 'confirm') {
        recentUserInteractionUntil.current = wallClockMs() + USER_NAVIGATION_OVERRIDE_MS;
        setPlanningConfirmed(true);
        pushTelemetry('workflow', 'info', 'release-guide:confirmed', 'User confirmed the visible coach step.');
        return;
      }

      if ((detail.type === 'next' || detail.type === 'back') && detail.targetTab) {
        handleUserTabClick(detail.targetTab);
        pushTelemetry('workflow', 'info', `release-guide:${detail.type}`, `Coach navigation selected ${detail.targetTab}.`, { tab: detail.targetTab });
      }
    };

    window.addEventListener('sovereign:release-guide-command', handleGuideCommand as EventListener);
    return () => window.removeEventListener('sovereign:release-guide-command', handleGuideCommand as EventListener);
    // Release guide commands are runtime events from the global coach.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const routerActiveTab: SovereignAutoViewTab = activeTab === 'monitor' ? 'repo' : activeTab;
    const decision = decideSovereignAutoView({
      mode: automationMode,
      activeStep: sequentialRuntime.activeStep,
      activeTab: routerActiveTab,
      hasPackage: Boolean(lastPackage),
      hasDiffSources: safeDiffSources.length > 0,
      isPublishing,
      isWatchingWorkflow,
      workflowStatus: workflowReport?.status ?? 'idle',
      hasActivePatterns: activePatternCount > 0,
      hasActiveTelemetry: telemetry.events.length > 0,
      nowMs: wallClockMs(),
      manualOverrideUntil: recentUserInteractionUntil.current,
      recentUserInteractionUntil: recentUserInteractionUntil.current,
      planningConfirmed,
    });

    if (!decision.shouldSwitch) return;

    setActiveTab(decision.tab);

    if (lastAutoViewReasonRef.current !== decision.reason) {
      lastAutoViewReasonRef.current = decision.reason;
      pushTelemetry('workflow', 'info', 'view:auto-switch', decision.reason, { tab: decision.tab });
    }
    // Auto-view router intentionally follows runtime state snapshots.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, automationMode, isPublishing, isWatchingWorkflow, lastPackage, sequentialRuntime.activeStep, workflowReport?.status]);

  useEffect(() => {
    if (!safeRepoFiles.length) return;

    const startedAt = wallClockMs();
    const findings = collectRepoPathFindings(safeRepoFiles, startedAt);
    const completedAt = wallClockMs();

    setScanRegistry((current) => applyScanFindings(current, 'repo-path-scan', findings, startedAt, completedAt));

    pushTelemetry(
      'workflow',
      findings.some((finding) => finding.severity === 'critical' || finding.severity === 'high') ? 'warning' : 'success',
      'scan:repo-path-finished',
      `Repo scan abgeschlossen: ${findings.length} finding(s).`,
    );
    // Only react to fresh repo snapshots; telemetry helper identity is intentionally not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoFiles]);

  const setSequentialState = (next: SequentialRuntimeState) => {
    sequentialRuntimeRef.current = next;
    setSequentialRuntime(next);
  };

  const sequentialOptions = (override: SequentialStartOptions = {}): SequentialStartOptions => ({
    repoReady: repoSnapshotStatus.ready,
    hasPackage: Boolean(lastPackage),
    hasDiffSources: safeDiffSources.length > 0,
    hasDraftCommit: Boolean(lastDraftCommitSha),
    hasWorkflowReport: Boolean(workflowReport),
    ...override,
  });

  // OpenHands Enterprise job functions
  const startOpenHandsJob = useCallback(async (missionText: string): Promise<void> => {
    if (!openhandsClient || !openhandsConfig.ready) {
      setSovereignSummary('OpenHands ist nicht konfiguriert.');
      return;
    }
    
    if (!repoUrl) {
      setSovereignSummary('OpenHands braucht ein Repository.');
      return;
    }

    try {
      setIsPollingOpenHands(true);
      pushTelemetry('openhands', 'info', 'openhands:job-start', 'Starte OpenHands Auftrag.', { repo: repoUrl });
      
      const snapshot = await openhandsClient.startJob({
        repoUrl,
        branch: repoBranch || 'main',
        mission: missionText,
      });
      
      setOpenhandsJob(snapshot);
      setOpenhandsJobId(snapshot.jobId || null);
      setSovereignSummary(summarizeOpenHandsJob(snapshot));
      
      pushTelemetry('openhands', 'info', 'openhands:job-created', snapshot.jobId || 'OpenHands Job erstellt.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'OpenHands Auftrag fehlgeschlagen.';
      setSovereignSummary(message);
      pushTelemetry('openhands', 'error', 'openhands:job-error', message);
    }
  }, [openhandsClient, openhandsConfig.ready, repoUrl, repoBranch, pushTelemetry]);

  const pollOpenHandsJob = useCallback(async (): Promise<void> => {
    if (!openhandsClient || !openhandsJobId) return;

    try {
      const snapshot = await openhandsClient.getJob(openhandsJobId);
      setOpenhandsJob(snapshot);
      setSovereignSummary(summarizeOpenHandsJob(snapshot));
      
      // Stop polling on terminal status
      if (snapshot.status === 'completed' || snapshot.status === 'failed' || snapshot.status === 'blocked') {
        setIsPollingOpenHands(false);
        pushTelemetry('openhands', snapshot.status === 'completed' ? 'success' : 'warning', 
          `openhands:job-${snapshot.status}`, summarizeOpenHandsJob(snapshot));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Poll fehlgeschlagen.';
      pushTelemetry('openhands', 'error', 'openhands:poll-error', message);
    }
  }, [openhandsClient, openhandsJobId, pushTelemetry]);

  const cancelOpenHandsJob = useCallback(async (): Promise<void> => {
    if (!openhandsClient || !openhandsJobId) return;

    try {
      const snapshot = await openhandsClient.cancelJob(openhandsJobId);
      setOpenhandsJob(snapshot);
      setIsPollingOpenHands(false);
      setSovereignSummary('OpenHands Auftrag abgebrochen.');
      pushTelemetry('openhands', 'info', 'openhands:job-cancelled', 'Auftrag abgebrochen.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Cancel fehlgeschlagen.';
      pushTelemetry('openhands', 'error', 'openhands:cancel-error', message);
    }
  }, [openhandsClient, openhandsJobId, pushTelemetry]);

  // Poll OpenHands when active
  useEffect(() => {
    if (!isPollingOpenHands || !openhandsJobId) return;
    
    const interval = setInterval(pollOpenHandsJob, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, [isPollingOpenHands, openhandsJobId, pollOpenHandsJob]);

  const runSequentialStep = async <T,>(
    step: SequentialRuntimeStep,
    task: () => Promise<T>,
    options: SequentialStartOptions = {},
  ): Promise<T | null> => {
    try {
      const started = startSequentialStep(sequentialRuntimeRef.current, step, sequentialOptions(options));
      setSequentialState(started);
      pushTelemetry('workflow', 'info', `sequence:${step}:start`, started.steps[step].message ?? `${step} started.`);

      const result = await task();

      const completed = finishSequentialStep(sequentialRuntimeRef.current, step, 'completed', `${step} completed.`);
      setSequentialState(completed);
      pushTelemetry('workflow', 'success', `sequence:${step}:completed`, `${step} completed.`);

      return result;
    } catch (error) {
      const message = stripTokenFromText(error instanceof Error ? error.message : `${step} failed.`, githubToken);

      if (sequentialRuntimeRef.current.activeStep === step) {
        setSequentialState(finishSequentialStep(sequentialRuntimeRef.current, step, 'failed', message));
      }

      setSovereignSummary(message);
      pushTelemetry('workflow', 'error', `sequence:${step}:failed`, message);

      return null;
    }
  };

  const buildPackageCore = async (
    nextMission: string,
    nextPackageKey = packageInputKey,
  ): Promise<SovereignImplementationPackage | null> => {
    try {
      const cleanMission = normalizeMission(nextMission);
      pushTelemetry('package', 'info', 'package:build-start', 'Building Sovereign package.', { files: safeRepoFiles.length });

      // Build memory context for LLM
      const memoryContext = await buildSovereignMemoryContext({
        mission: cleanMission,
        repoPaths: safeRepoFiles.map((file) => file.path),
        config: remoteMemoryConfig,
        solutionPatternStore,
      });

      const missionWithAha = memoryContext.contextLines.length > 0 
        ? `${cleanMission}\n\n${memoryContext.contextLines.join('\n\n')}` 
        : cleanMission;

      // Use LLM-aware package builder
      const pkg = await buildSovereignPackageFromRepoFilesWithLlm({
        mission: missionWithAha,
        repoFiles: safeRepoFiles,
        selectedFilePath: 'README.md',
        previousPreview: sovereignPreview,
        memoryContext: memoryContext.contextLines,
        runtimeEvents: telemetry.events.map((event) => `${event.stage}:${event.level}:${event.label}`),
        allowUserKeyRoutes: true,
      });

      const review = reviewGeneratedFiles(pkg.files);
      assertGeneratedFileReviewSafe(review);

      setMission(cleanMission);
      setLastPackage(pkg);
      setLastPackageKey(nextPackageKey);
      setDiffSources([]);

      setSovereignSummary(
        `${summarizeSovereignPackage(pkg, safeRepoFiles)}\n${review.summary}${memoryContext.contextLines.length > 0 ? `\n${memoryContext.summary}` : ''}`,
      );

      setSovereignPreview(JSON.stringify({
        architecture: pkg.architecture,
        brain: pkg.brain,
        files: pkg.files.map((file) => ({ path: file.path, reason: file.reason })),
        fileReview: review,
        remoteAhaMemory: memoryContext.contextLines.length > 0 ? memoryContext.contextLines.join('\n\n') : undefined,
        suggestions: pkg.suggestions,
      }, null, 2));

      pushTelemetry('guards', 'success', 'guards:passed', 'Functional guards and generated-file review accepted package.', {
        generatedFiles: pkg.files.length,
      });

      // Learn from successful package for future use
      if (pkg.brain.execution.patches.length > 0) {
        try {
          const learningResult = learnSolutionPattern(solutionPatternStore, {
            mission: cleanMission,
            brain: pkg.brain,
            files: pkg.files,
            architecture: pkg.architecture,
            providerId: pkg.brain.learning?.patterns?.[0] || 'unknown',
          });

          if (learningResult.ok) {
            setSolutionPatternStore(learningResult.store);
            pushTelemetry('memory', 'success', 'pattern:learned', `Learned ${learningResult.pattern.category} pattern: ${learningResult.pattern.solutionSummary}`);
          }
        } catch (learningError) {
          pushTelemetry('memory', 'warning', 'pattern:learning-failed', `Pattern learning failed: ${learningError instanceof Error ? learningError.message : 'Unknown error'}`);
        }
      }

      return pkg;
    } catch (error) {
      setLastPackage(null);
      setLastPackageKey('');
      setDiffSources([]);

      const message = error instanceof Error ? error.message : 'Sovereign-Paket konnte nicht erzeugt werden.';
      const cleanMessage = stripTokenFromText(message, githubToken);

      setSovereignSummary(cleanMessage);
      pushTelemetry('guards', 'error', 'guards:failed', cleanMessage);

      return null;
    }
  };

  const buildPackage = async (
    nextMission: string,
    nextPackageKey = packageInputKey,
  ): Promise<SovereignImplementationPackage | null> => runSequentialStep('package-build', async () => {
    const pkg = await buildPackageCore(nextMission, nextPackageKey);
    if (!pkg) throw new Error('Package build failed.');
    return pkg;
  });

  const handleLoadRepoTree = async () => {
    await runSequentialStep('repo-load', async () => {
      pushTelemetry('repo', 'info', 'repo:load-start', 'Loading repository tree.', { repoUrl });

      await loadRepoTree();

      pushTelemetry('repo', 'success', 'repo:load-finished', 'Repository load request finished. Check repo status for exact result.');

      setLastPackage(null);
      setLastPackageKey('');
      setDiffSources([]);
      setLastDraftCommitSha('');
      setLastDraftBranch('');
      setLastDraftPackageKey('');
      setWorkflowReport(null);

      return true;
    });
  };

  const loadGeneratedFileSources = async () => {
    await runSequentialStep('diff-load', async () => {
      if (!lastPackage) throw new Error('Build a Sovereign package before loading diff sources.');

      const parsed = parseGithubRepoUrl(repoUrl);
      if (!parsed) throw new Error('Cannot load diff sources from an invalid GitHub repo URL.');

      setIsLoadingDiffSources(true);

      const headers = buildGitHubHeaders({ token: githubToken });
      const cleanBranch = repoBranch.trim();
      const refQuery = cleanBranch ? `?ref=${encodeURIComponent(cleanBranch)}` : '';

      try {
        const snapshots = await Promise.all(lastPackage.files.map(async (file): Promise<SourceFileSnapshot> => {
          const url = `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/contents/${encodeGitHubContentPath(file.path)}${refQuery}`;

          try {
            const response = await fetch(url, { headers });

            if (response.status === 404 || !response.ok) {
              return { path: file.path, content: null, found: false };
            }

            const payload = await response.json() as { content?: string; encoding?: string } | Array<unknown>;

            if (Array.isArray(payload) || !payload.content || payload.encoding !== 'base64') {
              return { path: file.path, content: null, found: false };
            }

            return { path: file.path, content: decodeBase64Utf8(payload.content), found: true };
          } catch {
            return { path: file.path, content: null, found: false };
          }
        }));

        setDiffSources(snapshots);

        const report = buildGeneratedFileDiffReport(lastPackage.files, snapshots);
        const cleanSummary = stripTokenFromText(report.summary, githubToken);

        setSovereignSummary(cleanSummary);
        pushTelemetry('workflow', 'success', 'diff:load-finished', cleanSummary);

        return report;
      } finally {
        setIsLoadingDiffSources(false);
      }
    });
  };

  const watchLatestWorkflow = async (
    commitSha = lastDraftCommitSha,
    branch = lastDraftBranch,
  ) => runSequentialStep('workflow-watch', async () => {
    setIsWatchingWorkflow(true);

    try {
      const nextReport = await fetchWorkflowWatchReport({
        repoUrl,
        token: githubToken,
        commitSha,
        branch,
      });

      setWorkflowReport(nextReport);

      const startedAt = wallClockMs();
      const bridge = applyWorkflowScanAndBuildGate(scanRegistry, nextReport, startedAt, wallClockMs());

      setScanRegistry(bridge.registry);

      pushTelemetry(
        'workflow',
        nextReport.status === 'red' ? 'error' : nextReport.status === 'green' ? 'success' : 'warning',
        'workflow:watch-finished',
        stripTokenFromText(nextReport.summary, githubToken),
      );

      pushTelemetry(
        'workflow',
        bridge.gate.allowed ? 'success' : 'warning',
        'scan:workflow-findings-synced',
        stripTokenFromText(bridge.summary, githubToken),
        { blockers: bridge.gate.blockers.length },
      );

      return nextReport;
    } finally {
      setIsWatchingWorkflow(false);
    }
  }, { hasDraftCommit: Boolean(commitSha) });

  const generateRepoIdeas = () => {
    void buildPackage(currentMission);
  };

  const generateErrorWorkflow = () => {
    void buildPackage('Workflow Fehleranalyse + Runtime Check + Test Plan');
  };

  const useRepairMission = (nextMission: string) => {
    void runSequentialStep('repair-plan', async () => {
      const cleanMission = normalizeMission(nextMission);

      setMission(cleanMission);
      setLastPackage(null);
      setLastPackageKey('');
      setDiffSources([]);
      setSovereignSummary('Repair mission loaded into Builder. Run Ideen/Full Auto to generate a guarded repair package.');

      pushTelemetry('workflow', 'info', 'repair:mission-loaded', 'Workflow repair mission loaded into Builder.');

      return true;
    }, { hasWorkflowReport: Boolean(workflowReport) });
  };

  const saveCurrentSession = () => {
    if (!repoSnapshotStatus.ready || typeof window === 'undefined') {
      pushTelemetry('memory', 'warning', 'memory:save-blocked', repoSnapshotStatus.reason);
      return;
    }

    const snapshot = createSessionMemorySnapshot({
      repoUrl,
      repoBranch,
      repoStatus,
      repoFiles: safeRepoFiles,
      mission: currentMission,
      sovereignSummary,
      sovereignPreview,
    });

    saveSessionMemory(window.localStorage, snapshot);

    pushTelemetry('memory', 'success', 'memory:saved', `Session saved ${formatSessionMemoryAge(snapshot)}.`, {
      files: safeRepoFiles.length,
    });
  };

  const restoreSession = () => {
    if (typeof window === 'undefined') return;

    const snapshot = loadSessionMemory(window.localStorage);

    if (!snapshot) {
      pushTelemetry('memory', 'warning', 'memory:empty', 'No valid session memory snapshot found.');
      return;
    }

    restoreRepoSnapshot(snapshot);
    setMission(normalizeMission(snapshot.mission));
    setSovereignSummary(`${snapshot.sovereignSummary}\nRestored ${formatSessionMemoryAge(snapshot)}.`);
    setSovereignPreview(snapshot.sovereignPreview);
    setLastPackage(null);
    setLastPackageKey('');
    setDiffSources([]);
    setLastDraftCommitSha('');
    setLastDraftBranch('');
    setLastDraftPackageKey('');
    setWorkflowReport(null);
    setLastAutoRunKey('');

    pushTelemetry('memory', 'success', 'memory:restored', `Restored session from ${formatSessionMemoryAge(snapshot)}.`, {
      files: snapshot.repoFiles.length,
    });
  };

  const clearSession = () => {
    clearRepoSnapshot();
    setLastPackage(null);
    setLastPackageKey('');
    setDiffSources([]);
    setLastDraftCommitSha('');
    setLastDraftBranch('');
    setLastDraftPackageKey('');
    setWorkflowReport(null);
    setLastAutoRunKey('');
    setSovereignPreview('');
    setSovereignSummary('Noch kein Sovereign-Paket erzeugt.');

    pushTelemetry('memory', 'info', 'memory:cleared', 'Visible session state cleared. Stored memory is unchanged.');
  };

  const publishDraftPrForPackage = async (pkg: SovereignImplementationPackage): Promise<boolean> => {
    if (lastDraftCommitSha && lastDraftBranch && lastDraftPackageKey === packageInputKey) {
      const message = [
        'Draft PR existiert bereits fuer diesen Auftrag und Repo-Snapshot.',
        `Branch: ${lastDraftBranch}`,
        `Commit: ${lastDraftCommitSha}`,
        'Ich erstelle keinen zweiten identischen Draft PR. Beobachte stattdessen die bestehenden Checks.',
      ].join('\n');
      setSovereignSummary(message);
      pushTelemetry('github', 'info', 'github:draft-pr-deduped', 'Existing Draft PR reused for this exact package input.', { branch: lastDraftBranch });
      await watchLatestWorkflow(lastDraftCommitSha, lastDraftBranch);
      return true;
    }

    const result = await runSequentialStep('draft-pr-publish', async () => {
      // Guard: all publish preconditions must pass (file review + health gate)
      const review = reviewGeneratedFiles(pkg.files);
      assertGeneratedFileReviewSafe(review);
      assertCanPublishPackage(pkg, {
        repoFiles: safeRepoFiles,
        healthReport,
      });

      if (!githubToken.trim()) {
        throw new Error('GitHub Zugang fehlt. Draft PR wird nur mit bewusst eingegebenem Zugangswert erstellt.');
      }

      setIsPublishing(true);

      try {
        return await publishPackageAsDraftPr({
          repoUrl,
          token: githubToken,
          baseBranch: repoBranch,
          branchNonce: makeId(),
          title: `Sovereign Studio: ${currentMission || pkg.requestedWork}`,
          body: [
            'Generated by Sovereign Studio.',
            '',
            summarizeSovereignPackage(pkg, safeRepoFiles),
            '',
            'Generated file review:',
            review.summary,
            diffReport ? `Generated file diff preview: ${diffReport.summary}` : 'Generated file diff preview: not loaded.',
            '',
            'Scan findings:',
            summarizeScanFindingRegistry(scanRegistry),
            '',
            'Suggestions:',
            ...pkg.suggestions.map((item) => `- ${item}`),
          ].join('\n'),
          files: pkg.files,
        });
      } finally {
        setIsPublishing(false);
      }
    }, { hasPackage: true });

    if (!result) return false;

    setLastDraftCommitSha(result.commitSha);
    setLastDraftBranch(result.branch);
    setLastDraftPackageKey(packageInputKey);
    setSovereignSummary([
      'Draft PR erstellt.',
      `URL: ${result.pullRequestUrl}`,
      `Branch: ${result.branch}`,
      `Commit: ${result.commitSha}`,
    ].join('\n'));

    pushTelemetry('github', 'success', 'github:draft-pr-created', 'Draft PR created.', {
      pr: result.pullRequestNumber,
      branch: result.branch,
    });

    setTelemetryExpanded(true);

    await watchLatestWorkflow(result.commitSha, result.branch);

    return true;
  };

  const publishDraftPr = async () => {
    const pkg = hasFreshPackage && lastPackage ? lastPackage : await buildPackage(currentMission, packageInputKey);
    if (!pkg) return;

    await publishDraftPrForPackage(pkg);
  };

  useEffect(() => {
    if (!user) return undefined;

    if (autoStepTimerRef.current && typeof window !== 'undefined') {
      window.clearTimeout(autoStepTimerRef.current);
      autoStepTimerRef.current = null;
    }

    const decision = decideSovereignAutomation({
      mode: automationMode,
      repoReady: repoSnapshotStatus.ready,
      hasMission: currentMission.length > 0,
      hasToken: githubToken.trim().length > 0,
      isBusy: isRepoBusy || isPublishing || isWatchingWorkflow || isLoadingDiffSources || runtimeBusy,
      hasPackage: hasFreshPackage,
      lastAutoRunKey,
      nextAutoRunKey: automationRunKey,
    });

    if (automationMode === 'manual') {
      setAutomationStatus('Manual mode is active.');
      return undefined;
    }

    if (decision.blockedReason) {
      setAutomationStatus(decision.blockedReason);
      return undefined;
    }

    const scheduleAutoStep = (label: string, run: () => void): (() => void) | undefined => {
      const now = wallClockMs();
      const waitMs = Math.max(0, autoStepReadyAtRef.current - now);
      const start = () => {
        autoStepTimerRef.current = null;
        run();
      };

      if (waitMs <= 0 || typeof window === 'undefined') {
        start();
        return undefined;
      }

      setAutomationStatus(`${label} startet in ${Math.ceil(waitMs / 1000)}s. Ich lasse die Runtime sichtbar fertig atmen.`);
      const handle = window.setTimeout(start, waitMs);
      autoStepTimerRef.current = handle;
      return () => {
        window.clearTimeout(handle);
        if (autoStepTimerRef.current === handle) autoStepTimerRef.current = null;
      };
    };

    if (decision.shouldBuildPackage && automationMode === 'auto-review') {
      return scheduleAutoStep('Auto Review', () => {
        setLastAutoRunKey(automationRunKey);
        setAutomationStatus('Auto Review baut und prueft generierte Dateien.');
        pushTelemetry('workflow', 'info', 'automation:auto-review', 'Auto Review triggered package build.');
        void (async () => {
          try {
            await buildPackage(currentMission, packageInputKey);
          } finally {
            autoStepReadyAtRef.current = wallClockMs() + AUTO_STEP_DELAY_MS;
          }
        })();
      });
    }

    if (automationMode === 'full-auto-draft-pr' && decision.shouldPublishDraftPr) {
      return scheduleAutoStep('Full Auto Draft PR', () => {
        setLastAutoRunKey(automationRunKey);
        setAutomationStatus('Full Auto erstellt erst nach Runtime-Ruhefenster den Draft PR.');
        pushTelemetry('workflow', 'info', 'automation:full-auto', 'Full Auto triggered guarded Draft PR flow.');

        void (async () => {
          try {
            const pkg = hasFreshPackage && lastPackage ? lastPackage : await buildPackage(currentMission, packageInputKey);
            if (pkg) await publishDraftPrForPackage(pkg);
          } finally {
            autoStepReadyAtRef.current = wallClockMs() + AUTO_STEP_DELAY_MS;
          }
        })();
      });
    }

    return undefined;
    // The automation effect intentionally watches value snapshots, not helper function identities.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    automationMode,
    automationRunKey,
    currentMission,
    githubToken,
    hasFreshPackage,
    isLoadingDiffSources,
    isPublishing,
    isRepoBusy,
    isWatchingWorkflow,
    lastAutoRunKey,
    lastPackage,
    packageInputKey,
    repoSnapshotStatus.ready,
    runtimeBusy,
    user,
  ]);

  const resetPatternMemory = () => {
    if (typeof window === 'undefined') return;

    const result = clearSolutionPatternStore(window.localStorage);
    setSolutionPatternStore(result.store);

    pushTelemetry('memory', result.ok ? 'success' : 'warning', 'pattern-memory:reset', result.summary);
  };

  const changeAutomationMode = (mode: SovereignAutomationMode) => {
    setAutomationMode(mode);
    setLastAutoRunKey('');
    setAutomationStatus(describeAutomationMode(mode));

    pushTelemetry(
      'workflow',
      mode === 'manual' ? 'info' : 'warning',
      'automation:mode-changed',
      describeAutomationMode(mode),
    );
  };

  const login = () => {
    setUser({
      id: makeId(),
      email: 'demo@local',
      name: 'User',
      imageUrl: '',
    });
  };

  if (!user) return <LoginView onLogin={login} />;

  return (
    <LlmAdapterProvider>
    <div className={`${SOVEREIGN_APP_CLASSES.shell} min-h-screen p-4`} data-role="sovereign-app-shell" data-testid="app-shell__root">
      <h1 className={`${SOVEREIGN_APP_CLASSES.title} font-bold`} data-role="sovereign-app-title">Sovereign Canvas Tool</h1>

      {/* Settings Button */}
      <div className="flex justify-end mt-4">
        <button
          onClick={() => setShowSettings(true)}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg border border-slate-600 transition-colors"
          aria-label="Einstellungen"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M12 1v6m0 6v6M5.6 5.6l4.2 4.2m4.4 4.4l4.2 4.2M1 12h6m6 0h6M5.6 18.4l4.2-4.2m4.4-4.4l4.2-4.2"></path>
          </svg>
          <span className="text-sm font-medium">⚙️ Einstellungen</span>
        </button>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <SettingsModal
          repoUrl={repoUrl}
          setRepoUrl={setRepoUrl}
          accessKey={githubToken}
          setAccessKey={setGithubToken}
          geminiKey={userApiKeys.gemini || ''}
          setGeminiKey={(val) => setUserKeys({ ...userApiKeys, gemini: val || undefined })}
          settings={setupState.settings}
          setSettings={setupState.setSettings}
          setShowSettings={setShowSettings}
          userApiKeys={userApiKeys}
          setUserApiKeys={setUserKeys}
        />
      )}

      <div className={`${SOVEREIGN_APP_CLASSES.tabbar} mt-4 flex flex-wrap gap-2 border-b border-slate-800 pb-2`} role="tablist" aria-label="Sovereign workspace tabs" data-role="sovereign-tabbar" data-testid="tabbar__root">
        {primaryTabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-label={tab.ariaLabel}
            aria-selected={activeTab === tab.id}
            data-role={tab.dataRole}
            data-testid={tab.testId}
            className={activeTab === tab.id ? `${tab.cssClass} ${tab.activeCssClass}` : tab.cssClass}
            onClick={() => handleUserTabClick(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}

        <label className="sovereign-more-menu" data-testid="tabbar__more">
          <span className="sr-only">Weitere Bereiche</span>
          <select
            value={PRIMARY_TAB_IDS.has(activeTab) ? '' : activeTab}
            onChange={(event) => {
              const nextTab = event.target.value as SovereignTab;
              if (nextTab) handleUserTabClick(nextTab);
            }}
            className={`${SOVEREIGN_APP_CLASSES.select} sovereign-tab sovereign-more-select`}
            aria-label="Weitere Bereiche öffnen"
            data-role="sovereign-more-menu"
            data-testid="tabbar__more-select"
          >
            <option value="">Mehr Bereiche</option>
            <optgroup label="Workflow & Memory">
              {sideTabs.map((tab) => (
                <option key={tab.id} value={tab.id}>{tab.label}</option>
              ))}
            </optgroup>
            <optgroup label="Diagnose">
              {diagnosticTabs.map((tab) => (
                <option key={tab.id} value={tab.id}>{tab.label}</option>
              ))}
            </optgroup>
          </select>
        </label>
      </div>

      <section className={`${SOVEREIGN_APP_CLASSES.card} ${SOVEREIGN_APP_CLASSES.automationPanel} mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200`} data-role="sovereign-automation-panel" data-testid="automation__panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-bold">Automation Mode</h2>
            <p className="mt-1 text-xs text-slate-400">{automationStatus}</p>
          </div>

          <select
            value={automationMode}
            onChange={(event) => changeAutomationMode(event.target.value as SovereignAutomationMode)}
            className={`${SOVEREIGN_APP_CLASSES.select} rounded border border-slate-700 bg-slate-900 p-2 text-sm`}
            aria-label="Automation mode"
            data-role="automation-mode-select"
            data-testid="automation__mode-select"
          >
            {automationModes.map((mode) => (
              <option key={mode} value={mode}>
                {AUTOMATION_MODE_LABELS[mode]}
              </option>
            ))}
          </select>
        </div>

        <p className="mt-2 text-[11px] text-slate-500">
          Full Auto runs repo snapshot checks, scan findings, sequential runtime guard, generated-file review, auto-view routing, workflow watch and Draft PR publishing rules. It does not auto-merge.
        </p>
      </section>

      {activeTab === 'monitor' ? (
        <SovereignTabErrorBoundary
          tabId="monitor"
          tabLabel="Monitor"
          onDismiss={() => handleUserTabClick('repo')}
        >
          <section
            className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200"
            data-testid="operator-monitor"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-bold">Live Monitor</h2>
                <p className="mt-1 text-xs text-slate-400">
                  Optionale Operator-Zentrale für Runtime Guards, Pattern Memory, Remote Memory und Telemetry. Der Release-Workflow startet bewusst im Repo-Tab.
                </p>
              </div>

              <div className="flex flex-wrap gap-2 text-xs">
                <button type="button" onClick={() => handleUserTabClick('repo')}>Repo laden</button>
                <button type="button" onClick={() => handleUserTabClick('remote')}>Remote Memory</button>
                <button type="button" onClick={() => handleUserTabClick('telemetry')}>Telemetry öffnen</button>
              </div>
            </div>

            <div className="mt-4 grid gap-2 text-xs md:grid-cols-4">
              <div className="rounded bg-slate-900/70 p-3">Repo: {repoSnapshotStatus.ready ? 'ready' : 'not ready'}</div>
              <div className="rounded bg-slate-900/70 p-3">Runtime: {sequentialRuntime.activeStep ?? 'idle'}</div>
              <div className="rounded bg-slate-900/70 p-3">Workflow: {workflowReport?.status ?? 'idle'}</div>
              <div className="rounded bg-slate-900/70 p-3">Patterns: {activePatternCount}</div>
            </div>

            <div className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-300">
              <h3 className="font-bold uppercase tracking-wide text-slate-200">Remote Memory Snapshot</h3>
              <p className="mt-2">
                Enabled: {remoteMemoryConfig.enabled ? 'yes' : 'no'} · Mode: {remoteMemoryConfig.mode} · Workspace: {remoteMemoryConfig.workspaceId} · Collection: {remoteMemoryConfig.collectionName}
              </p>
              <p className="mt-1 text-slate-500">Remote Memory bleibt optional und consent-gated. Änderungen laufen im Remote-Memory-Tab.</p>
            </div>

            <SequentialRuntimePanel state={sequentialRuntime} />
            <RuntimeValidationCoveragePanel report={coverageReport} />
            <ScanFindingRegistryPanel registry={scanRegistry} />
            <PatternMemoryContainer store={solutionPatternStore} onClear={resetPatternMemory} />
            <TelemetryContainer state={telemetry} expanded={telemetryExpanded} onExpandedChange={setTelemetryExpanded} />
          </section>
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'repo' ? (
        <SovereignTabErrorBoundary tabId="repo" tabLabel="Repo">
          <RepoSnapshotContainer
            repoUrl={repoUrl}
            repoBranch={repoBranch}
            accessValue={githubToken}
            repoStatus={repoStatus}
            isRepoBusy={isRepoBusy}
            runtimeBusy={runtimeBusy}
            repoFiles={safeRepoFiles}
            memoryHints={solutionPatternHints}
            onRepoUrlChange={setRepoUrl}
            onRepoBranchChange={setRepoBranch}
            onAccessValueChange={setGithubToken}
            onLoadRepo={() => { void handleLoadRepoTree(); }}
            onSaveView={saveCurrentSession}
            onRestoreView={restoreSession}
            onClearView={clearSession}
          />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'readiness' ? (
        <SovereignTabErrorBoundary tabId="readiness" tabLabel="Readiness">
          <RepoReadinessPanel repoUrl={repoUrl} files={safeRepoFiles} status={repoStatus} />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'integrity' ? (
        <SovereignTabErrorBoundary tabId="integrity" tabLabel="Integrity">
          <RepoFileIntegrityMatrix files={safeRepoFiles} />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'findings' ? (
        <SovereignTabErrorBoundary tabId="findings" tabLabel="Findings">
          <ScanFindingRegistryPanel registry={scanRegistry} />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'builder' ? (
        <SovereignTabErrorBoundary tabId="builder" tabLabel="Builder">
          <RepoInsightPanelBridge
            repoFiles={safeRepoFiles}
            scanRegistry={scanRegistry}
            workflowReport={workflowReport}
            solutionPatternStore={solutionPatternStore}
            currentMission={mission}
            onSuggestionClick={(suggestion) => {
              setMission(suggestion.whyUseful);
            }}
          />
          <BuilderContainer
            mission={mission}
            repoReady={repoSnapshotStatus.ready}
            repoReason={repoSnapshotStatus.reason}
            repoBusy={isRepoBusy}
            runtimeBusy={runtimeBusy}
            isPublishing={isPublishing}
            sovereignSummary={sovereignSummary}
            sovereignPreview={sovereignPreview}
            onMissionChange={setMission}
            onGenerateIdeas={generateRepoIdeas}
            onGenerateErrorWorkflow={generateErrorWorkflow}
            onPublishDraftPr={() => { void publishDraftPr(); }}
            openhandsReady={openhandsConfig.ready}
            openhandsConfig={openhandsConfig}
            openhandsJobStatus={openhandsJob.status}
            openhandsIsRunning={isPollingOpenHands}
            onStartOpenHands={startOpenHandsJob}
            onCancelOpenHands={cancelOpenHandsJob}
          />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'chat' ? (
        <SovereignTabErrorBoundary tabId="chat" tabLabel="Chat AI">
          <ChatRuntimePanel />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'files' ? (
        <SovereignTabErrorBoundary tabId="files" tabLabel="Files">
          <GeneratedFileReviewPanel pkg={lastPackage} />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'diff' ? (
        <SovereignTabErrorBoundary tabId="diff" tabLabel="Diff">
          <GeneratedFileDiffPreviewPanel
            report={diffReport}
            isLoading={isLoadingDiffSources || runtimeBusy}
            onLoadSources={() => { void loadGeneratedFileSources(); }}
          />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'workflow' ? (
        <SovereignTabErrorBoundary tabId="workflow" tabLabel="Workflow">
          <WorkflowContainer
            mode="watch"
            report={workflowReport}
            repairPlan={repairPlan}
            isWatching={isWatchingWorkflow}
            runtimeBusy={runtimeBusy}
            hasDraftCommit={Boolean(lastDraftCommitSha)}
            onWatch={() => { void watchLatestWorkflow(); }}
            onUseRepairMission={useRepairMission}
          />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'repair' ? (
        <SovereignTabErrorBoundary tabId="repair" tabLabel="Repair">
          <WorkflowContainer
            mode="repair"
            report={workflowReport}
            repairPlan={repairPlan}
            isWatching={isWatchingWorkflow}
            runtimeBusy={runtimeBusy}
            hasDraftCommit={Boolean(lastDraftCommitSha)}
            onWatch={() => { void watchLatestWorkflow(); }}
            onUseRepairMission={useRepairMission}
          />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'health' ? (
        <SovereignTabErrorBoundary tabId="health" tabLabel="Health">
          <SovereignHealthPanel report={healthReport} />
          <ModelHealthPanel />
          <ChatRuntimePanel />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'runtime' ? (
        <SovereignTabErrorBoundary tabId="runtime" tabLabel="Runtime">
          <SequentialRuntimePanel state={sequentialRuntime} />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'coverage' ? (
        <SovereignTabErrorBoundary tabId="coverage" tabLabel="Coverage">
          <RuntimeValidationCoveragePanel report={coverageReport} />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'memory' ? (
        <SovereignTabErrorBoundary tabId="memory" tabLabel="Pattern Memory">
          <PatternMemoryContainer store={solutionPatternStore} onClear={resetPatternMemory} />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'remote' ? (
        <SovereignTabErrorBoundary tabId="remote" tabLabel="Remote Memory">
          <RemoteMemoryContainer
            config={remoteMemoryConfig}
            onConfigChange={setRemoteMemoryConfig}
            scanRegistry={scanRegistry}
            solutionPatternStore={solutionPatternStore}
            onSolutionPatternStoreChange={setSolutionPatternStore}
            mission={mission}
            onTelemetry={pushTelemetry}
          />
        </SovereignTabErrorBoundary>
      ) : null}

      {activeTab === 'telemetry' ? (
        <SovereignTabErrorBoundary tabId="telemetry" tabLabel="Telemetry">
          <TelemetryContainer state={telemetry} expanded={telemetryExpanded} onExpandedChange={setTelemetryExpanded} />
        </SovereignTabErrorBoundary>
      ) : null}
    </div>
  </LlmAdapterProvider>
  );
};

export default App;
