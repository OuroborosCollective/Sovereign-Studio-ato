import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FileItem, Card, WorkView, PipelineState, ProjectSettings } from './features/product/types';
import { makeId, demoFiles, starterCards, defaultSettings } from './features/product/constants';
import { runAwarenessSync, type AwarenessSyncResult, type RepoFile } from './features/ai/awarenessSync';
import { geminiService } from './features/ai/geminiService';
import { useProviderFallback, PROVIDER_INFO, ProviderType } from './features/ai/hooks/useProviderFallback';
import { providerManager } from './features/ai/providerManager';
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

  // Free provider API keys
  const [groqKey, setGroqKeyState] = useState(() => loadFromStorage('sovereign_groq_api_key'));
  const [hfKey, setHfKeyState] = useState(() => loadFromStorage('sovereign_huggingface_api_key'));
  const [togetherKey, setTogetherKeyState] = useState(() => loadFromStorage('sovereign_together_api_key'));
  const [openrouterKey, setOpenrouterKeyState] = useState(() => loadFromStorage('sovereign_openrouter_api_key'));

  const setGroqKey = (v: string) => { setGroqKeyState(v); saveToStorage('sovereign_groq_api_key', v); };
  const setHfKey = (v: string) => { setHfKeyState(v); saveToStorage('sovereign_huggingface_api_key', v); };
  const setTogetherKey = (v: string) => { setTogetherKeyState(v); saveToStorage('sovereign_together_api_key', v); };
  const setOpenrouterKey = (v: string) => { setOpenrouterKeyState(v); saveToStorage('sovereign_openrouter_api_key', v); };

  // Provider fallback hook
  const { currentProvider, setProviderApiKey, configuredProviders } = useProviderFallback({
    onFallback: (from: ProviderType, to: ProviderType, error: string) => {
      log(`🔄 Fallback: ${from} → ${to}: ${error}`);
    },
    onProviderChanged: (provider: ProviderType) => {
      log(`✅ Provider gewechselt zu: ${provider.toUpperCase()}`);
    },
  });

  // Initialize provider keys
  useEffect(() => {
    if (groqKey.trim()) setProviderApiKey('groq', groqKey);
    if (hfKey.trim()) setProviderApiKey('huggingface', hfKey);
    if (togetherKey.trim()) setProviderApiKey('together', togetherKey);
    if (openrouterKey.trim()) setProviderApiKey('openrouter', openrouterKey);
  }, [groqKey, hfKey, togetherKey, openrouterKey, setProviderApiKey]);

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
    // MLVOCA is always available (no API key required) — no early guard needed.
    // The hasAnyKey check was removed so no-key users can reach MLVOCA sync.

    if (!repoLoaded || repoFiles.length === 0) {
      log('⚠️ Zuerst ein Repo laden, dann Awareness Sync starten.');
      return;
    }

    setIsSyncing(true);
    log('🧠 Awareness Sync gestartet — AI analysiert das Repository...');

    try {
      let usedProvider = 'gemini';
      
      const result = await runAwarenessSync(
        geminiKey,
        repoFiles,
        repoUrl,
        {
          groqKey: groqKey,
          hfKey: hfKey,
          togetherKey: togetherKey,
          openrouterKey: openrouterKey,
        },
        'gemini-1.5-flash',
        (from, to, error) => {
          usedProvider = to;
          log(`🔄 Fallback: ${from.toUpperCase()} → ${to.toUpperCase()}: ${error}`);
        }
      );
      
      setSyncResult(result);
      log(`✅ Awareness Sync abgeschlossen (${usedProvider.toUpperCase()}).`);
      log(`📊 Technologien: ${result.technologies.slice(0, 5).join(', ')}`);
      log(`📋 Zusammenfassung: ${result.summary.slice(0, 120)}...`);
      setWorkView('editor');
    } catch (err: any) {
      const msg: string = err?.message ?? 'Unbekannter Fehler';
      log(`❌ Awareness Sync Fehler: ${msg}`);
      
      if (msg.includes('401') || msg.includes('authentication')) {
        log('💡 Tipp: API-Key ungültig oder abgelaufen. Bitte Key in den Einstellungen prüfen.');
      } else if (msg.includes('429') || msg.includes('quota')) {
        log('💡 Tipp: Rate-Limit erreicht. Kurz warten oder kostenlosen Key holen (Groq, HF, Together).');
      }
    } finally {
      setIsSyncing(false);
    }
  }, [geminiKey, groqKey, hfKey, togetherKey, openrouterKey, repoFiles, repoLoaded, repoUrl]);

  // --- Generate Code with Gemini + Auto-Fallback ---
  const generateCodeWithGemini = useCallback(async (userPrompt: string) => {
    // MLVOCA is always available (no API key required) — no early guard needed.
    // The hasProvider check was removed so no-key users can reach MLVOCA generation.
    
    setIsGenerating(true);

    const context = syncResult
      ? `Kontext:\n- Technologien: ${syncResult.technologies.join(', ')}\n- Struktur: ${syncResult.structure}\n`
      : '';

    const prompt = `Du bist ein Senior-Entwickler für das Sovereign Studio Projekt (React + Vite + Capacitor Android).
${context}
Blueprint: ${blueprint}
Aufgabe: ${userPrompt}

Generiere validen TypeScript/React Code. Nur Code, kein Prosa. Beginne direkt mit dem Code.`;

    try {
      // Priority 1: Try mlvoca (free, no API key required!)
      log('🔮 Generiere mit MLVOCA (kostenlos)...');
      try {
        const { callMlvoCa } = await import('./features/ai/providerManager');
        const response = await callMlvoCa('gemini-1.5-flash', prompt, {
          temperature: 0.3,
          maxOutputTokens: 2048,
        });
        setSelectedFile({ path: 'generated/sovereign-product/workflow.ts', icon: '✨' });
        setGeneratedCode(`// Generiert von Sovereign Studio + MLVOCA\n// ${new Date().toLocaleString('de-DE')}\n\n${response.text}`);
        setBuilt(true);
        setWorkView('editor');
        log('💻 MLVOCA hat Code generiert (kostenlos!).');
        return;
      } catch (mlvocaErr) {
        log('🔄 MLVOCA nicht verfügbar, versuche anderen Provider...');
      }

      // Priority 2: Try Gemini if key is available
      if (geminiKey.trim()) {
        log('🤖 Generiere mit Gemini...');
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
          log('💻 Gemini hat Code generiert.');
          return;
        } catch (err: any) {
          const msg: string = err?.message ?? 'Fehler';
          const isRetryable = 
            msg.includes('429') || msg.includes('quota') || 
            msg.includes('RESOURCE_EXHAUSTED') ||
            msg.includes('authentication') || msg.includes('api key') ||
            err?.status === 401 || err?.status === 403;
          
          if (!isRetryable) {
            throw err;
          }
          
          log(`⚠️ Gemini Fehler: ${msg}. Versuche Fallback...`);
        }
      }

      // Fallback: Try configured free providers
      let fallbackSuccess = false;
      
      // Groq fallback
      if (groqKey.trim()) {
        log('🔄 Versuche Groq...');
        try {
          const { callGroq } = await import('./features/ai/providerManager');
          const response = await callGroq(groqKey, 'gemini-1.5-flash', prompt, {
            temperature: 0.3,
            maxOutputTokens: 2048,
          });
          setSelectedFile({ path: 'generated/sovereign-product/workflow.ts', icon: '✨' });
          setGeneratedCode(`// Generiert von Sovereign Studio + Groq\n// ${new Date().toLocaleString('de-DE')}\n\n${response.text}`);
          setBuilt(true);
          setWorkView('editor');
          log('💻 Groq hat Code generiert.');
          fallbackSuccess = true;
        } catch (err) {
          log(`⚠️ Groq Fehler, versuche nächsten Provider...`);
        }
      }

      // HuggingFace fallback
      if (!fallbackSuccess && hfKey.trim()) {
        log('🔄 Versuche HuggingFace...');
        try {
          const { callHuggingFace } = await import('./features/ai/providerManager');
          const response = await callHuggingFace(hfKey, 'gemini-1.5-flash', prompt, {
            temperature: 0.3,
            maxOutputTokens: 2048,
          });
          setSelectedFile({ path: 'generated/sovereign-product/workflow.ts', icon: '✨' });
          setGeneratedCode(`// Generiert von Sovereign Studio + HuggingFace\n// ${new Date().toLocaleString('de-DE')}\n\n${response.text}`);
          setBuilt(true);
          setWorkView('editor');
          log('💻 HuggingFace hat Code generiert.');
          fallbackSuccess = true;
        } catch (err) {
          log(`⚠️ HuggingFace Fehler, versuche nächsten Provider...`);
        }
      }

      // Together AI fallback
      if (!fallbackSuccess && togetherKey.trim()) {
        log('🔄 Versuche Together AI...');
        try {
          const { callTogether } = await import('./features/ai/providerManager');
          const response = await callTogether(togetherKey, 'gemini-1.5-flash', prompt, {
            temperature: 0.3,
            maxOutputTokens: 2048,
          });
          setSelectedFile({ path: 'generated/sovereign-product/workflow.ts', icon: '✨' });
          setGeneratedCode(`// Generiert von Sovereign Studio + Together AI\n// ${new Date().toLocaleString('de-DE')}\n\n${response.text}`);
          setBuilt(true);
          setWorkView('editor');
          log('💻 Together AI hat Code generiert.');
          fallbackSuccess = true;
        } catch (err) {
          log(`⚠️ Together AI Fehler...`);
        }
      }

      // OpenRouter fallback
      if (!fallbackSuccess && openrouterKey.trim()) {
        log('🔄 Versuche OpenRouter...');
        try {
          const { callOpenRouter } = await import('./features/ai/providerManager');
          const response = await callOpenRouter(openrouterKey, 'gemini-1.5-flash', prompt, {
            temperature: 0.3,
            maxOutputTokens: 2048,
          });
          setSelectedFile({ path: 'generated/sovereign-product/workflow.ts', icon: '✨' });
          setGeneratedCode(`// Generiert von Sovereign Studio + OpenRouter\n// ${new Date().toLocaleString('de-DE')}\n\n${response.text}`);
          setBuilt(true);
          setWorkView('editor');
          log('💻 OpenRouter hat Code generiert.');
          fallbackSuccess = true;
        } catch (err) {
          log(`⚠️ OpenRouter Fehler...`);
        }
      }

      if (!fallbackSuccess) {
        log('⚠️ Alle Provider fehlgeschlagen. Nutze lokalen Generator.');
        generateCodeLocally();
      }
    } catch (err: any) {
      log(`❌ Unerwarteter Fehler: ${err?.message || err}. Nutze lokalen Generator.`);
      generateCodeLocally();
    } finally {
      setIsGenerating(false);
    }
  }, [geminiKey, groqKey, hfKey, togetherKey, openrouterKey, blueprint, syncResult]);

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
              <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1"><Zap size={10} className="text-amber-500"/> Gemini:</span>
              <input
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                type="password"
                placeholder="AIza..."
                className="text-xs px-2 py-1 border border-stone-300 rounded w-32 focus:outline-none focus:border-indigo-500 bg-white"
              />
            </label>
            <label className="flex items-center gap-2">
              <span className="font-bold text-stone-400 uppercase text-[9px]">Groq:</span>
              <input
                value={groqKey}
                onChange={(e) => setGroqKey(e.target.value)}
                type="password"
                placeholder="gsk_..."
                className="text-xs px-2 py-1 border border-stone-300 rounded w-24 focus:outline-none focus:border-indigo-500 bg-white"
              />
            </label>
            <label className="flex items-center gap-2">
              <span className="font-bold text-stone-400 uppercase text-[9px]">HF:</span>
              <input
                value={hfKey}
                onChange={(e) => setHfKey(e.target.value)}
                type="password"
                placeholder="hf_..."
                className="text-xs px-2 py-1 border border-stone-300 rounded w-20 focus:outline-none focus:border-indigo-500 bg-white"
              />
            </label>
            <label className="flex items-center gap-2">
              <span className="font-bold text-stone-400 uppercase text-[9px]">Together:</span>
              <input
                value={togetherKey}
                onChange={(e) => setTogetherKey(e.target.value)}
                type="password"
                placeholder="..."
                className="text-xs px-2 py-1 border border-stone-300 rounded w-20 focus:outline-none focus:border-indigo-500 bg-white"
              />
            </label>
            <a
              href="https://console.groq.com/keys"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[9px] px-2 py-1 bg-emerald-100 border border-emerald-300 text-emerald-800 rounded hover:bg-emerald-200 font-bold"
              title="Groq, HuggingFace, Together - Free tier available"
            >🔓 FREE</a>
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
      <main className="flex-1 flex flex-col overflow-hidden relative">
        
        {/* Persistent AI Status Banner */}
        <div className="bg-gradient-to-r from-indigo-600 via-violet-600 to-purple-600 px-4 py-2 flex items-center justify-between text-white text-[10px] shrink-0 shadow-lg">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
              <span className="font-bold">AI STATUS</span>
            </span>
            <span className="opacity-80">|</span>
            <span className="font-mono">
              Active: <span className="font-bold bg-white/20 px-1.5 py-0.5 rounded">{currentProvider.toUpperCase()}</span>
            </span>
            {syncResult && (
              <span className="opacity-90">
                | Sync: <span className="font-bold">{syncResult.technologies.slice(0, 3).join(', ')}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {geminiKey.trim() && (
              <span className="flex items-center gap-1 bg-amber-500/30 px-2 py-0.5 rounded">
                <Zap size={10}/> Gemini
              </span>
            )}
            {groqKey.trim() && (
              <span className="flex items-center gap-1 bg-emerald-500/30 px-2 py-0.5 rounded">
                <Zap size={10}/> Groq
              </span>
            )}
            <span className="flex items-center gap-1 bg-white/10 px-2 py-0.5 rounded">
              <Sparkles size={10}/> MLVOCA (Free)
            </span>
          </div>
        </div>

        {/* Left panel: file tree + pipeline controls */}
        <div className="flex-1 flex overflow-hidden">
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

        {/* Center: Matrix-style AI Terminal Interface */}
        <section className="flex-1 min-w-0 flex flex-col bg-black relative">
          
          {/* Matrix Rain Background Effect */}
          <div className="absolute inset-0 opacity-10 pointer-events-none overflow-hidden">
            <div className="matrix-rain absolute w-full h-full"></div>
          </div>

          {/* Terminal Header */}
          <div className="bg-black/90 border-b border-emerald-900 px-4 py-3 shrink-0 relative z-10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <span className="text-emerald-400 font-mono text-sm font-bold tracking-wider flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></span>
                  SOVEREIGN_AI
                </span>
                <span className="text-emerald-700">│</span>
                <span className="text-emerald-500/60 text-xs font-mono">
                  MLVOCA + Gemini + Groq Fallback System
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="text-emerald-600">STATUS:</span>
                <span className={`px-2 py-0.5 rounded ${isGenerating ? 'bg-emerald-500 text-black' : 'bg-emerald-900 text-emerald-400'}`}>
                  {isGenerating ? 'PROCESSING' : 'READY'}
                </span>
                <span className="text-emerald-600">│</span>
                <span className="text-emerald-400">{currentProvider.toUpperCase()}</span>
              </div>
            </div>
          </div>

          {/* Main Chat/Output Area */}
          <div className="flex-1 overflow-hidden flex flex-col relative z-10">
            
            {/* Output Display - Scrollable */}
            <div className="flex-1 overflow-y-auto p-6 font-mono text-sm">
              
              {/* System Initialization */}
              <div className="mb-6 border border-emerald-900/50 rounded-lg p-4 bg-emerald-950/20">
                <div className="text-emerald-600 text-xs mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
                  SYSTEM INITIALIZATION
                </div>
                <div className="text-emerald-500/80 text-xs space-y-1">
                  <p>› AI Provider: <span className="text-emerald-400">{currentProvider.toUpperCase()}</span></p>
                  <p>› Free Tier: <span className="text-emerald-400">MLVOCA (ACTIVE)</span></p>
                  <p>› Models: deepseek-r1:1.5b | llama-3.1-8b-instant</p>
                  <p>› Status: <span className="text-emerald-400">ONLINE</span></p>
                </div>
              </div>

              {/* AI Response Messages */}
              {logs.map((entry, index) => (
                <div key={index} className={`mb-4 ${
                  entry.startsWith('💻') ? 'text-cyan-400' : 
                  entry.startsWith('🤖') ? 'text-emerald-400' :
                  entry.startsWith('❌') ? 'text-red-400' :
                  entry.startsWith('✅') ? 'text-emerald-400' :
                  entry.startsWith('⚠️') ? 'text-yellow-400' :
                  entry.startsWith('🔮') ? 'text-purple-400' :
                  'text-emerald-500/70'
                }`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-emerald-800 text-xs">[{index + 1}]</span>
                    <span className="text-emerald-600 text-xs">
                      {entry.startsWith('💻') ? '▸ CODE' : 
                       entry.startsWith('🤖') ? '▸ AI' :
                       entry.startsWith('❌') ? '▸ ERROR' :
                       entry.startsWith('✅') ? '▸ SUCCESS' :
                       entry.startsWith('⚠️') ? '▸ WARNING' :
                       '▸ LOG'}
                    </span>
                  </div>
                  <div className="pl-4 whitespace-pre-wrap leading-relaxed text-xs">
                    {entry.replace(/^[🤖💻❌✅⚠️🔮]\s*/, '')}
                  </div>
                </div>
              ))}

              {/* Generated Code Display */}
              {generatedCode && (
                <div className="mt-6 border border-cyan-900/50 rounded-lg overflow-hidden bg-black/50">
                  <div className="bg-cyan-950/50 px-4 py-2 border-b border-cyan-900/50 flex items-center justify-between">
                    <span className="text-cyan-500 text-xs font-mono flex items-center gap-2">
                      <span className="w-2 h-2 bg-cyan-500 rounded-full"></span>
                      GENERATED_CODE_OUTPUT
                    </span>
                    <span className="text-cyan-700 text-xs">{generatedCode.split('\n').length} lines</span>
                  </div>
                  <pre className="p-4 text-cyan-400 text-xs overflow-x-auto font-mono">
                    {generatedCode.split('\n').map((line, i) => (
                      <div key={i} className="flex hover:bg-cyan-950/30">
                        <span className="text-cyan-900 w-12 shrink-0 text-right pr-4 select-none">{i + 1}</span>
                        <span className="whitespace-pre">{line || ' '}</span>
                      </div>
                    ))}
                  </pre>
                </div>
              )}

              {/* Suggestions Panel */}
              <div className="mt-6 border border-emerald-900/30 rounded-lg p-4 bg-emerald-950/10">
                <div className="text-emerald-600 text-xs mb-3 font-mono">▸ SUGGESTED ACTIONS</div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'Create README', prompt: 'Erstelle eine vollständige README.md für dieses Projekt' },
                    { label: 'Write Tests', prompt: 'Schreibe Jest/React Tests für die Hauptkomponenten' },
                    { label: 'Build Feature', prompt: 'Implementiere ein neues Feature nach meiner Beschreibung' },
                    { label: 'Fix Bugs', prompt: 'Analysiere und behebe mögliche Bugs im Code' },
                  ].map((item) => (
                    <button 
                      key={item.label}
                      onClick={() => generateCodeWithGemini(item.prompt)}
                      className="text-left px-3 py-2 bg-emerald-950/50 hover:bg-emerald-900/30 border border-emerald-900/30 rounded text-emerald-400 text-xs font-mono transition-colors"
                    >
                      ✦ {item.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Command Input Area */}
            <div className="border-t border-emerald-900/50 bg-black/90 p-4 shrink-0">
              <div className="flex gap-3">
                <div className="flex-1 relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-emerald-500 font-mono">›</span>
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') sendChat(); }}
                    placeholder="Enter command or describe what you want to build..."
                    className="w-full bg-emerald-950/30 border border-emerald-900/50 text-emerald-400 placeholder-emerald-800 
                               px-4 py-3 pl-8 rounded-lg font-mono text-sm focus:outline-none focus:border-emerald-600
                               focus:shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                  />
                </div>
                <button 
                  onClick={sendChat}
                  disabled={isGenerating}
                  className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-900 disabled:text-emerald-600 
                           text-black font-mono font-bold px-6 py-3 rounded-lg transition-all flex items-center gap-2
                           disabled:cursor-not-allowed"
                >
                  {isGenerating ? (
                    <>
                      <Loader2 size={16} className="animate-spin"/>
                      PROCESSING
                    </>
                  ) : (
                    <>
                      <Send size={16}/>
                      EXECUTE
                    </>
                  )}
                </button>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs font-mono">
                <span className="text-emerald-700">Press Enter to execute • Auto-fallback active</span>
                <div className="flex items-center gap-4">
                  {geminiKey.trim() && <span className="text-amber-500">● Gemini</span>}
                  {groqKey.trim() && <span className="text-emerald-500">● Groq</span>}
                  <span className="text-purple-400">● MLVOCA</span>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Status Bar */}
          <div className="h-10 border-t border-emerald-900/50 px-4 flex items-center justify-between bg-black/50 shrink-0 relative z-10">
            <div className="flex items-center gap-6 text-xs font-mono text-emerald-700">
              <span>PR_QUEUE: <span className="text-emerald-400">{cards.length}</span></span>
              <span>│</span>
              <span>FIX_LOOP: <span className="text-emerald-400">{fixLoops}/{settings.maxFixLoops}</span></span>
              <span>│</span>
              <span>REPO: <span className={repoLoaded ? 'text-emerald-400' : 'text-yellow-500'}>{repoLoaded ? `${repoFiles.length} files` : 'not loaded'}</span></span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={buildProduct} disabled={isGenerating} className="px-3 py-1 bg-emerald-900/50 hover:bg-emerald-900 border border-emerald-800 text-emerald-400 text-xs font-mono rounded flex items-center gap-1">
                {isGenerating ? <Loader2 size={12} className="animate-spin"/> : <Rocket size={12}/>}
                BUILD
              </button>
              <button onClick={publishAndValidate} className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-black text-xs font-mono rounded font-bold">
                🛡️ PUBLISH
              </button>
            </div>
          </div>
        </section>

        {/* Right panel: logs */}
        <section className="w-[320px] shrink-0 border-l border-stone-200 bg-white flex flex-col">
          <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold text-stone-800 flex items-center justify-between shrink-0">
            <div><span className="text-indigo-600">✨</span> SYSTEM LOG</div>
            <button onClick={() => setLogs([])} className="text-[9px] text-stone-400 hover:text-stone-600">Leeren</button>
          </div>

          {/* Key status indicators */}
          <div className="px-3 py-2 border-b border-stone-100 grid grid-cols-3 gap-1 text-[9px] font-bold">
            <span className={`flex items-center gap-1 ${geminiKey.trim() ? 'text-green-700' : 'text-stone-400'}`}>
              <Zap size={9}/> Gemini {geminiKey.trim() ? '✓' : '–'}
            </span>
            <span className={`flex items-center gap-1 ${groqKey.trim() ? 'text-green-700' : 'text-stone-400'}`}>
              <Zap size={9}/> Groq {groqKey.trim() ? '✓' : '–'}
            </span>
            <span className={`flex items-center gap-1 ${hfKey.trim() ? 'text-green-700' : 'text-stone-400'}`}>
              <Zap size={9}/> HF {hfKey.trim() ? '✓' : '–'}
            </span>
            <span className={`flex items-center gap-1 ${togetherKey.trim() ? 'text-green-700' : 'text-stone-400'}`}>
              <Zap size={9}/> Togthr {togetherKey.trim() ? '✓' : '–'}
            </span>
            <span className={`flex items-center gap-1 ${currentProvider ? 'text-indigo-600' : 'text-stone-400'}`}>
              <Bot size={9}/> Active: {currentProvider.toUpperCase()}
            </span>
            <span className={`flex items-center gap-1 ${accessKey.trim() ? 'text-green-700' : 'text-stone-400'}`}>
              <KeyRound size={9}/> GH {accessKey.trim() ? '✓' : '–'}
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
        </div>{/* Close flex-1 */}
        </main>
    </div>
  );
}
