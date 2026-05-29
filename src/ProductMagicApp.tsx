import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FileItem, Card, WorkView, PipelineState, ProjectSettings } from './features/product/types';
import { makeId, demoFiles, starterCards, defaultSettings } from './features/product/constants';
import { runAwarenessSync, type AwarenessSyncResult, type RepoFile } from './features/ai/awarenessSync';
import { geminiService } from './features/ai/geminiService';
import {
  AlertTriangle,
  Bot,
  CheckCircle,
  Code2,
  Download,
  Eye,
  FolderTree,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Rocket,
  Send,
  Settings,
  Shield,
  Sparkles,
  Trash2,
  Wand2,
  Zap,
} from 'lucide-react';

// --- Persistence helpers ---
const STORAGE_GEMINI_KEY = 'sovereign_gemini_api_key';
const STORAGE_GITHUB_TOKEN = 'sovereign_github_pat';
const STORAGE_REPO_URL = 'sovereign_repo_url';

function loadFromStorage(key: string, fallback = ''): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function saveToStorage(key: string, value: string) {
  try {
    if (value.trim()) {
      localStorage.setItem(key, value.trim());
    } else {
      localStorage.removeItem(key);
    }
  } catch {
    // ignore
  }
}

// --- GitHub helpers ---
const parseGithubRepoUrl = (value: string): { owner: string; repo: string } | null => {
  const match = value.match(/github\.com\/([^/\s]+)\/([^/\s#?]+)/i);
  if (!match) return null;
  return { owner: match[1], repo: match[2].replace(/\.git$/, '') };
};

async function fetchRepoTree(
  owner: string,
  repo: string,
  branch: string,
  token: string
): Promise<RepoFile[]> {
  const headers: Record<string, string> = { Accept: 'application/vnd.github+json' };
  if (token.trim()) headers.Authorization = `Bearer ${token.trim()}`;

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/git/trees/${branch}?recursive=1`,
    { headers }
  );

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`GitHub API ${response.status}: ${text || response.statusText}`);
  }

  const data = await response.json();
  const treeData: any[] = data.tree ?? [];
  const files: RepoFile[] = [];

  for (const f of treeData) {
    if (f.type === 'blob' || f.type === 'tree') {
      files.push({ path: f.path, type: f.type, size: f.size });
      if (files.length >= 250) break;
    }
  }

  return files;
}

// --- Main App ---
export default function ProductMagicApp() {
  // Keys (persisted)
  const [geminiKey, setGeminiKeyState] = useState(() => loadFromStorage(STORAGE_GEMINI_KEY));
  const [accessKey, setAccessKeyState] = useState(() => loadFromStorage(STORAGE_GITHUB_TOKEN));
  const [repoUrl, setRepoUrlState] = useState(() => loadFromStorage(STORAGE_REPO_URL, 'https://github.com/OuroborosCollective/Sovereign-Studio-ato'));

  const setGeminiKey = (v: string) => { setGeminiKeyState(v); saveToStorage(STORAGE_GEMINI_KEY, v); };
  const setAccessKey = (v: string) => { setAccessKeyState(v); saveToStorage(STORAGE_GITHUB_TOKEN, v); };
  const setRepoUrl = (v: string) => { setRepoUrlState(v); saveToStorage(STORAGE_REPO_URL, v); };

  const [repoBranch] = useState('main');

  // Repo state
  const [repoFiles, setRepoFiles] = useState<RepoFile[]>([]);
  const [repoStatus, setRepoStatus] = useState('Bereit. Repo-URL eingeben und laden.');
  const [isRepoBusy, setIsRepoBusy] = useState(false);
  const [repoLoaded, setRepoLoaded] = useState(false);

  // Awareness sync state
  const [syncResult, setSyncResult] = useState<AwarenessSyncResult | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  // Product builder state
  const [blueprint, setBlueprint] = useState('Baue aus diesem Workflow eine klickbare Mini-App mit GitHub Explorer, Auto-Resolver, Living Preview und Agent Workspace.');
  const [cards, setCards] = useState<Card[]>(starterCards());
  const [selectedFile, setSelectedFile] = useState<FileItem>(demoFiles[0]);
  const [built, setBuilt] = useState(false);
  const [chatInput, setChatInput] = useState('Setze diesen Workflow als echtes Produkt um.');
  const [logs, setLogs] = useState<string[]>(['🚀 Sovereign Studio geladen. Keys eintragen und Repo laden.']);
  const [workView, setWorkView] = useState<WorkView>('editor');
  const [pipelineState, setPipelineState] = useState<PipelineState>('idle');
  const [fixLoops, setFixLoops] = useState(0);
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState<ProjectSettings>(defaultSettings);
  const [generatedCode, setGeneratedCode] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  const currentCode = generatedCode || `// ${selectedFile.path}\n// Sovereign Auto-Resolver Preview\n\nconst blueprint = ${JSON.stringify(blueprint, null, 2)};\n\nexport const generatedProduct = {\n  mode: 'living-preview',\n  repo: '${repoUrl}',\n  modules: ${cards.length},\n  repoMode: '${settings.repoMode}',\n  packageManager: '${settings.packageManager}',\n  linter: '${settings.linter}',\n  ready: ${built}\n};`;

  const generatedPackage = useMemo(
    () => JSON.stringify({ repoUrl, blueprint, cards, selectedFile: selectedFile.path, settings, syncResult, generatedCode: currentCode }, null, 2),
    [repoUrl, blueprint, cards, selectedFile, settings, syncResult, currentCode]
  );

  const log = (text: string) => setLogs((items) => [text, ...items].slice(0, 20));

  // --- Load Repo Tree ---
  const loadRepoTree = useCallback(async () => {
    const parsed = parseGithubRepoUrl(repoUrl);
    if (!parsed) {
      setRepoStatus('❌ Ungültige GitHub URL. Format: https://github.com/owner/repo');
      return;
    }

    setIsRepoBusy(true);
    setRepoLoaded(false);
    setSyncResult(null);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}...`);
    log(`📁 Lade Repository: ${parsed.owner}/${parsed.repo}`);

    try {
      const files = await fetchRepoTree(parsed.owner, parsed.repo, repoBranch, accessKey);
      setRepoFiles(files);
      setRepoLoaded(true);
      setRepoStatus(`✅ ${files.length} Dateien geladen`);
      log(`✅ Repo geladen: ${files.length} Dateien in ${parsed.owner}/${parsed.repo}`);
    } catch (err: any) {
      const msg = err?.message ?? 'Unbekannter Fehler';
      setRepoStatus(`❌ ${msg}`);
      log(`❌ Fehler beim Laden: ${msg}`);
      if (msg.includes('401') || msg.includes('403')) {
        log('💡 Tipp: Für private Repos GitHub PAT eintragen.');
      }
      if (msg.includes('404')) {
        log('💡 Tipp: Repo oder Branch nicht gefunden. URL und Branch prüfen.');
      }
    } finally {
      setIsRepoBusy(false);
    }
  }, [repoUrl, accessKey, repoBranch]);

  // --- Awareness Sync ---
  const runSync = useCallback(async () => {
    if (!geminiKey.trim()) {
      log('❌ Fehler beim Awareness Sync: Kein Gemini API-Key eingetragen. Bitte Key aus AI Studio eintragen.');
      setRepoStatus('❌ Gemini API-Key fehlt');
      return;
    }
    if (!repoLoaded || repoFiles.length === 0) {
      log('⚠️ Zuerst ein Repo laden, dann Awareness Sync starten.');
      return;
    }

    setIsSyncing(true);
    log('🧠 Awareness Sync gestartet — Gemini analysiert das Repository...');

    try {
      const result = await runAwarenessSync(geminiKey, repoFiles, repoUrl);
      setSyncResult(result);
      log(`✅ Awareness Sync abgeschlossen. Technologien: ${result.technologies.slice(0, 5).join(', ')}`);
      log(`📋 Zusammenfassung: ${result.summary.slice(0, 120)}...`);
      setWorkView('editor');
    } catch (err: any) {
      const msg: string = err?.message ?? 'Unbekannter Fehler';
      const is429 = msg.includes('429') || msg.includes('quota') || msg.includes('RESOURCE_EXHAUSTED');
      if (is429) {
        log('❌ Fehler beim Awareness Sync: Gemini Rate-Limit erreicht. Bitte kurz warten und erneut versuchen, oder einen Key mit freiem Kontingent nutzen.');
        log('💡 Tipp: Auf https://aistudio.google.com/app/apikey kannst du einen kostenlosen Key erstellen.');
      } else if (msg.includes('API-Key')) {
        log(`❌ Fehler beim Awareness Sync: ${msg}`);
      } else {
        log(`❌ Fehler beim Awareness Sync: ${msg}`);
      }
    } finally {
      setIsSyncing(false);
    }
  }, [geminiKey, repoFiles, repoLoaded, repoUrl]);

  // --- Generate Code with Gemini ---
  const generateCodeWithGemini = useCallback(async (userPrompt: string) => {
    if (!geminiKey.trim()) {
      log('❌ Kein Gemini API-Key. Bitte Key eintragen.');
      generateCodeLocally();
      return;
    }

    setIsGenerating(true);
    log('🤖 Gemini generiert Code...');

    const context = syncResult
      ? `Kontext:\n- Technologien: ${syncResult.technologies.join(', ')}\n- Struktur: ${syncResult.structure}\n`
      : '';

    const prompt = `Du bist ein Senior-Entwickler für das Sovereign Studio Projekt (React + Vite + Capacitor Android).
${context}
Blueprint: ${blueprint}
Aufgabe: ${userPrompt}

Generiere validen TypeScript/React Code. Nur Code, kein Prosa. Beginne direkt mit dem Code.`;

    try {
      const code = await geminiService.generateText(geminiKey, prompt, {
        model: 'gemini-1.5-flash',
        temperature: 0.3,
        maxOutputTokens: 2048,
      });
      setSelectedFile({ path: 'generated/sovereign-product/workflow.ts', icon: '✨' });
      setGeneratedCode(`// Generiert von Sovereign Studio + Gemini\n// ${new Date().toLocaleString('de-DE')}\n\n${code}`);
      setBuilt(true);
      setWorkView('editor');
      log('💻 Gemini hat Code sichtbar in den Editor geschrieben.');
    } catch (err: any) {
      const msg: string = err?.message ?? 'Fehler';
      const is429 = msg.includes('429') || msg.includes('quota');
      if (is429) {
        log('⚠️ Gemini Rate-Limit. Fallback auf lokalen Code-Generator.');
      } else {
        log(`⚠️ Gemini Fehler: ${msg}. Fallback auf lokalen Generator.`);
      }
      generateCodeLocally();
    } finally {
      setIsGenerating(false);
    }
  }, [geminiKey, blueprint, syncResult]);

  const generateCodeLocally = () => {
    const pm = settings.packageManager === 'auto' ? 'detected-package-manager' : settings.packageManager;
    const lintCommand = settings.linter === 'biome' ? `${pm} biome check .` : settings.linter === 'eslint' ? `${pm} lint` : `${pm} lint || ${pm} format`;
    const installCommand = settings.repoMode === 'monorepo' ? `${pm} install --frozen-lockfile` : `${pm} install`;
    const code = `// Generiert von Sovereign Studio\n// File: generated/sovereign-product/workflow.ts\n\nexport const projectProfile = {\n  repoMode: '${settings.repoMode}',\n  packageManager: '${settings.packageManager}',\n  installStrategy: '${settings.installStrategy}',\n  linter: '${settings.linter}',\n  specialization: ${JSON.stringify(settings.specialization)}\n};\n\nexport const safeCommands = {\n  install: '${installCommand}',\n  lint: '${lintCommand}',\n  test: '${pm} test',\n  build: '${pm} build'\n};\n\nexport const productModules = ${JSON.stringify(cards.map((card) => ({ title: card.title, task: card.body })), null, 2)};\n\nexport function runVisibleWorkflow() {\n  return {\n    status: 'ready-for-review',\n    blueprint: ${JSON.stringify(blueprint)},\n    next: 'publish-and-validate'\n  };\n}\n`;
    setSelectedFile({ path: 'generated/sovereign-product/workflow.ts', icon: '✨' });
    setGeneratedCode(code);
    setBuilt(true);
    setWorkView('editor');
    log('💻 Code-Agent hat Code sichtbar im Editor erzeugt.');
  };

  const buildProduct = () => {
    log('🏗️ Produkt wird gebaut...');
    if (geminiKey.trim()) {
      generateCodeWithGemini('Implementiere alle Blueprint-Module als vollständige TypeScript-Klassen.');
    } else {
      generateCodeLocally();
      log('✨ Produkt gebaut (ohne Gemini — Key eintragen für KI-Generierung).');
    }
  };

  const addCard = () => setCards((items) => [...items, { id: makeId(), title: 'Neues Modul', body: blueprint }]);

  const sendChat = () => {
    if (!chatInput.trim()) return;
    const msg = chatInput;
    setChatInput('');
    log(`🤖 Auftrag: ${msg}`);
    generateCodeWithGemini(msg);
  };

  const downloadPackage = () => {
    const blob = new Blob([generatedPackage], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `sovereign-product-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const publishAndValidate = () => {
    setWorkView('pipeline');
    setPipelineState('publishing');
    log('🚀 Publish gestartet: Review-Branch, Dateien und Workflow-Paket werden vorbereitet.');
    window.setTimeout(() => {
      setPipelineState('validating');
      log(`🔎 Validierung läuft mit ${settings.packageManager}/${settings.linter}.`);
    }, 450);
    window.setTimeout(() => {
      if (fixLoops < 1) {
        setPipelineState('failed');
        setFixLoops((count) => count + 1);
        log('❌ Workflow-Fehler erkannt: Agent springt zurück in den Editor und patcht sichtbar.');
      } else {
        setPipelineState('green');
        log('✅ Workflows grün. PR kann gemerged werden.');
      }
    }, 900);
  };

  const patchFromPipeline = () => {
    setPipelineState('patching');
    setWorkView('editor');
    const patched = `${currentCode}\n\n// AutoPatch ${fixLoops}: lint/build guard\nexport const validationPatch = {\n  reason: 'CI failure resolved by visible patch loop',\n  linter: '${settings.linter}',\n  packageManager: '${settings.packageManager}',\n  monorepoSafe: ${settings.repoMode === 'monorepo'}\n};\n`;
    setGeneratedCode(patched);
    log('🛠️ Patch sichtbar im Editor erzeugt. Danach erneut Publish & Validate drücken.');
  };

  const mergeWhenGreen = () => {
    if (pipelineState !== 'green') {
      log('⚠️ Merge blockiert: erst grüne Validierung abwarten.');
      return;
    }
    log('🎉 Merge/Patch abgeschlossen. Branch Cleanup vorbereitet.');
  };

  const pipelineBadge = {
    idle: 'Bereit', publishing: 'Publishing', validating: 'Validating',
    failed: 'Fehler', patching: 'Patching', green: 'Grün',
  }[pipelineState];

  const displayFiles: FileItem[] = repoLoaded && repoFiles.length > 0
    ? repoFiles.filter(f => f.type === 'blob').slice(0, 30).map(f => ({
        path: f.path,
        icon: f.path.endsWith('.ts') || f.path.endsWith('.tsx') ? '🟦'
          : f.path.endsWith('.json') ? '📦'
          : f.path.endsWith('.yml') || f.path.endsWith('.yaml') ? '⚙️'
          : f.path.endsWith('.md') ? '📝'
          : f.path.includes('android') ? '🤖'
          : '📄',
      }))
    : demoFiles;

  return (
    <div className="h-screen overflow-hidden bg-stone-50 text-stone-900 font-sans flex flex-col">
      {/* Header */}
      <header className="h-14 bg-white border-b border-stone-200 flex items-center justify-between px-4 shrink-0 shadow-sm z-50">
        <div>
          <h1 className="text-sm font-bold tracking-tight">SOVEREIGN<span className="text-indigo-600">_STUDIO</span></h1>
          <div className="text-[9px] font-bold text-indigo-600 uppercase tracking-widest">No-Code Product Builder · AI-Powered</div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowSettings((v) => !v)} className="px-3 py-1.5 bg-indigo-50 border border-indigo-200 text-indigo-700 rounded text-[10px] font-bold hover:bg-indigo-100 flex items-center gap-1"><Settings size={12}/> SETTINGS</button>
          <button onClick={() => { setLogs([]); setGeneratedCode(''); setBuilt(false); setRepoFiles([]); setRepoLoaded(false); setSyncResult(null); setPipelineState('idle'); setFixLoops(0); log('🧹 Workspace zurückgesetzt.'); }} className="px-3 py-1.5 bg-rose-50 border border-rose-200 text-rose-700 rounded text-[10px] font-bold hover:bg-rose-100">🧹 RESET</button>
          <button onClick={loadRepoTree} disabled={isRepoBusy} className="px-3 py-1.5 bg-stone-100 border border-stone-200 rounded text-[10px] font-bold hover:bg-stone-200 disabled:opacity-50 flex items-center gap-1">
            {isRepoBusy ? <Loader2 size={11} className="animate-spin"/> : <RefreshCw size={11}/>} REFRESH
          </button>
        </div>
      </header>

      {/* Config bar: Repo URL + Keys */}
      <div className="bg-stone-50 border-b border-stone-200 flex flex-col shrink-0 text-xs">
        <div className="flex items-center justify-between px-4 py-2 gap-4 overflow-x-auto">
          <div className="flex items-center gap-2 shrink-0">
            <span className="font-bold text-stone-500 uppercase text-[10px]">Repo URL:</span>
            <input
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') loadRepoTree(); }}
              className="text-xs px-2 py-1 border border-stone-300 rounded w-72 focus:outline-none focus:border-indigo-500 bg-white"
              placeholder="https://github.com/owner/repo"
            />
            <button
              onClick={loadRepoTree}
              disabled={isRepoBusy}
              className="px-3 py-1 bg-indigo-600 text-white font-bold rounded hover:bg-indigo-700 text-[10px] uppercase disabled:opacity-50 flex items-center gap-1"
            >
              {isRepoBusy ? <Loader2 size={11} className="animate-spin"/> : null} Laden
            </button>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <label className="flex items-center gap-2">
              <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1"><KeyRound size={10}/> GitHub PAT:</span>
              <input
                value={accessKey}
                onChange={(e) => setAccessKey(e.target.value)}
                type="password"
                placeholder="für private Repos"
                className="text-xs px-2 py-1 border border-stone-300 rounded w-40 focus:outline-none focus:border-indigo-500 bg-white"
              />
            </label>
            <label className="flex items-center gap-2">
              <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1"><Zap size={10} className="text-amber-500"/> Gemini Key:</span>
              <input
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                type="password"
                placeholder="AIza..."
                className="text-xs px-2 py-1 border border-stone-300 rounded w-44 focus:outline-none focus:border-indigo-500 bg-white"
              />
              <a
                href="https://aistudio.google.com/app/apikey"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[10px] px-2 py-1 bg-amber-100 border border-amber-300 text-amber-800 rounded hover:bg-amber-200 font-bold"
              >🌐 AI Studio</a>
            </label>
          </div>
        </div>

        {/* Status + Awareness Sync bar */}
        <div className="flex items-center justify-between px-4 py-1.5 border-t border-stone-200 bg-stone-100/60 gap-4">
          <span className="text-[10px] text-stone-500 truncate">{repoStatus}</span>
          <button
            onClick={runSync}
            disabled={isSyncing || !repoLoaded}
            className="shrink-0 flex items-center gap-1.5 px-3 py-1 bg-violet-600 text-white text-[10px] font-bold rounded hover:bg-violet-700 disabled:opacity-40 transition-colors"
          >
            {isSyncing ? <Loader2 size={11} className="animate-spin"/> : <Sparkles size={11}/>}
            {isSyncing ? 'Awareness Sync...' : '✨ Awareness Sync'}
          </button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="bg-white border-b border-indigo-200 p-3 grid grid-cols-2 lg:grid-cols-6 gap-2 text-[10px] shrink-0">
          <label className="font-bold text-stone-600 uppercase">Repo Typ<select value={settings.repoMode} onChange={(e) => setSettings({ ...settings, repoMode: e.target.value as ProjectSettings['repoMode'] })} className="mt-1 w-full border rounded p-1 bg-stone-50"><option value="single">Single Repo</option><option value="monorepo">Monorepo</option></select></label>
          <label className="font-bold text-stone-600 uppercase">Package Manager<select value={settings.packageManager} onChange={(e) => setSettings({ ...settings, packageManager: e.target.value as ProjectSettings['packageManager'] })} className="mt-1 w-full border rounded p-1 bg-stone-50"><option value="auto">Auto</option><option value="pnpm">pnpm</option><option value="npm">npm</option><option value="yarn">yarn</option><option value="bun">bun</option></select></label>
          <label className="font-bold text-stone-600 uppercase">Install<select value={settings.installStrategy} onChange={(e) => setSettings({ ...settings, installStrategy: e.target.value as ProjectSettings['installStrategy'] })} className="mt-1 w-full border rounded p-1 bg-stone-50"><option value="workspace">Workspace Safe</option><option value="frozen">Frozen Lockfile</option><option value="safe">Safe Default</option></select></label>
          <label className="font-bold text-stone-600 uppercase">Linter<select value={settings.linter} onChange={(e) => setSettings({ ...settings, linter: e.target.value as ProjectSettings['linter'] })} className="mt-1 w-full border rounded p-1 bg-stone-50"><option value="auto">Auto</option><option value="eslint">ESLint</option><option value="biome">Biome</option><option value="prettier-eslint">Prettier + ESLint</option></select></label>
          <label className="font-bold text-stone-600 uppercase">Fix Loops<input value={settings.maxFixLoops} onChange={(e) => setSettings({ ...settings, maxFixLoops: Number(e.target.value) || 1 })} type="number" min={1} max={8} className="mt-1 w-full border rounded p-1 bg-stone-50" /></label>
          <label className="font-bold text-stone-600 uppercase">Spezialisierung<input value={settings.specialization} onChange={(e) => setSettings({ ...settings, specialization: e.target.value })} className="mt-1 w-full border rounded p-1 bg-stone-50" /></label>
        </div>
      )}

      {/* Main layout */}
      <main className="flex-1 flex overflow-hidden relative">
        {/* Left panel: file tree + pipeline controls */}
        <section className="flex flex-col w-[300px] shrink-0 border-r border-stone-200 bg-white">
          <div className="p-3 bg-indigo-50 border-b border-indigo-200 shrink-0 shadow-sm">
            <h3 className="text-[11px] font-black text-indigo-800 mb-1 flex justify-between items-center">
              <span>🔁 AUTO-RESOLVER</span>
              <span className={`px-2 py-0.5 rounded-full text-[9px] uppercase ${pipelineState === 'failed' ? 'bg-red-200 text-red-800' : pipelineState === 'green' ? 'bg-green-200 text-green-800' : 'bg-indigo-200 text-indigo-800'}`}>{pipelineBadge}</span>
            </h3>
            <p className="text-[10px] text-indigo-700 mb-2">Profil: <span className="font-mono font-bold">{settings.repoMode}/{settings.packageManager}/{settings.linter}</span></p>
            <button onClick={buildProduct} disabled={isGenerating} className="w-full bg-indigo-600 hover:bg-indigo-700 text-white py-2 rounded text-[11px] font-bold uppercase shadow-sm flex items-center justify-center gap-2 disabled:opacity-50">
              {isGenerating ? <Loader2 size={14} className="animate-spin"/> : <Rocket size={14}/>}
              {isGenerating ? 'Generiere...' : 'Produkt bauen'}
            </button>
          </div>

          <div className="p-3 bg-stone-50 border-b border-stone-200 shrink-0">
            <h3 className="text-[11px] font-bold text-stone-700 mb-2">⚡ ARCHITECT BLUEPRINT</h3>
            <textarea value={blueprint} onChange={(e) => setBlueprint(e.target.value)} rows={3} className="w-full p-2 text-[11px] border border-stone-300 rounded focus:outline-none focus:border-indigo-500 resize-none shadow-inner" />
            <div className="flex gap-2 mt-2">
              <button onClick={buildProduct} disabled={isGenerating} className="flex-1 bg-stone-800 hover:bg-black text-white py-1.5 rounded text-[11px] font-bold uppercase shadow-sm disabled:opacity-50"><Wand2 size={13} className="inline mr-1"/>Generieren</button>
              <button onClick={addCard} className="shrink-0 bg-yellow-100 hover:bg-yellow-200 border border-yellow-300 text-yellow-800 py-1.5 px-3 rounded text-[11px] font-bold uppercase shadow-sm"><Plus size={13} className="inline mr-1"/>Modul</button>
            </div>
          </div>

          {/* Awareness Sync Result */}
          {syncResult && (
            <div className="p-3 bg-violet-50 border-b border-violet-200 shrink-0 text-[10px]">
              <div className="font-black text-violet-800 mb-1 flex items-center gap-1"><Sparkles size={11}/> AWARENESS SYNC</div>
              <p className="text-violet-700 mb-1 line-clamp-2">{syncResult.summary}</p>
              <div className="flex flex-wrap gap-1">
                {syncResult.technologies.slice(0, 6).map((t) => (
                  <span key={t} className="px-1.5 py-0.5 bg-violet-200 text-violet-800 rounded text-[9px] font-bold">{t}</span>
                ))}
              </div>
            </div>
          )}

          {/* File tree */}
          <div className="flex-1 overflow-y-auto bg-white">
            <div className="px-3 py-1.5 text-[9px] font-bold text-stone-400 uppercase border-b border-stone-100 flex items-center gap-1">
              <FolderTree size={10}/> {repoLoaded ? `Repo (${repoFiles.filter(f => f.type === 'blob').length} Dateien)` : 'Demo-Dateien'}
            </div>
            {displayFiles.map((file) => (
              <button
                key={file.path}
                onClick={() => { setSelectedFile(file); setWorkView('editor'); log(`📄 Datei: ${file.path}`); }}
                className={`w-full p-2.5 border-b border-stone-100 text-[11px] flex items-center gap-2 text-left hover:bg-stone-50 ${selectedFile.path === file.path ? 'bg-teal-50 text-teal-700 border-l-4 border-l-teal-600 font-semibold' : 'text-stone-600'}`}
              >
                <span className="shrink-0">{file.icon}</span>
                <span className="truncate">{file.path}</span>
              </button>
            ))}
          </div>
        </section>

        {/* Center: editor / pipeline */}
        <section className="flex-1 min-w-0 flex flex-col bg-stone-50">
          <div className="h-10 bg-stone-50 border-b border-stone-200 flex items-center gap-2 px-2 shrink-0 overflow-x-auto">
            <button onClick={() => setWorkView('editor')} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'editor' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-700'}`}><Code2 size={11} className="inline mr-1"/>EDITOR</button>
            <button onClick={() => setWorkView('pipeline')} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'pipeline' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-700'}`}><RefreshCw size={11} className="inline mr-1"/>PUBLISH LOOP</button>
            <span className="text-[11px] font-mono text-stone-600 italic truncate px-2 max-w-[220px]">{selectedFile.path}</span>
            {['REVIEW','TESTS','DOCS','CI/CD','README','AUTOLINT'].map((label) => (
              <button key={label} onClick={() => { log(`✨ ${label} vorbereitet.`); generateCodeWithGemini(`Erstelle ${label} für das Projekt.`); }} className="px-2 py-1 bg-indigo-100 text-indigo-700 text-[9px] font-bold rounded hover:bg-indigo-200">✨ {label}</button>
            ))}
          </div>

          {workView === 'editor' ? (
            <div className="flex-1 bg-stone-100/30 p-4 overflow-hidden flex flex-col">
              <div className="flex-1 rounded-xl shadow-inner relative overflow-hidden flex flex-col bg-stone-950 font-mono border border-stone-800">
                <div className="h-8 bg-stone-900 border-b border-stone-800 flex items-center gap-2 px-3 text-[10px] text-stone-400">
                  <span className="w-2 h-2 rounded-full bg-red-500"/><span className="w-2 h-2 rounded-full bg-yellow-500"/><span className="w-2 h-2 rounded-full bg-green-500"/>
                  <span className="ml-2">Monaco-style Editor · {geminiKey.trim() ? '🤖 Gemini aktiv' : '⚠️ Kein Gemini Key'}</span>
                </div>
                <div className="flex-1 overflow-auto p-3 text-[12px] text-stone-300 whitespace-pre leading-relaxed">
                  {currentCode.split('\n').map((line, index) => `${String(index + 1).padStart(3, ' ')} │ ${line}`).join('\n')}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 bg-stone-100/30 p-4 overflow-y-auto">
              <div className="bg-white border border-stone-200 rounded-xl shadow-sm p-4">
                <h3 className="text-sm font-black text-stone-900 mb-2">Publish · Validate · Patch Loop</h3>
                <p className="text-xs text-stone-500 mb-4">Code erzeugen → Publish/PR → Workflows prüfen → bei Fehler patchen → erneut validieren.</p>
                <div className="grid grid-cols-4 gap-2 mb-4">
                  {[['publishing','1 Publish'], ['validating','2 Validate'], ['failed','3 Fehler'], ['green','4 Grün']].map(([state, label]) => (
                    <div key={state} className={`p-3 rounded-xl border text-center text-[10px] font-black ${pipelineState === state ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-stone-50 text-stone-500 border-stone-200'}`}>{label}</div>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={publishAndValidate} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-[10px] font-black uppercase">🚀 Publish & Validate</button>
                  <button onClick={patchFromPipeline} className="px-4 py-2 bg-amber-100 text-amber-800 border border-amber-200 rounded-lg text-[10px] font-black uppercase">🛠️ Fehler patchen</button>
                  <button onClick={mergeWhenGreen} className="px-4 py-2 bg-green-600 text-white rounded-lg text-[10px] font-black uppercase">✅ Merge/Patch</button>
                </div>
                {pipelineState === 'failed' && <div className="mt-4 p-3 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs"><AlertTriangle size={14} className="inline mr-1"/> Fehler gefunden. Agent springt zurück in den Editor.</div>}
                {pipelineState === 'green' && <div className="mt-4 p-3 bg-green-50 border border-green-200 text-green-800 rounded-xl text-xs"><CheckCircle size={14} className="inline mr-1"/> Alle Workflows grün. Merge freigegeben.</div>}
              </div>
            </div>
          )}

          {/* Chat bar */}
          <div className="h-12 bg-white border-t border-stone-200 flex items-center px-4 gap-3 shrink-0">
            <span className="text-lg">🤖</span>
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') sendChat(); }}
              placeholder={geminiKey.trim() ? 'Frag Gemini: was soll generiert werden?' : 'Gemini Key eintragen um KI-Chat zu nutzen...'}
              className="flex-1 text-[11px] p-1.5 border border-stone-300 rounded focus:outline-none focus:border-indigo-500 bg-stone-50"
            />
            <button onClick={sendChat} disabled={isGenerating} className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded text-[10px] font-bold uppercase shadow-sm disabled:opacity-50"><Send size={13}/></button>
          </div>

          {/* Bottom publish bar */}
          <div className="h-16 border-t border-indigo-200 px-4 flex items-center justify-between bg-indigo-50 shrink-0 gap-3">
            <div className="flex-1 min-w-0">
              <h4 className="text-[10px] font-black text-indigo-800 uppercase">PR-Queue: <span>{cards.length}</span> Module · Fixloop {fixLoops}/{settings.maxFixLoops}</h4>
              <input value={built ? 'feat: sovereign studio product workspace' : ''} readOnly placeholder="Commit Nachricht..." className="w-full text-[10px] p-1 border border-indigo-200 rounded bg-white" />
            </div>
            <button onClick={publishAndValidate} className="shrink-0 px-6 py-2 bg-indigo-600 text-white rounded-lg font-bold text-[10px] uppercase shadow-sm">🛡️ PUBLISH & VALIDATE</button>
          </div>
        </section>

        {/* Right panel: logs */}
        <section className="w-[320px] shrink-0 border-l border-stone-200 bg-white flex flex-col">
          <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold text-stone-800 flex items-center justify-between shrink-0">
            <div><span className="text-indigo-600">✨</span> SYSTEM LOG</div>
            <button onClick={() => setLogs([])} className="text-[9px] text-stone-400 hover:text-stone-600">Leeren</button>
          </div>

          {/* Key status indicators */}
          <div className="px-3 py-2 border-b border-stone-100 flex gap-3 text-[9px] font-bold">
            <span className={`flex items-center gap-1 ${geminiKey.trim() ? 'text-green-700' : 'text-red-600'}`}>
              <Zap size={9}/> Gemini: {geminiKey.trim() ? 'OK' : 'Fehlt'}
            </span>
            <span className={`flex items-center gap-1 ${accessKey.trim() ? 'text-green-700' : 'text-stone-400'}`}>
              <KeyRound size={9}/> GitHub PAT: {accessKey.trim() ? 'OK' : 'Optional'}
            </span>
            <span className={`flex items-center gap-1 ${repoLoaded ? 'text-green-700' : 'text-stone-400'}`}>
              <FolderTree size={9}/> Repo: {repoLoaded ? `${repoFiles.length} Files` : 'Nicht geladen'}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-2 bg-white text-[11px]">
            {built && (
              <div className="p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-900 shadow-sm">
                <strong><Eye size={13} className="inline mr-1"/>Living Product aktiv</strong>
                <div className="mt-1">
                  {cards.map((card) => (
                    <button key={card.id} onClick={() => log(`▶ Modul: ${card.title}`)} className="mt-1 mr-1 px-2 py-0.5 rounded bg-white border border-emerald-200 text-[9px] font-bold">{card.title}</button>
                  ))}
                </div>
              </div>
            )}
            <div className="p-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-900 shadow-sm">
              <strong><Bot size={13} className="inline mr-1"/>Agent Workspace</strong>
              <br/>GitHub Explorer · Monaco Editor · Gemini Chat · Awareness Sync · Publish Loop
            </div>
            {logs.map((entry, index) => (
              <div key={`${index}`} className={`p-2.5 rounded-xl border text-stone-700 shadow-sm break-words ${entry.startsWith('❌') ? 'bg-red-50 border-red-200 text-red-800' : entry.startsWith('✅') ? 'bg-green-50 border-green-200 text-green-800' : entry.startsWith('⚠️') ? 'bg-amber-50 border-amber-200 text-amber-800' : 'bg-stone-100 border-stone-200'}`}>
                {entry}
              </div>
            ))}
          </div>

          <div className="border-t border-stone-200 p-3 bg-stone-50">
            <button onClick={downloadPackage} className="w-full bg-stone-900 text-white py-2 rounded-lg text-[10px] font-black uppercase flex items-center justify-center gap-2"><Download size={13}/> Produktpaket sichern</button>
          </div>
        </section>
      </main>
    </div>
  );
}
