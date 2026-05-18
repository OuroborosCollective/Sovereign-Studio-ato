import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bug,
  Download,
  FileCode2,
  GitBranch,
  KeyRound,
  Layout,
  LogOut,
  Plus,
  RefreshCw,
  Save,
  Search,
  Shield,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
  Zap,
} from 'lucide-react';

interface UserSession {
  id: string;
  email: string;
  name: string;
  imageUrl: string;
}

interface BoardCard {
  id: string;
  title: string;
  body: string;
  x: number;
  y: number;
  color: 'amber' | 'indigo' | 'emerald' | 'rose' | 'sky';
}

interface BoardState {
  title: string;
  blueprint: string;
  cards: BoardCard[];
  updatedAt: string;
}

interface RepoFile {
  path: string;
  type: 'blob' | 'tree';
  size?: number;
}

interface ParsedRepo {
  owner: string;
  repo: string;
}

const STORAGE_KEY = 'sovereign_canvas_tool_board_v1';
const COLORS: BoardCard['color'][] = ['amber', 'indigo', 'emerald', 'rose', 'sky'];

const makeId = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const defaultBoard = (): BoardState => ({
  title: 'GitHub Auto-Fix Demo Workflow',
  blueprint: 'Demo Workflow Canvas',
  cards: [],
  updatedAt: new Date().toISOString(),
});

const sampleRepoFiles: RepoFile[] = [
  { path: '.github/workflows/ci.yml', type: 'blob' },
  { path: 'package.json', type: 'blob' },
  { path: 'src/App.tsx', type: 'blob' },
];

const parseGithubRepoUrl = (value: string): ParsedRepo | null => {
  const match = value.match(/github\.com\/([^/]+)\/([^/]+)/i);
  if (!match) return null;
  return { owner: match[1], repo: match[2].replace('.git', '') };
};

const App: React.FC = () => {
  const [user, setUser] = useState<UserSession | null>(null);
  const [board, setBoard] = useState<BoardState>(() => defaultBoard());
  const [repoUrl, setRepoUrl] = useState('');
  const [repoBranch, setRepoBranch] = useState('main');
  const [githubToken, setGithubToken] = useState('');
  const [repoFiles, setRepoFiles] = useState<RepoFile[]>(sampleRepoFiles);
  const [repoStatus, setRepoStatus] = useState('');
  const [isRepoBusy, setIsRepoBusy] = useState(false);

  const addLog = (msg: string) => console.log(msg);

  const updateBoard = (next: BoardState) => {
    setBoard({ ...next, updatedAt: new Date().toISOString() });
  };

  /**
   * FIXED LOAD FUNCTION (Merge Conflict entfernt)
   */
  const loadRepoTree = async () => {
    const parsed = parseGithubRepoUrl(repoUrl);

    if (!parsed) {
      setRepoStatus('Ungültige GitHub URL');
      return;
    }

    setIsRepoBusy(true);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}...`);

    try {
      const headers: Record<string, string> = {
        Accept: 'application/vnd.github+json',
      };

      if (githubToken.trim()) {
        headers.Authorization = `Bearer ${githubToken.trim()}`;
      }

      const response = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${repoBranch}?recursive=1`,
        { headers }
      );

      if (!response.ok) {
        throw new Error(`GitHub API Fehler: ${response.status}`);
      }

      const data = await response.json();

      const files: RepoFile[] = (data.tree ?? [])
        .filter((f: any) => f.type === 'blob' || f.type === 'tree')
        .map((f: any) => ({
          path: f.path,
          type: f.type,
          size: f.size,
        }))
        .slice(0, 250);

      setRepoFiles(files);
      setRepoStatus(`${files.length} Dateien geladen`);
      addLog(`Repo geladen: ${parsed.owner}/${parsed.repo}`);
    } catch (err) {
      console.error(err);
      setRepoStatus('Fehler beim Laden des Repos');
    } finally {
      setIsRepoBusy(false);
    }
  };

  const generateRepoIdeas = () => {
    addLog('Ideen generiert');
  };

  const generateErrorWorkflow = () => {
    addLog('Error Workflow erstellt');
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
    return (
      <div className="p-6">
        <button onClick={login}>Login</button>
      </div>
    );
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

      <div>
        {repoFiles.map((f) => (
          <div key={f.path}>{f.path}</div>
        ))}
      </div>

      <button onClick={generateRepoIdeas}>Ideen</button>
      <button onClick={generateErrorWorkflow}>Fehler</button>
    </div>
  );
};

export default App;
