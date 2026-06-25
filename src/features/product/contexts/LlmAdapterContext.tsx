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

// ============================================================================
// Types
// ============================================================================

export interface LlmAdapterContextValue {
  /** All available LLM adapters */
  adapters: LlmAdapter[];
  /** Only enabled adapters */
  enabledAdapters: LlmAdapter[];
  /** Count of all adapters */
  count: number;
  /** Whether any adapter is enabled */
  hasEnabledAdapter: boolean;
  /** Whether adapters are loading */
  isLoading: boolean;
}

export interface LlmAdapterProviderProps {
  children: ReactNode;
  /** Override cards for LocalSafe adapter */
  cards?: Card[];
  /** Override settings for LocalSafe adapter */
  settings?: ProjectSettings;
  /** Override API keys */
  apiKeys?: {
    primaryBridgeProxyUrl?: string;
    primaryBridgeModel?: string;
    pollinationsApiKey?: string;
    groqApiKey?: string;
    huggingfaceApiKey?: string;
    togetherApiKey?: string;
    openrouterApiKey?: string;
    geminiApiKey?: string;
  };
}

// ============================================================================
// Context
// ============================================================================

const LlmAdapterContext = createContext<LlmAdapterContextValue | null>(null);

/**
 * Get LLM adapters from context
 */
export function useLlmAdaptersContext(): LlmAdapterContextValue {
  const context = useContext(LlmAdapterContext);
  if (!context) {
    throw new Error('useLlmAdaptersContext must be used within LlmAdapterProvider');
  }
  return context;
}

/**
 * Get all LLM adapters from context
 */
export function useAllLlmAdapters(): LlmAdapter[] {
  return useLlmAdaptersContext().adapters;
}

/**
 * Get only enabled LLM adapters from context
 */
export function useEnabledLlmAdapters(): LlmAdapter[] {
  return useLlmAdaptersContext().enabledAdapters;
}

// ============================================================================
// Provider
// ============================================================================

export function LlmAdapterProvider({
  children,
  cards = [],
  settings = { id: 'default', name: 'Default', createdAt: 0, updatedAt: 0 },
  apiKeys = {},
}: LlmAdapterProviderProps) {
  // Get user API keys from hook
  const { apiKeys: userApiKeys, isLoading: isUserKeysLoading } = useUserApiKeys();

  // Merge API keys
  const mergedApiKeys = {
    ...userApiKeys,
    ...apiKeys,
  };

  // Build adapters
  const adapters = useMemo(
    () => buildSovereignLlmAdapters({
      ...mergedApiKeys,
      cards,
      settings,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      mergedApiKeys.primaryBridgeProxyUrl,
      mergedApiKeys.primaryBridgeModel,
      mergedApiKeys.pollinationsApiKey,
      mergedApiKeys.groqApiKey,
      mergedApiKeys.huggingfaceApiKey,
      mergedApiKeys.togetherApiKey,
      mergedApiKeys.openrouterApiKey,
      mergedApiKeys.geminiApiKey,
      cards.length,
    ]
  );

  // Filter enabled adapters
  const enabledAdapters = useMemo(
    () => adapters.filter((adapter) => adapter.enabled),
    [adapters]
  );

  const value: LlmAdapterContextValue = {
    adapters,
    enabledAdapters,
    count: adapters.length,
    hasEnabledAdapter: enabledAdapters.length > 0,
    isLoading: isUserKeysLoading,
  };

  return (
    <LlmAdapterContext.Provider value={value}>
      {children}
    </LlmAdapterContext.Provider>
  );
}
