/**
 * LLM Adapters Hook
 * 
 * Provides LLM adapters to components that need model health monitoring.
 * Builds adapters from user API keys and project settings.
 */

import { useMemo } from 'react';
import type { LlmAdapter } from '../llm/llmAdapter';
import { buildSovereignLlmAdapters } from '../llm/sovereignLlmAdapters';
import type { Card, ProjectSettings } from '../types';

export interface UseLlmAdaptersOptions {
  /** Primary Bridge proxy URL */
  primaryBridgeProxyUrl?: string;
  /** Primary Bridge model */
  primaryBridgeModel?: string;
  /** Pollinations API key */
  pollinationsApiKey?: string;
  /** Groq API key */
  groqApiKey?: string;
  /** HuggingFace API key */
  huggingfaceApiKey?: string;
  /** Together AI API key */
  togetherApiKey?: string;
  /** OpenRouter API key */
  openrouterApiKey?: string;
  /** Gemini API key */
  geminiApiKey?: string;
  /** Project cards for LocalSafe adapter */
  cards?: Card[];
  /** Project settings for LocalSafe adapter */
  settings?: ProjectSettings;
}

export interface UseLlmAdaptersReturn {
  /** All available LLM adapters */
  adapters: LlmAdapter[];
  /** Only enabled adapters */
  enabledAdapters: LlmAdapter[];
  /** Count of adapters */
  count: number;
  /** Whether any adapter is enabled */
  hasEnabledAdapter: boolean;
}

/**
 * Hook to build and provide LLM adapters
 */
export function useLlmAdapters(options: UseLlmAdaptersOptions = {}): UseLlmAdaptersReturn {
  const {
    cards = [],
    settings = { id: 'default', name: 'Default', createdAt: 0, updatedAt: 0 },
    ...apiKeys
  } = options;

  const adapters = useMemo(
    () => buildSovereignLlmAdapters({
      ...apiKeys,
      cards,
      settings,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      apiKeys.primaryBridgeProxyUrl,
      apiKeys.primaryBridgeModel,
      apiKeys.pollinationsApiKey,
      apiKeys.groqApiKey,
      apiKeys.huggingfaceApiKey,
      apiKeys.togetherApiKey,
      apiKeys.openrouterApiKey,
      apiKeys.geminiApiKey,
      cards.length,
    ]
  );

  const enabledAdapters = useMemo(
    () => adapters.filter((adapter) => adapter.enabled),
    [adapters]
  );

  return {
    adapters,
    enabledAdapters,
    count: adapters.length,
    hasEnabledAdapter: enabledAdapters.length > 0,
  };
}
