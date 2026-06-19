import './runtime-adapter';
import React, { useEffect, useRef, useState } from 'react';
import { buildGitHubHeaders, stripTokenFromText } from './features/github/githubAuthSession';
import { parseGithubRepoUrl } from './features/github/utils';
import { publishPackageAsDraftPr } from './features/github/githubPackagePublisher';
import { useGithubRepo } from './features/github/hooks/useGithubRepo';
import { GeneratedFileDiffPreviewPanel } from './features/product/components/GeneratedFileDiffPreviewPanel';
import { GeneratedFileReviewPanel } from './features/product/components/GeneratedFileReviewPanel';
import { RemoteMemoryContainer } from './features/product/containers/RemoteMemoryContainer';
import { BuilderContainer } from './features/product/containers/BuilderContainer';
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
import { getRepoSnapshotStatus } from './features/product/runtime/sovereignFunctionalGuards';
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
  summarizeSovereignPackage,
} from './features/product/runtime/sovereignPackageFromRepoFiles';
import { buildWorkflowRepairPlan } from './features/product/runtime/workflowRepairPlan';
import { fetchWorkflowWatchReport, type WorkflowWatchReport } from './features/product/runtime/workflowWatch';
import type { SovereignImplementationPackage } from './features/product/runtime/sovereignRuntime';
import { UserSession } from './shared/types/user';
import { makeId } from './shared/utils/crypto';
import { LoginView } from './components/LoginView';
import { wallClockMs } from './mobile-operator-coach';

// Coach State Types - für Runtime-Integration
type CoachLamp = 'green' | 'yellow' | 'red';
type CoachSource = 'runtime-library' | 'workflow' | 'repair' | 'telemetry' | 'pattern-memory' | 'remote-memory' | 'runtime' | 'repo' | 'dom-fallback' | 'unknown';

interface CoachRuntimeState {
  lamp: CoachLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source: CoachSource;
  tick: number;
  updatedAt: number;
}

// Leitet Coach-State aus echtem Runtime ab - keine Mocks, keine Stubs
function deriveCoachStateFromRuntime(
  sequentialRuntime: SequentialRuntimeState,
  repoReady: boolean,
  hasPackage: boolean,
  workflowStatus?: string,
  isPublishing?: boolean,
  isWatchingWorkflow?: boolean,
  hasActivePatterns?: boolean
): CoachRuntimeState {
  const now = wallClockMs();
  
  // 1. Wenn gerade ein Step läuft
  if (sequentialRuntime.activeStep) {
    const step = sequentialRuntime.activeStep;
    const stepRecord = sequentialRuntime.steps[step];
    
    if (stepRecord?.status === 'running') {
      const stepLabels: Record<string, string> = {
        'repo-load': 'Repository wird geladen',
        'package-build': 'Package wird erstellt',
        'diff-load': 'Diff-Quellen werden geladen',
        'draft-pr-publish': 'Draft PR wird erstellt',
        'workflow-watch': 'Workflow wird beobachtet',
        'repair-plan': 'Repair-Plan wird erstellt'
      };
      return {
        lamp: 'green',
        title: stepLabels[step] || `Schritt: ${step}`,
        message: stepRecord.message || 'Prozess läuft...',
        action: 'Bitte warten',
        thinking: true,
        source: 'runtime-library',
        tick: now,
        updatedAt: now
      };
    }
    
    if (stepRecord?.status === 'failed') {
      return {
        lamp: 'red',
        title: 'Schritt fehlgeschlagen',
        message: stepRecord.message || 'Ein Prozessschritt ist fehlgeschlagen.',
        action: 'Repair prüfen',
        thinking: false,
        source: 'runtime-library',
        tick: now,
        updatedAt: now
      };
    }
  }
  
  // 2. Wenn Repo nicht geladen
  if (!repoReady) {
    return {
      lamp: 'yellow',
      title: 'Repository laden',
      message: 'Bitte GitHub-URL eingeben und Repository laden.',
      action: 'Zuerst Repo laden',
      thinking: false,
      source: 'repo',
      tick: now,
      updatedAt: now
    };
  }
  
  // 3. Wenn Draft PR erstellt wird
  if (isPublishing) {
    return {
      lamp: 'green',
      title: 'Draft PR wird erstellt',
      message: 'Branch und Commit werden erstellt...',
      action: 'Bitte warten',
      thinking: true,
      source: 'workflow',
      tick: now,
      updatedAt: now
    };
  }
  
  // 4. Wenn Workflow beobachtet wird
  if (isWatchingWorkflow) {
    return {
      lamp: 'green',
      title: 'Workflow wird beobachtet',
      message: 'CI/CD Checks werden überwacht...',
      action: 'Bitte warten',
      thinking: true,
      source: 'workflow',
      tick: now,
      updatedAt: now
    };
  }
  
  // 5. Wenn Workflow fehlgeschlagen
  if (workflowStatus === 'red') {
    return {
      lamp: 'red',
      title: 'Workflow fehlgeschlagen',
      message: 'Die CI/CD Checks sind fehlgeschlagen.',
      action: 'Repair prüfen',
      thinking: false,
      source: 'workflow',
      tick: now,
      updatedAt: now
    };
  }
  
  // 6. Wenn Package bereit
  if (hasPackage) {
    if (workflowStatus === 'green') {
      return {
        lamp: 'green',
        title: 'Fertig!',
        message: 'Package erstellt und Workflow erfolgreich.',
        action: 'Diff prüfen',
        thinking: false,
        source: 'runtime-library',
        tick: now,
        updatedAt: now
      };
    }
    return {
      lamp: 'green',
      title: 'Package bereit',
      message: 'Sovereign-Paket wurde erstellt. Diff und Files prüfen.',
      action: 'Weiter mit Diff',
      thinking: false,
      source: 'runtime-library',
      tick: now,
      updatedAt: now
    };
  }
  
  // 7. Default: bereit für Auftrag
  return {
    lamp: 'green',
    title: 'Bereit für Auftrag',
    message: 'Repository ist geladen. Auftrag eingeben und Package erstellen.',
    action: 'Package bauen',
    thinking: false,
    source: 'runtime-library',
    tick: now,
    updatedAt: now
  };
}

type SovereignTab = 'monitor' | SovereignAutoViewTab;

const DEFAULT_MISSION = 'README + Update History';

const tabs: Array<{ id: SovereignTab; label: string }> = [
  { id: 'repo', label: 'Repo' },
  { id: 'builder', label: 'Builder' },
  { id: 'files', label: 'Files' },
  { id: 'diff', label: 'Diff' },
  { id: 'workflow', label: 'Workflow' },
  { id: 'repair', label: 'Repair' },
  { id: 'remote', label: 'Remote Memory' },
  { id: 'memory', label: 'Pattern Memory' },
  { id: 'telemetry', label: 'Telemetry' },
  { id: 'monitor', label: 'Live Monitor' },
  { id: 'readiness', label: 'Readiness' },
  { id: 'integrity', label: 'Integrity' },
  { id: 'findings', label: 'Findings' },
  { id: 'health', label: 'Health' },
  { id: 'runtime', label: 'Runtime' },
  { id: 'coverage', label: 'Coverage' },
];

const automationModes: SovereignAutomationMode[] = ['manual', 'auto-review', 'full-auto-draft-pr'];

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
  const [workflowReport, setWorkflowReport] = useState<WorkflowWatchReport | null>(null);
  const [diffSources, setDiffSources] = useState<SourceFileSnapshot[]>([]);
  const [isLoadingDiffSources, setIsLoadingDiffSources] = useState(false);
  const [isWatchingWorkflow, setIsWatchingWorkflow] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [activeTab, setActiveTab] = useState<SovereignTab>('repo');
  const [telemetryExpanded, setTelemetryExpanded] = useState(true);
  const [telemetry, setTelemetry] = useState(() => createInitialTelemetryState());
  const [scanRegistry, setScanRegistry] = useState(() => createScanFindingRegistry());
  const [solutionPatternStore, setSolutionPatternStore] = useState(loadSafeSolutionPatternStore);
  const [remoteMemoryConfig, setRemoteMemoryConfig] = useState<ExternalMemorySyncConfig>(() => ({
    ...createExternalMemorySyncConfig(),
    gatewayUrl: 'http://46.202.154.25:8088',
    workspaceId: 'Pattern',
    collectionName: 'sovereign_logic_patterns',
    contributorId: 'sovereign-local-install',
    allowSelfHostedHttp: true,
  }));

  const sequentialRuntimeRef = useRef<SequentialRuntimeState>(createSequentialRuntimeState());
  const [sequentialRuntime, setSequentialRuntime] = useState(() => sequentialRuntimeRef.current);
  const [automationMode, setAutomationMode] = useState<SovereignAutomationMode>('manual');
  const [lastAutoRunKey, setLastAutoRunKey] = useState('');
  const [automationStatus, setAutomationStatus] = useState('Manual mode is active.');
  const lastAutoViewReasonRef = useRef('');

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
    loadRepoTree,
    restoreRepoSnapshot,
    clearRepoSnapshot,
  } = useGithubRepo();

  const safeRepoFiles = Array.isArray(repoFiles) ? repoFiles : [];
  const safeDiffSources = Array.isArray(diffSources) ? diffSources : [];
  const repoSnapshotStatus = getRepoSnapshotStatus(safeRepoFiles);
  const runtimeBusy = Boolean(sequentialRuntime.activeStep);
  const currentMission = normalizeMission(mission);
  const packageInputKey = buildAutomationRunKey({
    mode: 'manual',
    repoUrl,
    repoBranch,
    mission: currentMission,
    repoFileCount: safeRepoFiles.length,
  });
  const automationRunKey = buildAutomationRunKey({
    mode: automationMode,
    repoUrl,
    repoBranch,
    mission: currentMission,
    repoFileCount: safeRepoFiles.length,
  });
  const hasFreshPackage = Boolean(lastPackage && lastPackageKey === packageInputKey);
  const latestGeneratedReview = lastPackage ? reviewGeneratedFiles(lastPackage.files) : null;
  const diffReport = lastPackage ? buildGeneratedFileDiffReport(lastPackage.files, safeDiffSources) : null;
  const repairPlan = buildWorkflowRepairPlan(workflowReport);
  const healthReport = buildSovereignHealthReport({
    repoFiles: safeRepoFiles,
    generatedFileReview: latestGeneratedReview,
    workflowWatch: workflowReport,
    telemetry,
  });
  const coverageReport = buildRuntimeValidationCoverageReport();
  const solutionPatternHints = formatSolutionPatternHints(solutionPatternStore);
  const activePatternCount = Array.isArray(solutionPatternStore.patterns)
    ? solutionPatternStore.patterns.filter((pattern) => pattern.status === 'active').length
    : 0;

  // Coach-State aus echtem Runtime ableiten - für mobile-operator-coach
  const coachState = deriveCoachStateFromRuntime(
    sequentialRuntime,
    repoSnapshotStatus.ready,
    Boolean(lastPackage),
    workflowReport?.status,
    isPublishing,
    isWatchingWorkflow,
    activePatternCount > 0
  );

  // Expose Coach-State an Fenster für mobile-operator-coach
  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    // Setze globalen Coach-State
    (window as any).__sovereignRuntimeCoachState = coachState;
    
    // Broadcast Event für Coach-Update
    window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
      detail: coachState
    }));
  }, [coachState]);

  const pushTelemetry = (
    stage: Parameters<typeof createTelemetryEvent>[0],
    level: Parameters<typeof createTelemetryEvent>[1],
    label: string,
    message: string,
    details?: Parameters<typeof createTelemetryEvent>[4],
  ) => {
    setTelemetry((state) => appendTelemetryEvent(state, createTelemetryEvent(stage, level, label, message, details)));
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const result = saveSolutionPatternStore(window.localStorage, solutionPatternStore);
    if (!result.ok) pushTelemetry('memory', 'warning', 'aha-memory:persist-failed', result.summary);
    // Store persistence follows solutionPatternStore changes only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [solutionPatternStore]);

  useEffect(() => {
    const routerActiveTab: SovereignAutoViewTab = activeTab === 'monitor' ? 'repo' : activeTab;
    const decision = decideSovereignAutoView({
      mode: automationMode,
      activeStep: sequentialRuntime.activeStep,
      activeTab: routerActiveTab,
      hasPackage: Boolean(lastPackage),
      isPublishing,
      isWatchingWorkflow,
      workflowStatus: workflowReport?.status ?? 'idle',
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

  const buildPackageCore = (
    nextMission: string,
    nextPackageKey = packageInputKey,
  ): SovereignImplementationPackage | null => {
    try {
      const cleanMission = normalizeMission(nextMission);
      pushTelemetry('package', 'info', 'package:build-start', 'Building Sovereign package.', { files: safeRepoFiles.length });

      const missionWithAha = solutionPatternHints ? `${cleanMission}\n\n${solutionPatternHints}` : cleanMission;
      const pkg = buildSovereignPackageFromRepoFiles({
        mission: missionWithAha,
        repoFiles: safeRepoFiles,
        selectedFilePath: 'README.md',
        previousPreview: sovereignPreview,
      });

      const review = reviewGeneratedFiles(pkg.files);
      assertGeneratedFileReviewSafe(review);

      setMission(cleanMission);
      setLastPackage(pkg);
      setLastPackageKey(nextPackageKey);
      setDiffSources([]);

      setSovereignSummary(
        `${summarizeSovereignPackage(pkg, safeRepoFiles)}\n${review.summary}${solutionPatternHints ? `\n${solutionPatternHints}` : ''}`,
      );

      setSovereignPreview(JSON.stringify({
        architecture: pkg.architecture,
        brain: pkg.brain,
        files: pkg.files.map((file) => ({ path: file.path, reason: file.reason })),
        fileReview: review,
        remoteAhaMemory: solutionPatternHints,
        suggestions: pkg.suggestions,
      }, null, 2));

      pushTelemetry('guards', 'success', 'guards:passed', 'Functional guards and generated-file review accepted package.', {
        generatedFiles: pkg.files.length,
      });

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
    const pkg = buildPackageCore(nextMission, nextPackageKey);
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
    setWorkflowReport(null);
    setLastAutoRunKey('');
    setSovereignPreview('');
    setSovereignSummary('Noch kein Sovereign-Paket erzeugt.');

    pushTelemetry('memory', 'info', 'memory:cleared', 'Visible session state cleared. Stored memory is unchanged.');
  };

  const publishDraftPrForPackage = async (pkg: SovereignImplementationPackage): Promise<boolean> => {
    const result = await runSequentialStep('draft-pr-publish', async () => {
      const review = reviewGeneratedFiles(pkg.files);
      assertGeneratedFileReviewSafe(review);

      if (!githubToken.trim()) {
        throw new Error('GitHub PAT fehlt. Draft PR wird nur mit bewusst eingegebenem Token erstellt.');
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
    if (!user) return;

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
      return;
    }

    if (decision.blockedReason) {
      setAutomationStatus(decision.blockedReason);
      return;
    }

    if (decision.shouldBuildPackage && automationMode === 'auto-review') {
      setLastAutoRunKey(automationRunKey);
      setAutomationStatus('Auto Review is building and reviewing generated files.');
      pushTelemetry('workflow', 'info', 'automation:auto-review', 'Auto Review triggered package build.');
      void buildPackage(currentMission, packageInputKey);
      return;
    }

    if (automationMode === 'full-auto-draft-pr' && decision.shouldPublishDraftPr) {
      setLastAutoRunKey(automationRunKey);
      setAutomationStatus('Full Auto is building, reviewing and creating a Draft PR.');
      pushTelemetry('workflow', 'info', 'automation:full-auto', 'Full Auto triggered guarded Draft PR flow.');

      void (async () => {
        const pkg = hasFreshPackage && lastPackage ? lastPackage : await buildPackage(currentMission, packageInputKey);
        if (pkg) await publishDraftPrForPackage(pkg);
      })();
    }
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
    <div className="min-h-screen p-4">
      <h1 className="font-bold">Sovereign Canvas Tool</h1>

      <div className="mt-4 flex flex-wrap gap-2 border-b border-slate-800 pb-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={activeTab === tab.id ? 'font-bold underline' : ''}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-bold">Automation Mode</h2>
            <p className="mt-1 text-xs text-slate-400">{automationStatus}</p>
          </div>

          <select
            value={automationMode}
            onChange={(event) => changeAutomationMode(event.target.value as SovereignAutomationMode)}
            className="rounded border border-slate-700 bg-slate-900 p-2 text-sm"
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
              <button type="button" onClick={() => setActiveTab('repo')}>Repo laden</button>
              <button type="button" onClick={() => setActiveTab('remote')}>Remote Memory</button>
              <button type="button" onClick={() => setActiveTab('telemetry')}>Telemetry öffnen</button>
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
      ) : null}

      {activeTab === 'repo' ? (
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
      ) : null}

      {activeTab === 'readiness' ? (
        <RepoReadinessPanel repoUrl={repoUrl} files={safeRepoFiles} status={repoStatus} />
      ) : null}

      {activeTab === 'integrity' ? (
        <RepoFileIntegrityMatrix files={safeRepoFiles} />
      ) : null}

      {activeTab === 'findings' ? (
        <ScanFindingRegistryPanel registry={scanRegistry} />
      ) : null}

      {activeTab === 'builder' ? (
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
        />
      ) : null}

      {activeTab === 'files' ? (
        <GeneratedFileReviewPanel pkg={lastPackage} />
      ) : null}

      {activeTab === 'diff' ? (
        <GeneratedFileDiffPreviewPanel
          report={diffReport}
          isLoading={isLoadingDiffSources || runtimeBusy}
          onLoadSources={() => { void loadGeneratedFileSources(); }}
        />
      ) : null}

      {activeTab === 'workflow' ? (
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
      ) : null}

      {activeTab === 'repair' ? (
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
      ) : null}

      {activeTab === 'health' ? (
        <SovereignHealthPanel report={healthReport} />
      ) : null}

      {activeTab === 'runtime' ? (
        <SequentialRuntimePanel state={sequentialRuntime} />
      ) : null}

      {activeTab === 'coverage' ? (
        <RuntimeValidationCoveragePanel report={coverageReport} />
      ) : null}

      {activeTab === 'memory' ? (
        <PatternMemoryContainer store={solutionPatternStore} onClear={resetPatternMemory} />
      ) : null}

      {activeTab === 'remote' ? (
        <RemoteMemoryContainer
          config={remoteMemoryConfig}
          onConfigChange={setRemoteMemoryConfig}
          scanRegistry={scanRegistry}
          solutionPatternStore={solutionPatternStore}
          onSolutionPatternStoreChange={setSolutionPatternStore}
          mission={mission}
          onTelemetry={pushTelemetry}
        />
      ) : null}

      {activeTab === 'telemetry' ? (
        <TelemetryContainer state={telemetry} expanded={telemetryExpanded} onExpandedChange={setTelemetryExpanded} />
      ) : null}
    </div>
  );
};

export default App;
