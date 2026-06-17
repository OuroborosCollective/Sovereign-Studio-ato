import './runtime-adapter';
import React, { useEffect, useState } from 'react';
import { publishPackageAsDraftPr } from './features/github/githubPackagePublisher';
import { useGithubRepo } from './features/github/hooks/useGithubRepo';
import { RepoFileList } from './features/github/components/RepoFileList';
import { GeneratedFileReviewPanel } from './features/product/components/GeneratedFileReviewPanel';
import { RepoFileIntegrityMatrix } from './features/product/components/RepoFileIntegrityMatrix';
import { RepoReadinessPanel } from './features/product/components/RepoReadinessPanel';
import { RuntimeValidationCoveragePanel } from './features/product/components/RuntimeValidationCoveragePanel';
import { SovereignHealthPanel } from './features/product/components/SovereignHealthPanel';
import { SovereignTelemetryPanel } from './features/product/components/SovereignTelemetryPanel';
import { WorkflowWatchPanel } from './features/product/components/WorkflowWatchPanel';
import {
  AUTOMATION_MODE_LABELS,
  buildAutomationRunKey,
  decideSovereignAutomation,
  describeAutomationMode,
  type SovereignAutomationMode,
} from './features/product/runtime/sovereignAutomationMode';
import { assertGeneratedFileReviewSafe, reviewGeneratedFiles } from './features/product/runtime/generatedFileReview';
import { getRepoSnapshotStatus } from './features/product/runtime/sovereignFunctionalGuards';
import { buildRuntimeValidationCoverageReport } from './features/product/runtime/runtimeValidationCoverage';
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
import { fetchWorkflowWatchReport, type WorkflowWatchReport } from './features/product/runtime/workflowWatch';
import type { SovereignImplementationPackage } from './features/product/runtime/sovereignRuntime';
import { UserSession } from './shared/types/user';
import { makeId } from './shared/utils/crypto';
import { LoginView } from './components/LoginView';

type SovereignTab = 'repo' | 'readiness' | 'integrity' | 'builder' | 'files' | 'workflow' | 'health' | 'coverage' | 'telemetry';

const tabs: Array<{ id: SovereignTab; label: string }> = [
  { id: 'repo', label: 'Repo' },
  { id: 'readiness', label: 'Readiness' },
  { id: 'integrity', label: 'Integrity' },
  { id: 'builder', label: 'Builder' },
  { id: 'files', label: 'Files' },
  { id: 'workflow', label: 'Workflow' },
  { id: 'health', label: 'Health' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'telemetry', label: 'Telemetry' },
];

const automationModes: SovereignAutomationMode[] = ['manual', 'auto-review', 'full-auto-draft-pr'];

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
  const [isWatchingWorkflow, setIsWatchingWorkflow] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [activeTab, setActiveTab] = useState<SovereignTab>('repo');
  const [telemetryExpanded, setTelemetryExpanded] = useState(false);
  const [telemetry, setTelemetry] = useState(() => createInitialTelemetryState());
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
  const actionDisabled = isRepoBusy || !repoSnapshotStatus.ready;
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

  const watchLatestWorkflow = async (commitSha = lastDraftCommitSha, branch = lastDraftBranch) => {
    setIsWatchingWorkflow(true);
    pushTelemetry('workflow', 'info', 'workflow:watch-start', 'Watching GitHub commit checks.', { commitSha: commitSha || 'none' });
    try {
      const report = await fetchWorkflowWatchReport({
        repoUrl,
        token: githubToken,
        commitSha,
        branch,
      });
      setWorkflowReport(report);
      pushTelemetry(
        'workflow',
        report.status === 'red' ? 'error' : report.status === 'green' ? 'success' : 'warning',
        'workflow:watch-finished',
        report.summary,
      );
      setActiveTab('workflow');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Workflow watch failed.';
      pushTelemetry('workflow', 'error', 'workflow:watch-failed', message);
    } finally {
      setIsWatchingWorkflow(false);
    }
  };

  const buildPackage = (nextMission: string, nextPackageKey = packageInputKey): SovereignImplementationPackage | null => {
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
      const message = error instanceof Error ? error.message : 'Sovereign-Paket konnte nicht erzeugt werden.';
      setSovereignSummary(message);
      pushTelemetry('guards', 'error', 'guards:failed', message);
      return null;
    }
  };

  const handleLoadRepoTree = async () => {
    pushTelemetry('repo', 'info', 'repo:load-start', 'Loading repository tree.', { repoUrl });
    await loadRepoTree();
    pushTelemetry('repo', 'success', 'repo:load-finished', 'Repository load request finished. Check repo status for exact result.');
    setLastPackage(null);
    setLastPackageKey('');
    setLastDraftCommitSha('');
    setLastDraftBranch('');
    setWorkflowReport(null);
    setActiveTab('readiness');
  };

  const generateRepoIdeas = () => {
    buildPackage(mission.trim() || 'README + Update History');
  };

  const generateErrorWorkflow = () => {
    buildPackage('Workflow Fehleranalyse + Runtime Check + Test Plan');
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
    const review = reviewGeneratedFiles(pkg.files);
    try {
      assertGeneratedFileReviewSafe(review);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Generated file review blocked Draft PR.';
      setSovereignSummary(message);
      pushTelemetry('github', 'error', 'github:review-blocked', message);
      setActiveTab('files');
      return false;
    }

    if (!githubToken.trim()) {
      setSovereignSummary('GitHub PAT fehlt. Draft PR wird nur mit bewusst eingegebenem Token erstellt.');
      pushTelemetry('github', 'warning', 'github:token-missing', 'Draft PR blocked because no PAT was entered.');
      return false;
    }

    setIsPublishing(true);
    setSovereignSummary('Erstelle GitHub Branch, Commit und Draft PR...');
    pushTelemetry('github', 'info', 'github:draft-pr-start', 'Creating GitHub branch, commit and draft PR.', { files: pkg.files.length });
    try {
      const result = await publishPackageAsDraftPr({
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
          '',
          'Suggestions:',
          ...pkg.suggestions.map((item) => `- ${item}`),
        ].join('\n'),
        files: pkg.files,
      });

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
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Draft PR konnte nicht erstellt werden.';
      setSovereignSummary(message);
      pushTelemetry('github', 'error', 'github:draft-pr-failed', message);
      return false;
    } finally {
      setIsPublishing(false);
    }
  };

  const publishDraftPr = async () => {
    const pkg = hasFreshPackage && lastPackage
      ? lastPackage
      : buildPackage(mission.trim() || 'README + Update History', packageInputKey);
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
      isBusy: isRepoBusy || isPublishing,
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
      buildPackage(mission.trim() || 'README + Update History', packageInputKey);
      return;
    }

    if (automationMode === 'full-auto-draft-pr' && decision.shouldPublishDraftPr) {
      setLastAutoRunKey(automationRunKey);
      setAutomationStatus('Full Auto is building, reviewing and creating a Draft PR.');
      pushTelemetry('workflow', 'info', 'automation:full-auto', 'Full Auto triggered guarded Draft PR flow.');
      const pkg = hasFreshPackage && lastPackage
        ? lastPackage
        : buildPackage(mission.trim() || 'README + Update History', packageInputKey);
      if (pkg) void publishDraftPrForPackage(pkg);
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
          Full Auto still runs repo snapshot checks, functional guards, generated-file review, workflow watch and Draft PR publishing rules. It does not auto-merge.
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
            <button onClick={handleLoadRepoTree} disabled={isRepoBusy} type="button">
              Load Repo
            </button>
            <button onClick={saveCurrentSession} disabled={!repoSnapshotStatus.ready} type="button">
              Save Session
            </button>
            <button onClick={restoreSession} type="button">
              Restore Session
            </button>
            <button onClick={clearSession} type="button">
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

      {activeTab === 'workflow' ? (
        <WorkflowWatchPanel
          report={workflowReport}
          isWatching={isWatchingWorkflow}
          onWatch={() => { void watchLatestWorkflow(); }}
        />
      ) : null}

      {activeTab === 'health' ? <SovereignHealthPanel report={healthReport} /> : null}

      {activeTab === 'coverage' ? <RuntimeValidationCoveragePanel report={coverageReport} /> : null}

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
