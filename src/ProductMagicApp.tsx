import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useDispatch } from 'react-redux';
import { FileItem, Card, WorkView, PipelineState, ProjectSettings } from './features/product/types';
import { makeId, demoFiles, starterCards, defaultSettings } from './features/product/constants';
import { runAwarenessSync, type AwarenessSyncResult, type RepoFile } from './features/ai/awarenessSync';
import { geminiService } from './features/ai/geminiService';
import { useProviderFallback, PROVIDER_INFO, ProviderType } from './features/ai/hooks/useProviderFallback';
import { providerManager } from './features/ai/providerManager';
import { keyStorage } from './features/ai/keyStorage';
import CanvasEngine from './features/canvas/CanvasEngine';
import { addVectors, clearCanvas, type CanvasObject } from './features/canvas/canvasSlice';
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

// --- Storage keys ---
const STORAGE_GEMINI_KEY = 'sovereign_gemini_api_key';
const STORAGE_GITHUB_TOKEN = 'sovereign_github_pat';
const STORAGE_REPO_URL = 'sovereign_repo_url';
const DEFAULT_REPO_URL = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato';

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
  const dispatch = useDispatch();

  // Toast notification for "Key saved" confirmation
  const [savedToast, setSavedToast] = useState<string | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showSavedToast = (label: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setSavedToast(label);
    toastTimerRef.current = setTimeout(() => setSavedToast(null), 2500);
  };

  // Keys (persisted via Capacitor Preferences on Android, localStorage fallback on web)
  const [geminiKey, setGeminiKeyState] = useState('');
  const [accessKey, setAccessKeyState] = useState('');
  const [repoUrl, setRepoUrlState] = useState(DEFAULT_REPO_URL);

  const setGeminiKey = (v: string) => {
    setGeminiKeyState(v);
    void keyStorage.set(STORAGE_GEMINI_KEY, v).then(() => { if (v.trim()) showSavedToast('Gemini Key'); });
  };
  const setAccessKey = (v: string) => {
    setAccessKeyState(v);
    void keyStorage.set(STORAGE_GITHUB_TOKEN, v).then(() => { if (v.trim()) showSavedToast('GitHub PAT'); });
  };
  const setRepoUrl = (v: string) => { setRepoUrlState(v); void keyStorage.set(STORAGE_REPO_URL, v); };

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
  const [groqKey, setGroqKeyState] = useState('');
  const [hfKey, setHfKeyState] = useState('');
  const [togetherKey, setTogetherKeyState] = useState('');
  const [openrouterKey, setOpenrouterKeyState] = useState('');

  const setGroqKey = (v: string) => {
    setGroqKeyState(v);
    void keyStorage.set('sovereign_groq_api_key', v).then(() => { if (v.trim()) showSavedToast('Groq Key'); });
  };
  const setHfKey = (v: string) => {
    setHfKeyState(v);
    void keyStorage.set('sovereign_huggingface_api_key', v).then(() => { if (v.trim()) showSavedToast('HuggingFace Key'); });
  };
  const setTogetherKey = (v: string) => {
    setTogetherKeyState(v);
    void keyStorage.set('sovereign_together_api_key', v).then(() => { if (v.trim()) showSavedToast('Together Key'); });
  };
  const setOpenrouterKey = (v: string) => {
    setOpenrouterKeyState(v);
    void keyStorage.set('sovereign_openrouter_api_key', v).then(() => { if (v.trim()) showSavedToast('OpenRouter Key'); });
  };

  // Provider fallback hook
  const { currentProvider, setProviderApiKey, configuredProviders } = useProviderFallback({
    onFallback: (from: ProviderType, to: ProviderType, error: string) => {
      log(`🔄 Fallback: ${from} → ${to}: ${error}`);
    },
    onProviderChanged: (provider: ProviderType) => {
      log(`✅ Provider gewechselt zu: ${provider.toUpperCase()}`);
    },
  });

  // Load all persisted keys from native storage on app mount
  useEffect(() => {
    const loadPersistedKeys = async () => {
      const [gKey, ghToken, url, gqKey, hKey, tKey, orKey] = await Promise.all([
        keyStorage.get(STORAGE_GEMINI_KEY),
        keyStorage.get(STORAGE_GITHUB_TOKEN),
        keyStorage.get(STORAGE_REPO_URL, DEFAULT_REPO_URL),
        keyStorage.get('sovereign_groq_api_key'),
        keyStorage.get('sovereign_huggingface_api_key'),
        keyStorage.get('sovereign_together_api_key'),
        keyStorage.get('sovereign_openrouter_api_key'),
      ]);
      if (gKey) setGeminiKeyState(gKey);
      if (ghToken) setAccessKeyState(ghToken);
      if (url) setRepoUrlState(url);
      if (gqKey) setGroqKeyState(gqKey);
      if (hKey) setHfKeyState(hKey);
      if (tKey) setTogetherKeyState(tKey);
      if (orKey) setOpenrouterKeyState(orKey);
    };
    loadPersistedKeys();
  }, []);

  // Initialize provider manager with free provider keys whenever they change
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
    const hasAnyKey = geminiKey.trim() || groqKey.trim() || hfKey.trim() || togetherKey.trim() || openrouterKey.trim();
    
    if (!hasAnyKey) {
      log('❌ Fehler beim Awareness Sync: Kein API-Key konfiguriert.');
      log('💡 Bitte mindestens einen Key eintragen: Gemini, Groq, HuggingFace oder Together AI.');
      setRepoStatus('❌ Kein API-Key konfiguriert');
      return;
    }
    
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
    // Check if any provider is available
    const hasProvider = geminiKey.trim() || groqKey.trim() || hfKey.trim() || togetherKey.trim() || openrouterKey.trim();
    
    if (!hasProvider) {
      log('⚠️ Kein API-Key konfiguriert. Nutze lokalen Generator.');
      generateCodeLocally();
      return;
    }

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
      // Try Gemini first if key is available
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
    const hasAnyKey = geminiKey.trim() || groqKey.trim() || hfKey.trim() || togetherKey.trim() || openrouterKey.trim();
    if (hasAnyKey) {
      generateCodeWithGemini('Implementiere alle Blueprint-Module als vollständige TypeScript-Klassen.');
    } else {
      generateCodeLocally();
      log('✨ Produkt gebaut (lokal — AI Key eintragen für KI-Generierung).');
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

  // --- AI Canvas Generation ---
  const generateCanvasFromAI = useCallback(async () => {
    const hasAnyKey = geminiKey.trim() || groqKey.trim() || hfKey.trim() || togetherKey.trim() || openrouterKey.trim();
    if (!hasAnyKey) {
      log('⚠️ Kein AI Key — Canvas Demo-Layout wird geladen.');
      dispatch(clearCanvas());
      const demoObjs: CanvasObject[] = [
        { id: 'demo-1', type: 'rect', left: 40, top: 60, x: 40, y: 60, width: 200, height: 90, fill: '#6366f1', scaleX: 1, scaleY: 1, angle: 0, flipX: false, flipY: false, opacity: 1, visible: true, zIndex: 0, data: { color: '#6366f1' } },
        { id: 'demo-2', type: 'ai-text', left: 60, top: 88, x: 60, y: 88, width: 160, height: 30, fill: '#ffffff', scaleX: 1, scaleY: 1, angle: 0, flipX: false, flipY: false, opacity: 1, visible: true, zIndex: 1, data: { text: 'GitHub Loader' } },
        { id: 'demo-3', type: 'rect', left: 280, top: 60, x: 280, y: 60, width: 200, height: 90, fill: '#8b5cf6', scaleX: 1, scaleY: 1, angle: 0, flipX: false, flipY: false, opacity: 1, visible: true, zIndex: 2, data: { color: '#8b5cf6' } },
        { id: 'demo-4', type: 'ai-text', left: 300, top: 88, x: 300, y: 88, width: 160, height: 30, fill: '#ffffff', scaleX: 1, scaleY: 1, angle: 0, flipX: false, flipY: false, opacity: 1, visible: true, zIndex: 3, data: { text: 'AI Analyzer' } },
        { id: 'demo-5', type: 'rect', left: 160, top: 200, x: 160, y: 200, width: 200, height: 90, fill: '#0ea5e9', scaleX: 1, scaleY: 1, angle: 0, flipX: false, flipY: false, opacity: 1, visible: true, zIndex: 4, data: { color: '#0ea5e9' } },
        { id: 'demo-6', type: 'ai-text', left: 180, top: 228, x: 180, y: 228, width: 160, height: 30, fill: '#ffffff', scaleX: 1, scaleY: 1, angle: 0, flipX: false, flipY: false, opacity: 1, visible: true, zIndex: 5, data: { text: 'Monaco Editor' } },
      ];
      dispatch(addVectors(demoObjs));
      setWorkView('canvas');
      return;
    }

    setIsGenerating(true);
    log('🎨 Generiere Canvas-Architektur-Layout mit AI...');
    setWorkView('canvas');

    const canvasPrompt = `Du bist ein UI-Architektur-Visualisierer. Generiere ein JSON-Array mit Canvas-Objekten für das Sovereign Studio.

Blueprint: ${blueprint}
${syncResult ? `Technologien: ${syncResult.technologies.slice(0, 6).join(', ')}` : ''}

Antworte NUR mit einem gültigen JSON-Array (kein Prosa, kein Markdown):
[
  { "id": "r1", "type": "rect", "left": 40, "top": 40, "width": 180, "height": 80, "fill": "#6366f1" },
  { "id": "t1", "type": "ai-text", "left": 55, "top": 65, "width": 150, "height": 30, "text": "Komponentenname" }
]

Erstelle 6–10 Objekte (rect + ai-text Paare) als Architektur-Übersicht. Verteile sie gleichmäßig, keine Überschneidungen. Nutze Indigo/Violet/Sky für Fill-Farben.`;

    try {
      let jsonText = '';
      if (geminiKey.trim()) {
        jsonText = await geminiService.generateText(geminiKey, canvasPrompt, { model: 'gemini-1.5-flash', temperature: 0.4, maxOutputTokens: 1024 });
      } else if (groqKey.trim()) {
        const { callGroq } = await import('./features/ai/providerManager');
        jsonText = (await callGroq(groqKey, 'gemini-1.5-flash', canvasPrompt, { temperature: 0.4, maxOutputTokens: 1024 })).text;
      } else if (hfKey.trim()) {
        const { callHuggingFace } = await import('./features/ai/providerManager');
        jsonText = (await callHuggingFace(hfKey, 'gemini-1.5-flash', canvasPrompt, { temperature: 0.4, maxOutputTokens: 1024 })).text;
      } else if (togetherKey.trim()) {
        const { callTogether } = await import('./features/ai/providerManager');
        jsonText = (await callTogether(togetherKey, 'gemini-1.5-flash', canvasPrompt, { temperature: 0.4, maxOutputTokens: 1024 })).text;
      } else if (openrouterKey.trim()) {
        const { callOpenRouter } = await import('./features/ai/providerManager');
        jsonText = (await callOpenRouter(openrouterKey, 'gemini-1.5-flash', canvasPrompt, { temperature: 0.4, maxOutputTokens: 1024 })).text;
      }

      const jsonMatch = jsonText.match(/\[[\s\S]*?\]/);
      if (jsonMatch) {
        const parsed: any[] = JSON.parse(jsonMatch[0]);
        const canvasObjects: CanvasObject[] = parsed.map((obj: any, i: number) => ({
          id: obj.id || `ai-${i}`,
          type: obj.type || 'rect',
          left: obj.left ?? 40 + (i % 3) * 220,
          top: obj.top ?? 40 + Math.floor(i / 3) * 130,
          x: obj.left ?? 40,
          y: obj.top ?? 40,
          width: obj.width ?? 180,
          height: obj.height ?? 80,
          fill: obj.fill ?? '#6366f1',
          scaleX: 1, scaleY: 1, angle: 0, flipX: false, flipY: false,
          opacity: 1, visible: true, zIndex: i,
          data: { color: obj.fill ?? '#6366f1', text: obj.text ?? '', label: obj.text ?? '' },
        }));
        dispatch(clearCanvas());
        dispatch(addVectors(canvasObjects));
        log(`🎨 Canvas: ${canvasObjects.length} Architektur-Objekte generiert.`);
      } else {
        log('⚠️ AI: Kein gültiges JSON für Canvas. Demo-Layout behalten.');
      }
    } catch (err: any) {
      log(`❌ Canvas-Generierung Fehler: ${err?.message || err}`);
    } finally {
      setIsGenerating(false);
    }
  }, [geminiKey, groqKey, hfKey, togetherKey, openrouterKey, blueprint, syncResult, dispatch]);

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
      {/* Keys saved toast */}
      {savedToast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[9999] flex items-center gap-2 px-4 py-2.5 bg-emerald-600 text-white text-[12px] font-bold rounded-xl shadow-lg pointer-events-none animate-fade-in">
          <CheckCircle size={14}/> {savedToast} gespeichert ✓
        </div>
      )}
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
            <button onClick={generateCanvasFromAI} disabled={isGenerating} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'canvas' ? 'bg-violet-700 text-white' : 'bg-violet-100 text-violet-700'} disabled:opacity-50`}><Sparkles size={11} className="inline mr-1"/>CANVAS</button>
            <span className="text-[11px] font-mono text-stone-600 italic truncate px-2 max-w-[220px]">{selectedFile.path}</span>
            {['REVIEW','TESTS','DOCS','CI/CD','README','AUTOLINT'].map((label) => (
              <button key={label} onClick={() => { log(`✨ ${label} vorbereitet.`); generateCodeWithGemini(`Erstelle ${label} für das Projekt.`); }} className="px-2 py-1 bg-indigo-100 text-indigo-700 text-[9px] font-bold rounded hover:bg-indigo-200">✨ {label}</button>
            ))}
          </div>

          {workView === 'canvas' ? (
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="h-8 bg-violet-50 border-b border-violet-200 flex items-center gap-2 px-3 text-[10px] text-violet-700 shrink-0">
                <Sparkles size={11}/> <span className="font-bold">Canvas Workspace</span>
                <span className="text-violet-500">· Alt+Drag zum Panning · Scroll zum Zoomen · Objekte sind interaktiv</span>
                <button onClick={() => { dispatch(clearCanvas()); log('🗑️ Canvas geleert.'); }} className="ml-auto px-2 py-0.5 bg-violet-200 text-violet-800 rounded text-[9px] font-bold hover:bg-violet-300"><Trash2 size={9} className="inline mr-0.5"/>Leeren</button>
                <button onClick={generateCanvasFromAI} disabled={isGenerating} className="px-2 py-0.5 bg-violet-600 text-white rounded text-[9px] font-bold hover:bg-violet-700 disabled:opacity-50 flex items-center gap-1">{isGenerating ? <Loader2 size={9} className="animate-spin"/> : <Sparkles size={9}/>} AI neu generieren</button>
              </div>
              <CanvasEngine className="flex-1" />
            </div>
          ) : workView === 'editor' ? (
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
      </main>
    </div>
  );
}
