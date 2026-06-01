/**
 * RefactorContext - React Context for RefactorEngine
 * 
 * Provides global access to AI-powered refactoring throughout the app.
 * Must be used at the top level of the application.
 */

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { 
  refactorEngine, 
  type RefactorContext as RefactorContextType,
  type RefactorPlan,
  type RefactorTask,
  type RefactorFile,
  type RefactorOptions,
} from './RefactorEngine';

// ============================================================
// Context Types
// ============================================================

interface RefactorContextValue {
  // Engine state
  isInitialized: boolean;
  currentProvider: string;
  
  // Project context
  repoUrl: string;
  files: RefactorFile[];
  setRepoUrl: (url: string) => void;
  setFiles: (files: RefactorFile[]) => void;
  
  // AI Keys (optional)
  geminiKey: string;
  groqKey: string;
  setGeminiKey: (key: string) => void;
  setGroqKey: (key: string) => void;
  
  // Core operations
  analyze: (repoUrl: string, files: RefactorFile[]) => Promise<RefactorPlan>;
  generate: (prompt: string, options?: RefactorOptions) => Promise<string>;
  generateCode: (task: RefactorTask) => Promise<string>;
  explain: (code: string) => Promise<string>;
  generateFeature: (description: string, files?: string[]) => Promise<string>;
  
  // History
  history: RefactorPlan[];
  currentPlan: RefactorPlan | null;
  setCurrentPlan: (plan: RefactorPlan | null) => void;
  
  // Status
  isLoading: boolean;
  error: string | null;
  lastResult: string | null;
}

const RefactorContext = createContext<RefactorContextValue | null>(null);

// ============================================================
// Storage Keys
// ============================================================

const STORAGE_KEYS = {
  gemini: 'sovereign_gemini_api_key',
  groq: 'sovereign_groq_api_key',
  repo: 'sovereign_repo_url',
} as const;

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

// ============================================================
// Provider Component
// ============================================================

interface RefactorProviderProps {
  children: React.ReactNode;
}

export function RefactorProvider({ children }: RefactorProviderProps) {
  // Keys
  const [geminiKey, setGeminiKeyState] = useState(() => loadFromStorage(STORAGE_KEYS.gemini));
  const [groqKey, setGroqKeyState] = useState(() => loadFromStorage(STORAGE_KEYS.groq));

  // Project state
  const [repoUrl, setRepoUrlState] = useState(() => loadFromStorage(STORAGE_KEYS.repo, 'https://github.com/OuroborosCollective/Sovereign-Studio-ato'));
  const [files, setFiles] = useState<RefactorFile[]>([]);

  // Plans
  const [currentPlan, setCurrentPlan] = useState<RefactorPlan | null>(null);
  const [history, setHistory] = useState<RefactorPlan[]>([]);

  // Status
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);

  // Initialize engine with keys
  useEffect(() => {
    refactorEngine.setKeys({
      gemini: geminiKey,
      groq: groqKey,
    });
  }, [geminiKey, groqKey]);

  // Setters that persist to storage
  const setGeminiKey = useCallback((key: string) => {
    setGeminiKeyState(key);
    saveToStorage(STORAGE_KEYS.gemini, key);
  }, []);

  const setGroqKey = useCallback((key: string) => {
    setGroqKeyState(key);
    saveToStorage(STORAGE_KEYS.groq, key);
  }, []);

  const setRepoUrl = useCallback((url: string) => {
    setRepoUrlState(url);
    saveToStorage(STORAGE_KEYS.repo, url);
  }, []);

  // Core operations
  const analyze = useCallback(async (repoUrl: string, files: RefactorFile[]): Promise<RefactorPlan> => {
    setIsLoading(true);
    setError(null);
    try {
      const plan = await refactorEngine.analyzeRepo(repoUrl, files);
      setCurrentPlan(plan);
      setHistory(prev => [plan, ...prev].slice(0, 20));
      return plan;
    } catch (err: any) {
      const msg = err?.message || 'Analysis failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const generate = useCallback(async (prompt: string, options?: RefactorOptions): Promise<string> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await refactorEngine.generate(prompt, options);
      setLastResult(result);
      return result;
    } catch (err: any) {
      const msg = err?.message || 'Generation failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const generateCode = useCallback(async (task: RefactorTask): Promise<string> => {
    setIsLoading(true);
    setError(null);
    try {
      const code = await refactorEngine.generateCode(task);
      setLastResult(code);
      return code;
    } catch (err: any) {
      const msg = err?.message || 'Code generation failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const explain = useCallback(async (code: string): Promise<string> => {
    setIsLoading(true);
    setError(null);
    try {
      const explanation = await refactorEngine.explainCode(code);
      setLastResult(explanation);
      return explanation;
    } catch (err: any) {
      const msg = err?.message || 'Explanation failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const generateFeature = useCallback(async (description: string, filePaths?: string[]): Promise<string> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await refactorEngine.generateFeature(description, filePaths);
      setLastResult(result);
      return result;
    } catch (err: any) {
      const msg = err?.message || 'Feature generation failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const value: RefactorContextValue = {
    isInitialized: true,
    currentProvider: refactorEngine.getCurrentProvider(),
    repoUrl,
    files,
    setRepoUrl,
    setFiles,
    geminiKey,
    groqKey,
    setGeminiKey,
    setGroqKey,
    analyze,
    generate,
    generateCode,
    explain,
    generateFeature,
    history,
    currentPlan,
    setCurrentPlan,
    isLoading,
    error,
    lastResult,
  };

  return (
    <RefactorContext.Provider value={value}>
      {children}
    </RefactorContext.Provider>
  );
}

// ============================================================
// Hook
// ============================================================

export function useRefactor(): RefactorContextValue {
  const context = useContext(RefactorContext);
  if (!context) {
    throw new Error('useRefactor must be used within <RefactorProvider>');
  }
  return context;
}

// ============================================================
// Convenience Hooks
// ============================================================

export function useAnalyze() {
  const { analyze } = useRefactor();
  return analyze;
}

export function useGenerate() {
  const { generate } = useRefactor();
  return generate;
}

export function useGenerateCode() {
  const { generateCode } = useRefactor();
  return generateCode;
}

export function useExplain() {
  const { explain } = useRefactor();
  return explain;
}

export function useProviderStatus() {
  const { geminiKey, groqKey, currentProvider, isLoading } = useRefactor();
  return {
    hasGemini: !!geminiKey?.trim(),
    hasGroq: !!groqKey?.trim(),
    currentProvider,
    isFreeMode: !geminiKey?.trim(),
    isLoading,
  };
}