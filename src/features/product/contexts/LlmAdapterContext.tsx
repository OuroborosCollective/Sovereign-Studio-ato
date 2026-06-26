/**
 * LLM Adapter Context
 *
 * Global React context for LLM adapters.
 * Provides adapters to all components that need model health monitoring.
 */

import React, { createContext, useContext, useMemo, ReactNode } from 'react';
import type { LlmAdapter } from '../llm/llmAdapter';
import { buildSovereignLlmAdapters } from '../llm/sovereignLlmAdapters';
import { useUserApiKeys } from '../hooks/useUserApiKeys';
import type { Card, ProjectSettings } from '../types';
import type { UserApiKeys } from '../components/UserKeyManager';

export interface LlmAdapterContextValue {
  adapters: LlmAdapter[];
  enabledAdapters: LlmAdapter[];
  count: number;
  hasEnabledAdapter: boolean;
  isLoading: boolean;
}

export interface LlmAdapterProviderProps {
  children: ReactNode;
  cards?: Card[];
  settings?: ProjectSettings;
  apiKeys?: UserApiKeys & {
    primaryBridgeProxyUrl?: string;
    primaryBridgeModel?: string;
  };
}

const DEFAULT_PROJECT_SETTINGS: ProjectSettings = {
  repoMode: 'single',
  packageManager: 'auto',
  installStrategy: 'safe',
  linter: 'auto',
  specialization: 'sovereign-studio',
  maxFixLoops: 3,
  workMode: 'assisted',
};

const LlmAdapterContext = createContext<LlmAdapterContextValue | null>(null);

export function useLlmAdaptersContext(): LlmAdapterContextValue {
  const context = useContext(LlmAdapterContext);
  if (!context) throw new Error('useLlmAdaptersContext must be used within LlmAdapterProvider');
  return context;
}

export function useAllLlmAdapters(): LlmAdapter[] {
  return useLlmAdaptersContext().adapters;
}

export function useEnabledLlmAdapters(): LlmAdapter[] {
  return useLlmAdaptersContext().enabledAdapters;
}

export function LlmAdapterProvider({
  children,
  cards = [],
  settings = DEFAULT_PROJECT_SETTINGS,
  apiKeys = {},
}: LlmAdapterProviderProps) {
  const { userApiKeys, isLoading: isUserKeysLoading } = useUserApiKeys();

  const mergedApiKeys = useMemo(() => ({
    ...userApiKeys,
    ...apiKeys,
  }), [apiKeys, userApiKeys]);

  const adapters = useMemo(
    () => buildSovereignLlmAdapters({
      ...mergedApiKeys,
      cards,
      settings,
    }),
    [
      mergedApiKeys.primaryBridgeProxyUrl,
      mergedApiKeys.primaryBridgeModel,
      mergedApiKeys.pollinationsApiKey,
      mergedApiKeys.groqApiKey,
      mergedApiKeys.huggingfaceApiKey,
      mergedApiKeys.togetherApiKey,
      mergedApiKeys.openrouterApiKey,
      mergedApiKeys.geminiApiKey,
      cards,
      settings,
    ],
  );

  const enabledAdapters = useMemo(() => adapters.filter((adapter) => adapter.enabled), [adapters]);

  const value: LlmAdapterContextValue = useMemo(() => ({
    adapters,
    enabledAdapters,
    count: adapters.length,
    hasEnabledAdapter: enabledAdapters.length > 0,
    isLoading: isUserKeysLoading,
  }), [adapters, enabledAdapters, isUserKeysLoading]);

  return (
    <LlmAdapterContext.Provider value={value}>
      {children}
    </LlmAdapterContext.Provider>
  );
}
