/**
 * LauncherContext — liefert Launcher-Tools Runtime-Kontext.
 *
 * Wird in BuilderContainer via Provider gesetzt.
 * Launcher-Tools lesen hieraus (z.B. geminiApiKey für VpsChat).
 *
 * Issue #453
 */

import React, { createContext, useContext } from 'react';

export interface LauncherContextValue {
  /** Gemini API Key — optional, aus UserKeyManager / localStorage */
  geminiApiKey?: string;
}

const LauncherContext = createContext<LauncherContextValue>({});

export function LauncherProvider({
  value,
  children,
}: {
  value: LauncherContextValue;
  children: React.ReactNode;
}) {
  return <LauncherContext.Provider value={value}>{children}</LauncherContext.Provider>;
}

export function useLauncherContext(): LauncherContextValue {
  return useContext(LauncherContext);
}

/** Liest geminiApiKey direkt aus localStorage (sovereign_gemini_api_key). */
export function readGeminiApiKeyFromStorage(): string | undefined {
  try {
    const raw = localStorage.getItem('sovereign_gemini_api_key');
    return raw?.trim() || undefined;
  } catch {
    return undefined;
  }
}
