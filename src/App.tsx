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

const demoWorkflowCards = (): BoardCard[] => [
  {
    id: makeId(),
    title: '1 · Explorer Start',
    body: 'User öffnet die App, trägt GitHub-URL, optional GHP/PAT und Branch ein. Danach lädt der Explorer die Repo-Struktur bis zu den Code-Dateien.',
    x: 36,
    y: 72,
    color: 'indigo',
  },
  {
    id: makeId(),
    title: '2 · Repo Analyse',
    body: 'Button „Ideen“ erzeugt drei Vorschläge aus Dateibaum, Struktur, Framework-Spuren und vorhandenen Workflow-Dateien.',
    x: 292,
    y: 114,
    color: 'sky',
  },
  {
    id: makeId(),
    title: '3 · Fehler finden',
    body: 'User beschreibt Datei, Funktion oder Fehlermeldung. Das Tool erzeugt Suchstrategie, Verdachtsdateien und Fix-Plan als Karten.',
    x: 548,
    y: 72,
    color: 'amber',
  },
  {
    id: makeId(),
    title: '4 · Fix Loop',
    body: 'Demo-Runbook: Patch vorbereiten, GitHub Actions/YML ausführen, fehlgeschlagene Jobs lesen, Fix-Karte erzeugen, erneut prüfen bis grün.',
    x: 190,
    y: 330,
    color: 'rose',
  },
  {
    id: makeId(),
    title: '5 · Grün & Übergabe',
    body: 'Wenn Checks grün sind: PR-Beschreibung, Commit-Message, Release-Hinweise und nächste Schritte als exportierbare Karten speichern.',
    x: 480,
    y: 344,
    color: 'emerald',
  },
];

const defaultBoard = (): BoardState => ({
  title: 'GitHub Auto-Fix Demo Workflow',
  blueprint:
    'Demo: GitHub-Repo laden, Dateibaum anzeigen, drei Ideen erzeugen, Fehlerbeschreibung aufnehmen, Fix-Workflow als Karten planen, CI/YML prüfen und bis zum grünen Build iterieren.',
  updatedAt: new Date().toISOString(),
  cards: demoWorkflowCards(),
});

const sampleRepoFiles: RepoFile[] = [
  { path: '.github/workflows/ci.yml', type: 'blob' },
  { path: '.github/workflows/android-release.yml', type: 'blob' },
  { path: 'package.json', type: 'blob' },
  { path: 'src/App.tsx', type: 'blob' },
  { path: 'src/main.tsx', type: 'blob' },
  { path: 'android/app/build.gradle', type: 'blob' },
  { path: 'capacitor.config.ts', type: 'blob' },
];

const cardStyle = (color: BoardCard['color']) => {
  const styles = {
    amber: 'bg-amber-100 border-amber-300 text-amber-950',
    indigo: 'bg-indigo-100 border-indigo-300 text-indigo-950',
    emerald: 'bg-emerald-100 border-emerald-300 text-emerald-950',
    rose: 'bg-rose-100 border-rose-300 text-rose-950',
    sky: 'bg-sky-100 border-sky-300 text-sky-950',
  };
  return styles[color];
};

const parseGithubRepoUrl = (value: string): ParsedRepo | null => {
  const trimmed = value.trim();
  const match = trimmed.match(/github\.com[/:]([^/\s]+)\/([^/\s#.]+)(?:\.git)?/i);
  if (!match) return null;
  return { owner: match[1], repo: match[2].replace(/\.git$/i, '') };
};

const summarizeExtensions = (files: RepoFile[]) => {
  const counts = files.reduce<Record<string, number>>((acc, file) => {
    const ext = file.path.includes('.') ? file.path.split('.').pop()?.toLowerCase() ?? 'other' : 'other';
    acc[ext] = (acc[ext] ?? 0) + 1;
    return acc;
  }, {});

  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([ext, count]) => `${ext}: ${count}`)
    .join(', ');
};

const App: React.FC = () => {
  const boardRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);

  const [user, setUser] = useState<UserSession | null>(null);
  const [board, setBoard] = useState<BoardState>(() => defaultBoard());
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState('noch nicht');
  const [log, setLog] = useState<string[]>(['GitHub Demo-Workflow bereit.']);
  const [repoUrl, setRepoUrl] = useState('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
  const [repoBranch, setRepoBranch] = useState('main');
  const [githubToken, setGithubToken] = useState('');
  const [repoFiles, setRepoFiles] = useState<RepoFile[]>(sampleRepoFiles);
  const [repoStatus, setRepoStatus] = useState('Demo-Dateibaum geladen. Trage ein echtes Repo ein oder führe den Demo-Workflow aus.');
  const [isRepoBusy, setIsRepoBusy] = useState(false);

  const addLog = useCallback((line: string) => {
    setLog((current) => [`${new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} · ${line}`, ...current].slice(0, 10));
  }, []);

  useEffect(() => {
    const savedUser = localStorage.getItem('user_session');
    const savedBoard = localStorage.getItem(STORAGE_KEY);

    if (savedUser) {
      try {
        setUser(JSON.parse(savedUser) as UserSession);
      } catch {
        localStorage.removeItem('user_session');
      }
    }

    if (savedBoard) {
      try {
        setBoard(JSON.parse(savedBoard) as BoardState);
        setLastSaved('lokal geladen');
      } catch {
        localStorage.removeItem(STORAGE_KEY);
        addLog('Gespeichertes Board war beschädigt und wurde zurückgesetzt.');
      }
    }
  }, [addLog]);

  const login = () => {
    const session: UserSession = {
      id: makeId(),
      email: 'local@sovereign.studio',
      name: 'Sovereign User',
      imageUrl: '',
    };
    setUser(session);
    localStorage.setItem('user_session', JSON.stringify(session));
    addLog('Lokale Sitzung geöffnet.');
  };

  const logout = () => {
    localStorage.removeItem('user_session');
    setUser(null);
    addLog('Lokale Sitzung beendet.');
  };

  const updateBoard = (next: BoardState) => {
    setBoard({ ...next, updatedAt: new Date().toISOString() });
  };

  const appendCards = useCallback((cards: Omit<BoardCard, 'id'>[]) => {
    const created = cards.map((card) => ({ ...card, id: makeId() }));
    updateBoard({ ...board, cards: [...board.cards, ...created] });
    setActiveCardId(created[0]?.id ?? null);
  }, [board]);

  const addCard = useCallback((title = 'Neue Karte', body = board.blueprint) => {
    const index = board.cards.length;
    const nextCard: BoardCard = {
      id: makeId(),
      title,
      body: body.trim() || 'Leere Workflow-Karte.',
      x: 60 + (index % 4) * 74,
      y: 70 + (index % 5) * 52,
      color: COLORS[index % COLORS.length],
    };
    updateBoard({ ...board, cards: [...board.cards, nextCard] });
    setActiveCardId(nextCard.id);
    addLog('Karte erzeugt.');
  }, [addLog, board]);

  const removeCard = (id: string) => {
    updateBoard({ ...board, cards: board.cards.filter((card) => card.id !== id) });
    setActiveCardId(null);
    addLog('Karte gelöscht.');
  };

  const saveLocal = () => {
    const payload = { ...board, updatedAt: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload, null, 2));
    setBoard(payload);
    setLastSaved(new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }));
    addLog('Board lokal gespeichert.');
  };

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(board, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `sovereign-canvas-board-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
    addLog('JSON exportiert.');
  };

  const importJson = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result)) as BoardState;
        if (!Array.isArray(parsed.cards)) throw new Error('Invalid board file');
        updateBoard({ ...parsed, updatedAt: new Date().toISOString() });
        localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed, null, 2));
        addLog(`Board importiert: ${file.name}`);
      } catch {
        addLog('Import fehlgeschlagen. Datei ist kein gültiges Board-JSON.');
      } finally {
        event.target.value = '';
      }
    };
    reader.readAsText(file);
  };

  const resetBoard = () => {
    const fresh = defaultBoard();
    updateBoard(fresh);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(fresh, null, 2));
    setRepoFiles(sampleRepoFiles);
    setRepoStatus('Demo-Dateibaum geladen.');
    setActiveCardId(null);
    addLog('Board auf Demo-Workflow zurückgesetzt.');
  };

  const loadRepoTree = async () => {
    const parsed = parseGithubRepoUrl(repoUrl);
    if (!parsed) {
      setRepoStatus('GitHub-URL nicht erkannt. Beispiel: https://github.com/owner/repo');
      addLog('Repo-URL konnte nicht gelesen werden.');
      return;
    }

    setIsRepoBusy(true);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}@${repoBranch || 'main'} ...`);

    try {
      const headers: Record<string, string> = {
        Accept: 'application/vnd.github+json',
      };
      if (githubToken.trim()) headers.Authorization = `Bearer ${githubToken.trim()}`;

      const response = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${repoBranch || 'main'}?recursive=1`,
        { headers }
      );

      if (!response.ok) {
        throw new Error(`GitHub API ${response.status}`);
      }

      const data = await response.json() as { tree?: Array<{ path: string; type: string; size?: number }> };
      const files = (data.tree ?? [])
        .filter((item) => item.type === 'blob' || item.type === 'tree')
        .map((item) => ({ path: item.path, type: item.type as RepoFile['type'], size: item.size }))
        .slice(0, 250);

      setRepoFiles(files);
      setRepoStatus(`${files.length} Einträge geladen. Token wurde nicht lokal gespeichert.`);
      addLog(`Repo-Struktur geladen: ${parsed.owner}/${parsed.repo}.`);
    } catch (error) {
      console.error(error);
      setRepoStatus('Repo konnte nicht geladen werden. Prüfe URL, Branch, Token oder Repo-Rechte.');
      addLog('Repo-Laden fehlgeschlagen. Demo-Dateibaum bleibt verfügbar.');
    } finally {
      setIsRepoBusy(false);
    }
  };

  const generateRepoIdeas = () => {
    const files = repoFiles.length ? repoFiles : sampleRepoFiles;
    const extSummary = summarizeExtensions(files);
    const hasWorkflows = files.some((file) => file.path.startsWith('.github/workflows/'));
    const hasAndroid = files.some((file) => file.path.includes('android/') || file.path.includes('build.gradle'));
    const hasReact = files.some((file) => file.path.endsWith('.tsx') || file.path.endsWith('.jsx'));

    appendCards([
      {
        title: 'Idee 1 · Repo Radar',
        body: `Dateitypen erkennen und Fokus setzen. Aktuelle Spuren: ${extSummary || 'keine Daten'}. Daraus kann das Tool automatisch Analysebereiche priorisieren.`,
        x: 80,
        y: 140,
        color: 'sky',
      },
      {
        title: 'Idee 2 · Build Sentinel',
        body: hasWorkflows
          ? 'Workflow-Dateien gefunden. Demo-Flow: CI/YML lesen, fehlgeschlagene Jobs clustern, Fix-Karten erzeugen, erneut prüfen.'
          : 'Keine Workflow-Dateien im aktuellen Baum erkannt. Demo-Flow kann zuerst CI/YML-Vorschläge generieren.',
        x: 340,
        y: 180,
        color: 'amber',
      },
      {
        title: 'Idee 3 · Release Coach',
        body: `${hasAndroid ? 'Android/Gradle-Spuren gefunden.' : 'Android-Spuren nicht eindeutig.'} ${hasReact ? 'React/TSX-Spuren gefunden.' : 'React-Spuren nicht eindeutig.'} Vorschlag: App-Release-Checkliste, Signaturprüfung und UI-Smoke-Test als Karten ausgeben.`,
        x: 600,
        y: 220,
        color: 'emerald',
      },
    ]);
    addLog('Drei Repo-Ideen als Karten erzeugt.');
  };

  const generateErrorWorkflow = () => {
    const suspectedFiles = repoFiles
      .filter((file) => /app|main|workflow|build|config|service|hook|test/i.test(file.path))
      .slice(0, 7)
      .map((file) => `- ${file.path}`)
      .join('\n');

    appendCards([
      {
        title: 'Fehler finden · Suchauftrag',
        body: `User beschreibt Datei, Funktion oder Fehlermeldung im Blueprint. Tool sucht zuerst in Verdachtsdateien:\n${suspectedFiles || '- src/App.tsx\n- src/main.tsx\n- .github/workflows/ci.yml'}`,
        x: 84,
        y: 110,
        color: 'rose',
      },
      {
        title: 'Fix vorbereiten · Sicherheitsgeländer',
        body: 'Patch nur auf Branch/PR vorbereiten. Keine Secrets loggen. Token nur für GitHub API verwenden. Vor Merge: Diff, Tests und Workflow-Status prüfen.',
        x: 360,
        y: 260,
        color: 'indigo',
      },
      {
        title: 'Auto-Fix Loop · bis grün',
        body: '1. Workflow starten\n2. Fehlgeschlagene Jobs lesen\n3. Fehlerursache clustern\n4. Patch-Karte erzeugen\n5. Tests erneut laufen lassen\n6. Bei grün: PR-Text + Release-Notiz erzeugen',
        x: 590,
        y: 110,
        color: 'amber',
      },
    ]);
    addLog('Fehler-Fix-Demo als Runbook-Karten erzeugt.');
  };

  const runDemoWorkflow = () => {
    const fresh: BoardState = {
      title: 'GitHub Explorer Auto-Fix Demo',
      blueprint:
        'User trägt GitHub-Token und Repo-URL ein, lädt die Filestruktur, erzeugt Ideen, beschreibt Fehler, lässt Fix-Karten und CI/YML-Loop planen und speichert den Workflow als Board.',
      cards: demoWorkflowCards(),
      updatedAt: new Date().toISOString(),
    };
    updateBoard(fresh);
    setRepoFiles(sampleRepoFiles);
    setRepoStatus('Demo ausgeführt: Beispiel-Dateibaum und Workflow-Karten sind aktiv.');
    setLastSaved('Demo aktiv');
    addLog('Vorgefertigter GitHub-Demo-Workflow ausgeführt.');
  };

  const startDrag = (event: React.PointerEvent<HTMLDivElement>, card: BoardCard) => {
    const rect = event.currentTarget.getBoundingClientRect();
    dragRef.current = {
      id: card.id,
      dx: event.clientX - rect.left,
      dy: event.clientY - rect.top,
    };
    setActiveCardId(card.id);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const moveDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const boardElement = boardRef.current;
    if (!drag || !boardElement) return;

    const rect = boardElement.getBoundingClientRect();
    const x = Math.max(8, Math.min(event.clientX - rect.left - drag.dx, rect.width - 230));
    const y = Math.max(8, Math.min(event.clientY - rect.top - drag.dy, rect.height - 130));

    setBoard((current) => ({
      ...current,
      updatedAt: new Date().toISOString(),
      cards: current.cards.map((card) => (card.id === drag.id ? { ...card, x, y } : card)),
    }));
  };

  const stopDrag = () => {
    if (dragRef.current) addLog('Karte verschoben.');
    dragRef.current = null;
  };

  const activeCard = useMemo(
    () => board.cards.find((card) => card.id === activeCardId) ?? null,
    [activeCardId, board.cards]
  );

  const changeActiveCard = (patch: Partial<BoardCard>) => {
    if (!activeCard) return;
    updateBoard({
      ...board,
      cards: board.cards.map((card) => (card.id === activeCard.id ? { ...card, ...patch } : card)),
    });
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center p-6 text-center">
        <div className="max-w-md bg-white border border-stone-200 rounded-[2rem] p-8 shadow-xl">
          <div className="mx-auto mb-6 w-16 h-16 bg-indigo-600 rounded-3xl flex items-center justify-center text-white shadow-lg shadow-indigo-100">
            <Shield size={32} />
          </div>
          <h1 className="text-3xl font-black tracking-tight text-stone-900">Sovereign Canvas Tool</h1>
          <p className="mt-4 text-stone-500 leading-relaxed">
            Local-first Arbeitsfläche für GitHub-Explorer-Demos, Agent-Workflows, Architektur-Skizzen und Auto-Fix-Runbooks.
          </p>
          <button onClick={login} className="mt-8 w-full rounded-2xl bg-indigo-600 px-5 py-4 text-sm font-black uppercase tracking-wider text-white shadow-lg shadow-indigo-100 active:scale-95">
            Demo-Workspace öffnen
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 flex flex-col">
      <header className="h-16 bg-white border-b border-stone-200 px-4 sm:px-6 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 bg-indigo-600 text-white rounded-2xl flex items-center justify-center shrink-0">
            <Shield size={20} />
          </div>
          <div className="min-w-0">
            <h1 className="font-black tracking-tight truncate">Sovereign Canvas Tool</h1>
            <p className="text-[10px] text-indigo-600 font-black uppercase tracking-[0.18em] truncate">GitHub Demo Workflow · local-first</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden sm:inline text-xs text-stone-500">{user.email}</span>
          <button onClick={logout} className="p-2 rounded-xl text-stone-400 hover:text-rose-600 hover:bg-rose-50" aria-label="Logout">
            <LogOut size={20} />
          </button>
        </div>
      </header>

      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[340px_minmax(0,1fr)_320px] min-h-0">
        <aside className="bg-white border-b lg:border-b-0 lg:border-r border-stone-200 p-4 overflow-y-auto custom-scrollbar">
          <div className="flex items-center gap-2 mb-4">
            <Layout size={18} className="text-indigo-600" />
            <h2 className="text-sm font-black uppercase">Demo Workflow</h2>
          </div>

          <button onClick={runDemoWorkflow} className="mb-3 w-full rounded-2xl bg-indigo-600 px-3 py-3 text-[11px] font-black uppercase text-white flex items-center justify-center gap-2 active:scale-95 shadow-lg shadow-indigo-100">
            <Wand2 size={14} /> Vorgefertigten Demo-Flow ausführen
          </button>

          <input
            value={board.title}
            onChange={(event) => updateBoard({ ...board, title: event.target.value })}
            className="w-full mb-3 rounded-2xl border border-stone-200 bg-stone-50 px-3 py-3 text-sm font-bold outline-none focus:border-indigo-500"
          />
          <textarea
            value={board.blueprint}
            onChange={(event) => updateBoard({ ...board, blueprint: event.target.value })}
            rows={6}
            className="w-full rounded-2xl border border-stone-200 bg-stone-50 p-3 text-xs leading-relaxed outline-none resize-none focus:border-indigo-500"
          />

          <div className="mt-4 rounded-2xl border border-stone-200 bg-stone-50 p-3">
            <div className="mb-3 flex items-center gap-2">
              <KeyRound size={15} className="text-indigo-600" />
              <p className="text-[11px] font-black uppercase text-stone-700">GitHub Explorer</p>
            </div>
            <input
              value={githubToken}
              onChange={(event) => setGithubToken(event.target.value)}
              type="password"
              autoComplete="off"
              placeholder="GHP/PAT Token optional"
              className="mb-2 w-full rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs outline-none focus:border-indigo-500"
            />
            <input
              value={repoUrl}
              onChange={(event) => setRepoUrl(event.target.value)}
              placeholder="https://github.com/owner/repo"
              className="mb-2 w-full rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs outline-none focus:border-indigo-500"
            />
            <div className="mb-2 flex gap-2">
              <div className="relative flex-1">
                <GitBranch size={13} className="absolute left-3 top-2.5 text-stone-400" />
                <input
                  value={repoBranch}
                  onChange={(event) => setRepoBranch(event.target.value)}
                  placeholder="main"
                  className="w-full rounded-xl border border-stone-200 bg-white py-2 pl-8 pr-3 text-xs outline-none focus:border-indigo-500"
                />
              </div>
              <button onClick={loadRepoTree} disabled={isRepoBusy} className="rounded-xl bg-stone-900 px-3 py-2 text-[10px] font-black uppercase text-white disabled:opacity-50">
                {isRepoBusy ? 'Lädt' : 'Laden'}
              </button>
            </div>
            <p className="text-[10px] leading-relaxed text-stone-500">{repoStatus}</p>
          </div>

          <div className="grid grid-cols-2 gap-2 mt-3">
            <button onClick={generateRepoIdeas} className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-[10px] font-black uppercase text-sky-800 flex items-center justify-center gap-1">
              <Sparkles size={13} /> Ideen
            </button>
            <button onClick={generateErrorWorkflow} className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-[10px] font-black uppercase text-rose-800 flex items-center justify-center gap-1">
              <Bug size={13} /> Fehler
            </button>
            <button onClick={() => addCard('Agent Blueprint', board.blueprint)} className="col-span-2 rounded-2xl bg-stone-900 px-3 py-3 text-[11px] font-black uppercase text-white flex items-center justify-center gap-2 active:scale-95">
              <Plus size={14} /> Blueprint als Karte
            </button>
            <button onClick={saveLocal} className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-black uppercase text-emerald-800 flex items-center justify-center gap-1">
              <Save size={13} /> Speichern
            </button>
            <button onClick={exportJson} className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] font-black uppercase text-amber-800 flex items-center justify-center gap-1">
              <Download size={13} /> Export
            </button>
            <button onClick={() => fileRef.current?.click()} className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-[10px] font-black uppercase text-stone-700 flex items-center justify-center gap-1">
              <Upload size={13} /> Import
            </button>
            <button onClick={resetBoard} className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-[10px] font-black uppercase text-rose-700 flex items-center justify-center gap-1">
              <RefreshCw size={13} /> Reset
            </button>
          </div>

          <input ref={fileRef} type="file" accept="application/json" className="hidden" onChange={importJson} />

          <div className="mt-5 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-2xl bg-stone-50 border border-stone-200 p-3"><p className="text-[9px] font-black text-stone-400 uppercase">Karten</p><p className="font-black">{board.cards.length}</p></div>
            <div className="rounded-2xl bg-stone-50 border border-stone-200 p-3"><p className="text-[9px] font-black text-stone-400 uppercase">Files</p><p className="font-black">{repoFiles.length}</p></div>
            <div className="rounded-2xl bg-stone-50 border border-stone-200 p-3"><p className="text-[9px] font-black text-stone-400 uppercase">Save</p><p className="text-xs font-bold truncate">{lastSaved}</p></div>
          </div>
        </aside>

        <section className="min-h-[620px] lg:min-h-0 p-3 bg-stone-100/80">
          <div
            ref={boardRef}
            className="relative h-full min-h-[590px] overflow-hidden rounded-[2rem] border border-stone-200 bg-white shadow-inner touch-none"
            style={{ backgroundImage: 'linear-gradient(#e7e5e4 1px, transparent 1px), linear-gradient(90deg, #e7e5e4 1px, transparent 1px)', backgroundSize: '32px 32px' }}
            onPointerMove={moveDrag}
            onPointerUp={stopDrag}
            onPointerCancel={stopDrag}
          >
            <div className="absolute left-5 top-5 rounded-2xl bg-white/90 border border-stone-200 px-4 py-2 shadow-sm">
              <p className="text-xs font-black text-stone-800">{board.title}</p>
              <p className="text-[10px] text-stone-400">Karten ziehen · antippen zum Bearbeiten · Demo ausführbar</p>
            </div>

            {board.cards.map((card) => (
              <div
                key={card.id}
                className={`absolute w-[220px] min-h-[126px] rounded-2xl border p-4 shadow-xl cursor-grab active:cursor-grabbing select-none ${cardStyle(card.color)} ${activeCardId === card.id ? 'ring-4 ring-indigo-400/30' : ''}`}
                style={{ left: card.x, top: card.y }}
                onPointerDown={(event) => startDrag(event, card)}
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-black text-sm leading-tight">{card.title}</h3>
                  <button onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); removeCard(card.id); }} className="text-current/40 hover:text-current">
                    <Trash2 size={14} />
                  </button>
                </div>
                <p className="mt-3 text-xs leading-relaxed whitespace-pre-wrap">{card.body}</p>
              </div>
            ))}
          </div>
        </section>

        <aside className="bg-stone-950 text-white border-t lg:border-t-0 lg:border-l border-stone-200 p-4 overflow-y-auto custom-scrollbar">
          <div className="flex items-center gap-2 mb-4">
            <Zap size={18} className="text-yellow-400" />
            <h2 className="text-sm font-black uppercase text-indigo-300">Inspector</h2>
          </div>

          {activeCard ? (
            <div className="space-y-3">
              <input value={activeCard.title} onChange={(event) => changeActiveCard({ title: event.target.value })} className="w-full rounded-xl bg-stone-900 border border-stone-700 px-3 py-2 text-sm font-bold outline-none focus:border-indigo-400" />
              <textarea value={activeCard.body} onChange={(event) => changeActiveCard({ body: event.target.value })} rows={8} className="w-full rounded-xl bg-stone-900 border border-stone-700 px-3 py-2 text-xs leading-relaxed outline-none resize-none focus:border-indigo-400" />
              <div className="grid grid-cols-5 gap-2">
                {COLORS.map((color) => <button key={color} onClick={() => changeActiveCard({ color })} className={`h-9 rounded-xl border ${cardStyle(color)} ${activeCard.color === color ? 'ring-2 ring-white' : ''}`} aria-label={color} />)}
              </div>
            </div>
          ) : (
            <p className="text-xs text-stone-400 leading-relaxed">Wähle eine Karte aus, um Titel, Text und Farbe zu bearbeiten.</p>
          )}

          <div className="mt-6 border-t border-stone-800 pt-4">
            <div className="mb-2 flex items-center gap-2">
              <FileCode2 size={14} className="text-indigo-300" />
              <p className="text-[10px] font-black uppercase tracking-wider text-stone-500">Repo-Dateien</p>
            </div>
            <div className="max-h-52 overflow-y-auto custom-scrollbar space-y-1 rounded-xl border border-stone-800 bg-stone-900 p-2">
              {repoFiles.slice(0, 60).map((file) => (
                <button
                  key={file.path}
                  onClick={() => addCard(`Datei · ${file.path.split('/').pop()}`, `Pfad: ${file.path}\nTyp: ${file.type}\nDemo-Aufgabe: analysieren, Fehler suchen oder passenden Fix-Plan erzeugen.`)}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[10px] text-stone-300 hover:bg-stone-800"
                >
                  <Search size={11} className="shrink-0 text-stone-500" />
                  <span className="truncate">{file.path}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6 border-t border-stone-800 pt-4">
            <p className="text-[10px] font-black uppercase tracking-wider text-stone-500 mb-2">System Log</p>
            <div className="space-y-2">
              {log.map((line, index) => <div key={`${line}-${index}`} className="rounded-xl bg-stone-900 border border-stone-800 p-3 text-xs text-stone-300">{line}</div>)}
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
};

export default App;
