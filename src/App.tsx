import './runtime-adapter';
import React, { useState } from 'react';
import { useGithubRepo } from './features/github/hooks/useGithubRepo';
import { RepoFileList } from './features/github/components/RepoFileList';
import { RepoReadinessPanel } from './features/product/components/RepoReadinessPanel';
import {
  buildSovereignPackageFromRepoFiles,
  summarizeSovereignPackage,
} from './features/product/runtime/sovereignPackageFromRepoFiles';
import { UserSession } from './shared/types/user';
import { makeId } from './shared/utils/crypto';
import { LoginView } from './components/LoginView';

const App: React.FC = () => {
  const [user, setUser] = useState<UserSession | null>(null);
  const [mission, setMission] = useState('README + Update History');
  const [sovereignSummary, setSovereignSummary] = useState('Noch kein Sovereign-Paket erzeugt.');
  const [sovereignPreview, setSovereignPreview] = useState('');
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
  } = useGithubRepo();

  const buildPackage = (nextMission: string) => {
    try {
      const pkg = buildSovereignPackageFromRepoFiles({
        mission: nextMission,
        repoFiles,
        selectedFilePath: 'README.md',
        previousPreview: sovereignPreview,
      });

      setMission(nextMission);
      setSovereignSummary(summarizeSovereignPackage(pkg));
      setSovereignPreview(JSON.stringify({
        architecture: pkg.architecture,
        brain: pkg.brain,
        files: pkg.files.map((file) => ({ path: file.path, reason: file.reason })),
        suggestions: pkg.suggestions,
      }, null, 2));
    } catch (error) {
      setSovereignSummary(error instanceof Error ? error.message : 'Sovereign-Paket konnte nicht erzeugt werden.');
    }
  };

  const generateRepoIdeas = () => {
    buildPackage(mission.trim() || 'README + Update History');
  };

  const generateErrorWorkflow = () => {
    buildPackage('Workflow Fehleranalyse + Runtime Check + Test Plan');
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

      <div className="mt-4 grid gap-2 md:grid-cols-3">
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

      <button onClick={loadRepoTree} disabled={isRepoBusy}>
        Load Repo
      </button>

      <p>{repoStatus}</p>

      <RepoReadinessPanel repoUrl={repoUrl} files={repoFiles} status={repoStatus} />

      <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
        <h2 className="font-bold">Sovereign Action Builder</h2>
        <textarea
          className="mt-2 min-h-24 w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
          value={mission}
          onChange={(e) => setMission(e.target.value)}
          placeholder="Auftrag, z.B. README + Update History"
        />
        <div className="mt-2 flex flex-wrap gap-2">
          <button onClick={generateRepoIdeas}>Ideen</button>
          <button onClick={generateErrorWorkflow}>Fehler</button>
        </div>
        <pre className="mt-3 whitespace-pre-wrap rounded bg-black/40 p-3 text-xs text-slate-300">{sovereignSummary}</pre>
        {sovereignPreview ? (
          <details className="mt-3">
            <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400">Brain preview</summary>
            <pre className="mt-2 max-h-96 overflow-auto rounded bg-black/40 p-3 text-[11px] text-slate-300">{sovereignPreview}</pre>
          </details>
        ) : null}
      </section>

      <RepoFileList files={repoFiles} />
    </div>
  );
};

export default App;
