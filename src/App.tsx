import './runtime-adapter';
import React, { useState } from 'react';
import { BoardState } from './features/canvas/types';
import { defaultBoard } from './features/canvas/utils';
import { useGithubRepo } from './features/github/hooks/useGithubRepo';
import { RepoFileList } from './features/github/components/RepoFileList';
import { RepoReadinessPanel } from './features/product/components/RepoReadinessPanel';
import { UserSession } from './shared/types/user';
import { makeId } from './shared/utils/crypto';
import { LoginView } from './components/LoginView';

const App: React.FC = () => {
  const [user, setUser] = useState<UserSession | null>(null);
  const [board, setBoard] = useState<BoardState>(() => defaultBoard());
  const {
    repoUrl,
    setRepoUrl,
    repoStatus,
    isRepoBusy,
    repoFiles,
    loadRepoTree,
  } = useGithubRepo();

  const updateBoard = (next: BoardState) => {
    setBoard({ ...next, updatedAt: new Date().toISOString() });
  };

  const generateRepoIdeas = () => {
    console.log('Ideen generiert');
  };

  const generateErrorWorkflow = () => {
    console.log('Error Workflow erstellt');
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

      <input
        value={repoUrl}
        onChange={(e) => setRepoUrl(e.target.value)}
        placeholder="GitHub Repo URL"
      />

      <button onClick={loadRepoTree} disabled={isRepoBusy}>
        Load Repo
      </button>

      <p>{repoStatus}</p>

      <RepoReadinessPanel repoUrl={repoUrl} files={repoFiles} status={repoStatus} />

      <RepoFileList files={repoFiles} />

      <button onClick={generateRepoIdeas}>Ideen</button>
      <button onClick={generateErrorWorkflow}>Fehler</button>
    </div>
  );
};

export default App;
