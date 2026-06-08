import { create } from 'zustand';
import type { 
  Card, 
  FileItem, 
  ProjectSettings, 
  WorkView, 
  PipelineState,
  ProviderType,
  RepoFile,
  AwarenessSyncResult,
  ChatMessage
} from '../types';

// Default settings
export const defaultSettings: ProjectSettings = {
  repoMode: 'monorepo',
  packageManager: 'pnpm',
  installStrategy: 'workspace',
  linter: 'auto',
  specialization: 'React/Vite + Capacitor Android + GitHub Actions Release Pipeline',
  maxFixLoops: 3,
};

// Demo files
export const demoFiles: FileItem[] = [
  { path: 'src/App.tsx', icon: '🟦' },
  { path: 'src/main.tsx', icon: '🟦' },
  { path: 'package.json', icon: '📦' },
  { path: 'pnpm-workspace.yaml', icon: '🧩' },
  { path: '.github/workflows/ci.yml', icon: '⚙️' },
  { path: 'android/app/build.gradle', icon: '🤖' },
];

// Helper to generate IDs
const makeId = () => Math.random().toString(36).substring(2, 15);

// Starter cards
const starterCards = (): Card[] => [
  { id: makeId(), title: '1 · Wunsch', body: 'User beschreibt das gewünschte Produkt oder Feature in natürlicher Sprache.' },
  { id: makeId(), title: '2 · Repo lesen', body: 'Dateibaum, Struktur, Workflows und wichtige Dateien werden als Kontext genutzt.' },
  { id: makeId(), title: '3 · Code erzeugen', body: 'Der Agent wechselt in den Editor und schreibt sichtbaren Code in Dateien.' },
  { id: makeId(), title: '4 · Publish & Validate', body: 'Push/PR wird vorbereitet, Workflows werden geprüft, Fehler springen zurück in den Editor.' },
];

interface AppState {
  // API Keys
  geminiKey: string;
  githubToken: string;
  groqKey: string;
  hfKey: string;
  togetherKey: string;
  openrouterKey: string;

  // Repository
  repoUrl: string;
  repoBranch: string;
  repoFiles: RepoFile[];
  repoStatus: string;
  isRepoBusy: boolean;
  repoLoaded: boolean;

  // Awareness Sync
  syncResult: AwarenessSyncResult | null;
  isSyncing: boolean;

  // Product Builder
  blueprint: string;
  cards: Card[];
  selectedFile: FileItem;
  built: boolean;
  chatInput: string;
  logs: string[];
  workView: WorkView;
  pipelineState: PipelineState;
  fixLoops: number;
  showSettings: boolean;
  settings: ProjectSettings;
  generatedCode: string;
  isGenerating: boolean;

  // Current Provider
  currentProvider: ProviderType;

  // Chat Messages
  chatMessages: ChatMessage[];

  // Actions
  setGeminiKey: (key: string) => void;
  setGithubToken: (key: string) => void;
  setGroqKey: (key: string) => void;
  setHfKey: (key: string) => void;
  setTogetherKey: (key: string) => void;
  setOpenrouterKey: (key: string) => void;

  setRepoUrl: (url: string) => void;
  setRepoFiles: (files: RepoFile[]) => void;
  setRepoStatus: (status: string) => void;
  setIsRepoBusy: (busy: boolean) => void;
  setRepoLoaded: (loaded: boolean) => void;

  setSyncResult: (result: AwarenessSyncResult | null) => void;
  setIsSyncing: (syncing: boolean) => void;

  setBlueprint: (blueprint: string) => void;
  setSelectedFile: (file: FileItem) => void;
  setBuilt: (built: boolean) => void;
  setChatInput: (input: string) => void;
  addLog: (text: string) => void;
  clearLogs: () => void;
  setWorkView: (view: WorkView) => void;
  setPipelineState: (state: PipelineState) => void;
  incrementFixLoops: () => void;
  resetFixLoops: () => void;
  setShowSettings: (show: boolean) => void;
  setSettings: (settings: ProjectSettings) => void;
  setGeneratedCode: (code: string) => void;
  setIsGenerating: (generating: boolean) => void;

  setCurrentProvider: (provider: ProviderType) => void;

  // Chat Actions
  addChatMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void;
  clearChatMessages: () => void;

  // Initialize
  reset: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Initial API Keys
  geminiKey: '',
  githubToken: '',
  groqKey: '',
  hfKey: '',
  togetherKey: '',
  openrouterKey: '',

  // Repository
  repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
  repoBranch: 'main',
  repoFiles: [],
  repoStatus: 'Bereit. Repo-URL eingeben und laden.',
  isRepoBusy: false,
  repoLoaded: false,

  // Awareness Sync
  syncResult: null,
  isSyncing: false,

  // Product Builder
  blueprint: 'Baue aus diesem Workflow eine klickbare Mini-App mit GitHub Explorer, Auto-Resolver, Living Preview und Agent Workspace.',
  cards: starterCards(),
  selectedFile: demoFiles[0],
  built: false,
  chatInput: 'Setze diesen Workflow als echtes Produkt um.',
  logs: ['🚀 Sovereign Studio geladen. Keys eintragen und Repo laden.'],
  workView: 'editor',
  pipelineState: 'idle',
  fixLoops: 0,
  showSettings: false,
  settings: defaultSettings,
  generatedCode: '',
  isGenerating: false,

  // Current Provider
  currentProvider: 'mlvoca',

  // Chat Messages
  chatMessages: [],

  // Actions - API Keys
  setGeminiKey: (key) => set({ geminiKey: key }),
  setGithubToken: (key) => set({ githubToken: key }),
  setGroqKey: (key) => set({ groqKey: key }),
  setHfKey: (key) => set({ hfKey: key }),
  setTogetherKey: (key) => set({ togetherKey: key }),
  setOpenrouterKey: (key) => set({ openrouterKey: key }),

  // Actions - Repository
  setRepoUrl: (url) => set({ repoUrl: url }),
  setRepoFiles: (files) => set({ repoFiles: files }),
  setRepoStatus: (status) => set({ repoStatus: status }),
  setIsRepoBusy: (busy) => set({ isRepoBusy: busy }),
  setRepoLoaded: (loaded) => set({ repoLoaded: loaded }),

  // Actions - Awareness Sync
  setSyncResult: (result) => set({ syncResult: result }),
  setIsSyncing: (syncing) => set({ isSyncing: syncing }),

  // Actions - Product Builder
  setBlueprint: (blueprint) => set({ blueprint }),
  setSelectedFile: (file) => set({ selectedFile: file }),
  setBuilt: (built) => set({ built }),
  setChatInput: (input) => set({ chatInput: input }),
  addLog: (text) => set((state) => ({ 
    logs: [text, ...state.logs].slice(0, 50) 
  })),
  clearLogs: () => set({ logs: [] }),
  setWorkView: (view) => set({ workView: view }),
  setPipelineState: (state) => set({ pipelineState: state }),
  incrementFixLoops: () => set((state) => ({ fixLoops: state.fixLoops + 1 })),
  resetFixLoops: () => set({ fixLoops: 0 }),
  setShowSettings: (show) => set({ showSettings: show }),
  setSettings: (settings) => set({ settings }),
  setGeneratedCode: (code) => set({ generatedCode: code }),
  setIsGenerating: (generating) => set({ isGenerating: generating }),

  // Actions - Provider
  setCurrentProvider: (provider) => set({ currentProvider: provider }),

  // Actions - Chat
  addChatMessage: (message) => set((state) => ({
    chatMessages: [
      ...state.chatMessages,
      {
        ...message,
        id: makeId(),
        timestamp: Date.now(),
      },
    ],
  })),
  clearChatMessages: () => set({ chatMessages: [] }),

  // Reset
  reset: () => set({
    repoFiles: [],
    repoStatus: 'Bereit. Repo-URL eingeben und laden.',
    isRepoBusy: false,
    repoLoaded: false,
    syncResult: null,
    isSyncing: false,
    built: false,
    logs: ['🚀 Sovereign Studio geladen.'],
    pipelineState: 'idle',
    fixLoops: 0,
    generatedCode: '',
  }),
}));