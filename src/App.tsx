import './runtime-adapter';
import React, { useEffect, useRef, useState } from 'react';
import { buildGitHubHeaders, stripTokenFromText } from './features/github/githubAuthSession';
import { parseGithubRepoUrl } from './features/github/utils';
import { publishPackageAsDraftPr } from './features/github/githubPackagePublisher';
import { useGithubRepo } from './features/github/hooks/useGithubRepo';
import { RepoFileList } from './features/github/components/RepoFileList';
import { GeneratedFileDiffPreviewPanel } from './features/product/components/GeneratedFileDiffPreviewPanel';
import { GeneratedFileReviewPanel } from './features/product/components/GeneratedFileReviewPanel';
import { RemoteMemoryPanel } from './features/product/components/RemoteMemoryPanel';
import { RepoFileIntegrityMatrix } from './features/product/components/RepoFileIntegrityMatrix';
import { RepoReadinessPanel } from './features/product/components/RepoReadinessPanel';
import { RuntimeValidationCoveragePanel } from './features/product/components/RuntimeValidationCoveragePanel';
import { ScanFindingRegistryPanel } from './features/product/components/ScanFindingRegistryPanel';
import { SequentialRuntimePanel } from './features/product/components/SequentialRuntimePanel';
import { SovereignHealthPanel } from './features/product/components/SovereignHealthPanel';
import { SovereignTelemetryPanel } from './features/product/components/SovereignTelemetryPanel';
import { WorkflowRepairPanel } from './features/product/components/WorkflowRepairPanel';
import { WorkflowWatchPanel } from './features/product/components/WorkflowWatchPanel';
import {
  AUTOMATION_MODE_LABELS,
  buildAutomationRunKey,
  decideSovereignAutomation,
  describeAutomationMode,
  type SovereignAutomationMode,
} from './features/product/runtime/sovereignAutomationMode';
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
  buildExternalMemorySyncPayload,
  checkExternalMemoryHealth,
  createExternalMemorySyncConfig,
  pullExternalMemoryUpdates,
  searchExternalMemory,
  syncExternalMemory,
  type ExternalMemoryHealthResult,
  type ExternalMemoryPullUpdatesResult,
  type ExternalMemorySearchResult,
  type ExternalMemorySyncResult,
} from './features/product/runtime/externalMemorySync';
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

type SovereignTab = 'repo' | 'readiness' | 'integrity' | 'findings' | 'builder' | 'files' | 'diff' | 'workflow' | 'repair' | 'health' | 'runtime' | 'coverage' | 'remote' | 'telemetry';

const tabs: Array<{ id: SovereignTab; label: string }> = [
  { id: 'repo', label: 'Repo' },
  { id: 'readiness', label: 'Readiness' },
  { id: 'integrity', label: 'Integrity' },
  { id: 'findings', label: 'Findings' },
  { id: 'builder', label: 'Builder' },
  { id: 'files', label: 'Files' },
  { id: 'diff', label: 'Diff' },
  { id: 'workflow', label: 'Workflow' },
  { id: 'repair', label: 'Repair' },
  { id: 'health', label: 'Health' },
  { id: 'runtime', label: 'Runtime' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'remote', label: 'Remote' },
  { id: 'telemetry', label: 'Telemetry' },
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

const App: React.FC = () => {
  const [user, setUser] = useState<UserSession | null>(null);
  const [mission, setMission] = useState('README + Update History');
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
  const [telemetryExpanded, setTelemetryExpanded] = useState(false);
  const [telemetry, setTelemetry] = useState(() => createInitialTelemetryState());
  const [scanRegistry, setScanRegistry] = useState(() => createScanFindingRegistry());
  const [remoteMemoryConfig, setRemoteMemoryConfig] = useState(() => ({
    ...createExternalMemorySyncConfig(),
    gatewayUrl: 'http://46.202.154.25:8088',
    workspaceId: 'Pattern',
    collectionName: 'sovereign_logic_patterns',
    allowSelfHostedHttp: true,
  }));
  const [remoteMemoryHealth, setRemoteMemoryHealth] = useState<ExternalMemoryHealthResult | null>(null);
  const [remoteMemorySync, setRemoteMemorySync] = useState<ExternalMemorySyncResult | null>(null);
  const [remoteMemorySearch, setRemoteMemorySearch] = useState<ExternalMemorySearchResult | null>(null);
  const [remoteMemoryUpdates, setRemoteMemoryUpdates] = useState<ExternalMemoryPullUpdatesResult | null>(null);
  const [isRemoteMemoryBusy, setIsRemoteMemoryBusy] = useState(false);
  const sequentialRuntimeRef = useRef<SequentialRuntimeState>(createSequentialRuntimeState());
  const [sequentialRuntime, setSequentialRuntime] = useState(() => sequentialRuntimeRef.current);
  const [automationMode, setAutomationMode] = useState<SovereignAutomationMode>('manual');
  const [lastAutoRunKey, setLastAutoRunKey] = useState('');
  const [automationStatus, setAutomationStatus] = useState('Manual mode is active.');
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
  const repoSnapshotStatus = getRepoSnapshotStatus(repoFiles);
  const runtimeBusy = Boolean(sequentialRuntime.activeStep);
  const actionDisabled = isRepoBusy || runtimeBusy || !repoSnapshotStatus.ready;
  const packageInputKey = buildAutomationRunKey({
    mode: 'manual',
    repoUrl,
    repoBranch,
    mission,
    repoFileCount: repoFiles.length,
  });
  const automationRunKey = buildAutomationRunKey({
    mode: automationMode,
    repoUrl,
    repoBranch,
    mission,
    repoFileCount: repoFiles.length,
  });
  const hasFreshPackage = Boolean(lastPackage && lastPackageKey === packageInputKey);
  const latestGeneratedReview = lastPackage ? reviewGeneratedFiles(lastPackage.files) : null;
  const diffReport = lastPackage ? buildGeneratedFileDiffReport(lastPackage.files, diffSources) : null;
  const repairPlan = buildWorkflowRepairPlan(workflowReport);
  const healthReport = buildSovereignHealthReport({
    repoFiles,
    generatedFileReview: latestGeneratedReview,
    workflowWatch: workflowReport,
    telemetry,
  });
  const coverageReport = buildRuntimeValidationCoverageReport();

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
    if (!repoFiles.length) return;
    const startedAt = Date.now();
    const findings = collectRepoPathFindings(repoFiles, startedAt);
    const completedAt = Date.now();
    setScanRegistry((current) => {
      const next = applyScanFindings(current, 'repo-path-scan', findings, startedAt, completedAt);
      return next;
    });
    pushTelemetry('workflow', findings.some((finding) => finding.severity === 'critical' || finding.severity === 'high') ? 'warning' : 'success', 'scan:repo-path-finished', `Repo scan abgeschlossen: ${findings.length} finding(s).`);
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
    hasDiffSources: diffSources.length > 0,
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
        const failed = finishSequentialStep(sequentialRuntimeRef.current, step, 'failed', message);
        setSequentialState(failed);
      }
      setSovereignSummary(message);
      pushTelemetry('workflow', 'error', `sequence:${step}:failed`, message);
      return null;
    }
  };

  const withRemoteMemoryBusy = async <T,>(task: () => Promise<T>): Promise<T | null> => {
    setIsRemoteMemoryBusy(true);
    try {
      return await task();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Remote memory action failed.';
      pushTelemetry('memory', 'error', 'remote-memory:failed', stripTokenFromText(message, githubToken));
      return null;
    } finally {
      setIsRemoteMemoryBusy(false);
    }
  };

  const handleRemoteMemoryHealth = () => {
    void withRemoteMemoryBusy(async () => {
      const result = await checkExternalMemoryHealth({ config: remoteMemoryConfig });
      setRemoteMemoryHealth(result);
      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:health', result.summary);
      return result;
    });
  };

  const handleRemoteMemorySync = () => {
    void withRemoteMemoryBusy(async () => {
      const payload = buildExternalMemorySyncPayload({ config: remoteMemoryConfig, scanRegistry });
      const result = await syncExternalMemory({ config: remoteMemoryConfig, payload });
      setRemoteMemorySync(result);
      pushTelemetry('memory', result.accepted ? 'success' : 'warning', 'remote-memory:sync', result.summary, { items: payload.items.length });
      return result;
    });
  };

  const handleRemoteMemorySearch = () => {
    void withRemoteMemoryBusy(async () => {
      const result = await searchExternalMemory({ config: remoteMemoryConfig, query: mission.trim() || summarizeScanFindingRegistry(scanRegistry), limit: 8 });
      setRemoteMemorySearch(result);
      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:search', result.summary, { items: result.items.length });
      return result;
    });
  };

  const handleRemoteMemoryPullUpdates = () => {
    void withRemoteMemoryBusy(async () => {
      const result = await pullExternalMemoryUpdates({ config: remoteMemoryConfig });
      setRemoteMemoryUpdates(result);
      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:pull-updates', result.summary, { items: result.items.length });
      return result;
    });
  };

  const loadGeneratedFileSources = async () => {
    await runSequentialStep('diff-load', async () => {
      if (!lastPackage) {
        throw new Error('Build a Sovereign package before loading diff sources.');
      }
      const parsed = parseGithubRepoUrl(repoUrl);
      if (!parsed) {
        throw new Error('Cannot load diff sources from an invalid GitHub repo URL.');
      }

      setIsLoadingDiffSources(true);
      pushTelemetry('workflow', 'info', 'diff:load-start', 'Loading source snapshots for generated files.', { files: lastPackage.files.length });

      const headers = buildGitHubHeaders({ token: githubToken });
      const refQuery = repoBranch.trim() ? `?ref=${encodeURIComponent(repoBranch.trim())}` : '';

      try {
        const snapshots = await Promise.all(lastPackage.files.map(async (file): Promise<SourceFileSnapshot> => {
          const path = encodeGitHubContentPath(file.path);
          const url = `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/contents/${path}${refQuery}`;
          try {
            const response = await fetch(url, { headers });
            if (response.status === 404) return { path: file.path, content: null, found: false };
            if (!response.ok) return { path: file.path, content: null, found: false };
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
        setSovereignSummary(report.summary);
        pushTelemetry('workflow', 'success', 'diff:load-finished', stripTokenFromText(report.summary, githubToken));
        setActiveTab('diff');
        return report;
      } finally {
        setIsLoadingDiffSources(false);
      }
    });
  };

  const watchLatestWorkflow = async (commitSha = lastDraftCommitSha, branch = lastDraftBranch) => {
    const report = await runSequentialStep('workflow-watch', async () => {
      setIsWatchingWorkflow(true);
      pushTelemetry('workflow', 'info', 'workflow:watch-start', 'Watching GitHub commit checks.', { commitSha: commitSha || 'none' });
      try {
        const nextReport = await fetchWorkflowWatchReport({
          repoUrl,
          token: githubToken,
          commitSha,
          branch,
        });
        setWorkflowReport(nextReport);

        const scanStartedAt = Date.now();
        const workflowFindingBridge = applyWorkflowScanAndBuildGate(scanRegistry, nextReport, scanStartedAt, Date.now());
        setScanRegistry(workflowFindingBridge.registry);

        pushTelemetry(
          'workflow',
          nextReport.status === 'red' ? 'error' : nextReport.status === 'green' ? 'success' : 'warning',
          'workflow:watch-finished',
          stripTokenFromText(nextReport.summary, githubToken),
        );
        pushTelemetry(
          'workflow',
          workflowFindingBridge.gate.allowed ? 'success' : 'warning',
          'scan:workflow-findings-synced',
          stripTokenFromText(workflowFindingBridge.summary, githubToken),
          { blockers: workflowFindingBridge.gate.blockers.length },
        );
        setActiveTab(nextReport.status === 'red' ? 'repair' : 'workflow');
        return nextReport;
      } finally {
        setIsWatchingWorkflow(false);
      }
    }, { hasDraftCommit: Boolean(commitSha) });
    return report;
  };

  const buildPackageCore = (nextMission: string, nextPackageKey = packageInputKey): SovereignImplementationPackage | null => {
    try {
      pushTelemetry('package', 'info', 'package:build-start', 'Building Sovereign package.', { files: repoFiles.length });
      const pkg = buildSovereignPackageFromRepoFiles({
        mission: nextMission,
        repoFiles,
        selectedFilePath: 'README.md',
        previousPreview: sovereignPreview,
      });

      const review = reviewGeneratedFiles(pkg.files);
      assertGeneratedFileReviewSafe(review);

      setMission(nextMission);
      setLastPackage(pkg);
      setLastPackageKey(nextPackageKey);
      setDiffSources([]);
      setSovereignSummary(`${summarizeSovereignPackage(pkg, repoFiles)}\n${review.summary}`);
      setSovereignPreview(JSON.stringify({
        architecture: pkg.architecture,
        brain: pkg.brain,
        files: pkg.files.map((file) => ({ path: file.path, reason: file.reason })),
        fileReview: review,
        suggestions: pkg.suggestions,
      }, null, 2));
      pushTelemetry('guards', 'success', 'guards:passed', 'Functional guards and generated-file review accepted package.', { generatedFiles: pkg.files.length });
      setActiveTab('files');
      return pkg;
    } catch (error) {
      setLastPackage(null);
      setLastPackageKey('');
      setDiffSources([]);
      const message = error instanceof Error ? error.message : 'Sovereign-Paket konnte nicht erzeugt werden.';
      setSovereignSummary(stripTokenFromText(message, githubToken));
      pushTelemetry('guards', 'error', 'guards:failed', stripTokenFromText(message, githubToken));
      return null;
    }
  };

  const buildPackage = async (nextMission: string, nextPackageKey = packageInputKey): Promise<SovereignImplementationPackage | null> => {
    return runSequentialStep('package-build', async () => {
      const pkg = buildPackageCore(nextMission, nextPackageKey);
      if (!pkg) throw new Error('Package build failed.');
      return pkg;
    });
  };

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
      setActiveTab('readiness');
      return true;
    });
  };

  const generateRepoIdeas = () => {
    void buildPackage(mission.trim() || 'README + Update History');
  };

  const generateErrorWorkflow = () => {
    void buildPackage('Workflow Fehleranalyse + Runtime Check + Test Plan');
  };

  const useRepairMission = (nextMission: string) => {
    void runSequentialStep('repair-plan', async () => {
      setMission(nextMission);
      setLastPackage(null);
      setLastPackageKey('');
      setDiffSources([]);
      setSovereignSummary('Repair mission loaded into Builder. Run Ideen/Full Auto to generate a guarded repair package.');
      pushTelemetry('workflow', 'info', 'repair:mission-loaded', 'Workflow repair mission loaded into Builder.');
      setActiveTab('builder');
      return true;
    }, { hasWorkflowReport: Boolean(workflowReport) });
  };

  const saveCurrentSession = () => {
    if (!repoSnapshotStatus.ready) {
      pushTelemetry('memory', 'warning', 'memory:save-blocked', repoSnapshotStatus.reason);
      return;
    }
    const snapshot = createSessionMemorySnapshot({
      repoUrl,
      repoBranch,
      repoStatus,
      repoFiles,
      mission,
      sovereignSummary,
      sovereignPreview,
    });
    saveSessionMemory(window.localStorage, snapshot);
    pushTelemetry('memory', 'success', 'memory:saved', `Session saved ${formatSessionMemoryAge(snapshot)}.`, { files: repoFiles.length });
  };

  const restoreSession = () => {
    const snapshot = loadSessionMemory(window.localStorage);
    if (!snapshot) {
      pushTelemetry('memory', 'warning', 'memory:empty', 'No valid session memory snapshot found.');
      return;
    }

    restoreRepoSnapshot(snapshot);
    setMission(snapshot.mission);
    setSovereignSummary(`${snapshot.sovereignSummary}\nRestored ${formatSessionMemoryAge(snapshot)}.`);
    setSovereignPreview(snapshot.sovereignPreview);
    setLastPackage(null);
    setLastPackageKey('');
    setDiffSources([]);
    setLastDraftCommitSha('');
    setLastDraftBranch('');
    setWorkflowReport(null);
    setLastAutoRunKey('');
    pushTelemetry('memory', 'success', 'memory:restored', `Restored session from ${formatSessionMemoryAge(snapshot)}.`, { files: snapshot.repoFiles.length });
    setActiveTab('repo');
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
    setActiveTab('repo');
  };

  const publishDraftPrForPackage = async (pkg: SovereignImplementationPackage): Promise<boolean> => {
    const result = await runSequentialStep('draft-pr-publish', async () => {
      const review = reviewGeneratedFiles(pkg.files);
      assertGeneratedFileReviewSafe(review);

      if (!githubToken.trim()) {
        throw new Error('GitHub PAT fehlt. Draft PR wird nur mit bewusst eingegebenem Token erstellt.');
      }

      setIsPublishing(true);
      setSovereignSummary('Erstelle GitHub Branch, Commit und Draft PR...');
      pushTelemetry('github', 'info', 'github:draft-pr-start', 'Creating GitHub branch, commit and draft PR.', { files: pkg.files.length });
      try {
        return await publishPackageAsDraftPr({
          repoUrl,
          token: githubToken,
          baseBranch: repoBranch,
          branchNonce: String(Date.now()),
          title: `Sovereign Studio: ${mission.trim() || pkg.requestedWork}`,
          body: [
            'Generated by Sovereign Studio.',
            '',
            summarizeSovereignPackage(pkg, repoFiles),
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

    if (!result) {
      setActiveTab('files');
      return false;
    }

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
    const pkg = hasFreshPackage && lastPackage
      ? lastPackage
      : await buildPackage(mission.trim() || 'README + Update History', packageInputKey);
    if (!pkg) return;
    await publishDraftPrForPackage(pkg);
  };

  useEffect(() => {
    if (!user) return;
    const decision = decideSovereignAutomation({
      mode: automationMode,
      repoReady: repoSnapshotStatus.ready,
      hasMission: mission.trim().length > 0,
      hasToken: githubToken.trim().length > 0,
      isBusy: isRepoBusy || isPublishing || runtimeBusy,
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
      void buildPackage(mission.trim() || 'README + Update History', packageInputKey);
      return;
    }

    if (automationMode === 'full-auto-draft-pr' && decision.shouldPublishDraftPr) {
      setLastAutoRunKey(automationRunKey);
      setAutomationStatus('Full Auto is building, reviewing and creating a Draft PR.');
      pushTelemetry('workflow', 'info', 'automation:full-auto', 'Full Auto triggered guarded Draft PR flow.');
      void (async () => {
        const pkg = hasFreshPackage && lastPackage
          ? lastPackage
          : await buildPackage(mission.trim() || 'README + Update History', packageInputKey);
        if (pkg) await publishDraftPrForPackage(pkg);
      })();
    }
    // The automation effect intentionally watches value snapshots, not helper function identities.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    automationMode,
    automationRunKey,
    githubToken,
    hasFreshPackage,
    isPublishing,
    isRepoBusy,
    lastAutoRunKey,
    lastPackage,
    mission,
    packageInputKey,
    repoSnapshotStatus.ready,
    runtimeBusy,
    user,
  ]);

  const changeAutomationMode = (mode: SovereignAutomationMode) => {
    setAutomationMode(mode);
    setLastAutoRunKey('');
    setAutomationStatus(describeAutomationMode(mode));
    pushTelemetry('workflow', mode === 'manual' ? 'info' : 'warning', 'automation:mode-changed', describeAutomationMode(mode));
  };

  const login = () => {
    setUser({
      id: makeId(),
      email: 'demo@local',
      name: 'User',
      imageUrl: '',
    });
  };

  if (!user) {
    return <LoginView onLogin={login} />;
  }

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
              <option key={mode} value={mode}>{AUTOMATION_MODE_LABELS[mode]}</option>
            ))}
          </select>
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          Full Auto still runs repo snapshot checks, categorized scan findings, sequential runtime guard, functional guards, generated-file review, diff preview when loaded, workflow watch and Draft PR publishing rules. It does not auto-merge.
        </p>
      </section>

      {activeTab === 'repo' ? (
        <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
          <h2 className="font-bold">Repository Snapshot</h2>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <input
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="GitHub Repo URL"
            />

            <input
              value={repoBranch}
              onChange={(e) => setRepoBranch(e.target.value)}
              placeholder="Branch leer = Default"
            />

            <input
              value={githubToken}
              onChange={(e) => setGithubToken(e.target.value)}
              placeholder="GitHub PAT für private Repos"
              type="password"
            />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <button onClick={handleLoadRepoTree} disabled={isRepoBusy || runtimeBusy} type="button">
              Load Repo
            </button>
            <button onClick={saveCurrentSession} disabled={!repoSnapshotStatus.ready || runtimeBusy} type="button">
              Save Session
            </button>
            <button onClick={restoreSession} disabled={runtimeBusy} type="button">
              Restore Session
            </button>
            <button onClick={clearSession} disabled={runtimeBusy} type="button">
              Clear View
            </button>
          </div>

          <p className="mt-3 text-xs text-slate-400">{repoStatus}</p>
          <p className="mt-1 text-xs text-slate-400">{repoSnapshotStatus.reason}</p>
          <RepoFileList files={repoFiles} />
        </section>
      ) : null}

      {activeTab === 'readiness' ? <RepoReadinessPanel repoUrl={repoUrl} files={repoFiles} status={repoStatus} /> : null}

      {activeTab === 'integrity' ? <RepoFileIntegrityMatrix files={repoFiles} /> : null}

      {activeTab === 'findings' ? <ScanFindingRegistryPanel registry={scanRegistry} /> : null}

      {activeTab === 'builder' ? (
        <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
          <h2 className="font-bold">Sovereign Action Builder</h2>
          <p className="mt-1 text-xs text-slate-400">{repoSnapshotStatus.reason}</p>
          <textarea
            className="mt-2 min-h-24 w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
            value={mission}
            onChange={(e) => setMission(e.target.value)}
            placeholder="Auftrag, z.B. README + Update History"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <button onClick={generateRepoIdeas} disabled={actionDisabled} type="button">Ideen</button>
            <button onClick={generateErrorWorkflow} disabled={actionDisabled} type="button">Fehler</button>
            <button onClick={publishDraftPr} disabled={isPublishing || actionDisabled} type="button">
              {isPublishing ? 'Draft PR läuft...' : 'Draft PR erstellen'}
            </button>
          </div>
          <pre className="mt-3 whitespace-pre-wrap rounded bg-black/40 p-3 text-xs text-slate-300">{sovereignSummary}</pre>
          {sovereignPreview ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400">Brain preview</summary>
              <pre className="mt-2 max-h-96 overflow-auto rounded bg-black/40 p-3 text-[11px] text-slate-300">{sovereignPreview}</pre>
            </details>
          ) : null}
        </section>
      ) : null}

      {activeTab === 'files' ? <GeneratedFileReviewPanel pkg={lastPackage} /> : null}

      {activeTab === 'diff' ? (
        <GeneratedFileDiffPreviewPanel
          report={diffReport}
          isLoading={isLoadingDiffSources || runtimeBusy}
          onLoadSources={() => { void loadGeneratedFileSources(); }}
        />
      ) : null}

      {activeTab === 'workflow' ? (
        <WorkflowWatchPanel
          report={workflowReport}
          isWatching={isWatchingWorkflow || runtimeBusy}
          onWatch={() => { void watchLatestWorkflow(); }}
        />
      ) : null}

      {activeTab === 'repair' ? <WorkflowRepairPanel plan={repairPlan} onUseMission={useRepairMission} /> : null}

      {activeTab === 'health' ? <SovereignHealthPanel report={healthReport} /> : null}

      {activeTab === 'runtime' ? <SequentialRuntimePanel state={sequentialRuntime} /> : null}

      {activeTab === 'coverage' ? <RuntimeValidationCoveragePanel report={coverageReport} /> : null}

      {activeTab === 'remote' ? (
        <RemoteMemoryPanel
          config={remoteMemoryConfig}
          syncResult={remoteMemorySync}
          healthResult={remoteMemoryHealth}
          searchResult={remoteMemorySearch}
          updatesResult={remoteMemoryUpdates}
          isBusy={isRemoteMemoryBusy}
          onChange={setRemoteMemoryConfig}
          onHealth={handleRemoteMemoryHealth}
          onSync={handleRemoteMemorySync}
          onSearch={handleRemoteMemorySearch}
          onPullUpdates={handleRemoteMemoryPullUpdates}
        />
      ) : null}

      {activeTab === 'telemetry' ? (
        <SovereignTelemetryPanel
          state={telemetry}
          expanded={telemetryExpanded}
          onToggle={() => setTelemetryExpanded((value) => !value)}
        />
      ) : null}
    </div>
  );
};

export default App;
