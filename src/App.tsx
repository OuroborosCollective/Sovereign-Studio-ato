import './runtime-adapter';
import React, { useState } from 'react';
import { publishPackageAsDraftPr } from './features/github/githubPackagePublisher';
import { useGithubRepo } from './features/github/hooks/useGithubRepo';
import { RepoFileList } from './features/github/components/RepoFileList';
import { RepoFileIntegrityMatrix } from './features/product/components/RepoFileIntegrityMatrix';
import { RepoReadinessPanel } from './features/product/components/RepoReadinessPanel';
import { SovereignTelemetryPanel } from './features/product/components/SovereignTelemetryPanel';
import { getRepoSnapshotStatus } from './features/product/runtime/sovereignFunctionalGuards';
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
import type { SovereignImplementationPackage } from './features/product/runtime/sovereignRuntime';
import { UserSession } from './shared/types/user';
import { makeId } from './shared/utils/crypto';
import { LoginView } from './components/LoginView';

type SovereignTab = 'repo' | 'readiness' | 'integrity' | 'builder' | 'telemetry';

const tabs: Array<{ id: SovereignTab; label: string }> = [
  { id: 'repo', label: 'Repo' },
  { id: 'readiness', label: 'Readiness' },
  { id: 'integrity', label: 'Integrity' },
  { id: 'builder', label: 'Builder' },
  { id: 'telemetry', label: 'Telemetry' },
];

const App: React.FC = () => {
  const [user, setUser] = useState<UserSession | null>(null);
  const [mission, setMission] = useState('README + Update History');
  const [sovereignSummary, setSovereignSummary] = useState('Noch kein Sovereign-Paket erzeugt.');
  const [sovereignPreview, setSovereignPreview] = useState('');
  const [lastPackage, setLastPackage] = useState<SovereignImplementationPackage | null>(null);
  const [isPublishing, setIsPublishing] = useState(false);
  const [activeTab, setActiveTab] = useState<SovereignTab>('repo');
  const [telemetryExpanded, setTelemetryExpanded] = useState(false);
  const [telemetry, setTelemetry] = useState(() => createInitialTelemetryState());
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

  const pushTelemetry = (
    stage: Parameters<typeof createTelemetryEvent>[0],
    level: Parameters<typeof createTelemetryEvent>[1],
    label: string,
    message: string,
    details?: Parameters<typeof createTelemetryEvent>[4],
  ) => {
    setTelemetry((state) => appendTelemetryEvent(state, createTelemetryEvent(stage, level, label, message, details)));
  };

  const buildPackage = (nextMission: string): SovereignImplementationPackage | null => {
    try {
      pushTelemetry('package', 'info', 'package:build-start', 'Building Sovereign package.', { files: repoFiles.length });
      const pkg = buildSovereignPackageFromRepoFiles({
        mission: nextMission,
        repoFiles,
        selectedFilePath: 'README.md',
        previousPreview: sovereignPreview,
      });

      setMission(nextMission);
      setLastPackage(pkg);
      setSovereignSummary(summarizeSovereignPackage(pkg, repoFiles));
      setSovereignPreview(JSON.stringify({
        architecture: pkg.architecture,
        brain: pkg.brain,
        files: pkg.files.map((file) => ({ path: file.path, reason: file.reason })),
        suggestions: pkg.suggestions,
      }, null, 2));
      pushTelemetry('guards', 'success', 'guards:passed', 'Functional guards accepted generated package.', { generatedFiles: pkg.files.length });
      setActiveTab('builder');
      return pkg;
    } catch (error) {
      setLastPackage(null);
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
    pushTelemetry('memory', 'success', 'memory:restored', `Restored session from ${formatSessionMemoryAge(snapshot)}.`, { files: snapshot.repoFiles.length });
    setActiveTab('repo');
  };

  const clearSession = () => {
    clearRepoSnapshot();
    setLastPackage(null);
    setSovereignPreview('');
    setSovereignSummary('Noch kein Sovereign-Paket erzeugt.');
    pushTelemetry('memory', 'info', 'memory:cleared', 'Visible session state cleared. Stored memory is unchanged.');
    setActiveTab('repo');
  };

  const publishDraftPr = async () => {
    const pkg = lastPackage ?? buildPackage(mission.trim() || 'README + Update History');
    if (!pkg) return;
    if (!githubToken.trim()) {
      setSovereignSummary('GitHub PAT fehlt. Draft PR wird nur mit bewusst eingegebenem Token erstellt.');
      pushTelemetry('github', 'warning', 'github:token-missing', 'Draft PR blocked because no PAT was entered.');
      return;
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
          'Suggestions:',
          ...pkg.suggestions.map((item) => `- ${item}`),
        ].join('\n'),
        files: pkg.files,
      });

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
      setActiveTab('telemetry');
      setTelemetryExpanded(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Draft PR konnte nicht erstellt werden.';
      setSovereignSummary(message);
      pushTelemetry('github', 'error', 'github:draft-pr-failed', message);
    } finally {
      setIsPublishing(false);
    }
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
