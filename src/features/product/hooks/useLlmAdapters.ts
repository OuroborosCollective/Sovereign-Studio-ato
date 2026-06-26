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
  primaryBridgeProxyUrl?: string;
  primaryBridgeModel?: string;
  pollinationsApiKey?: string;
  groqApiKey?: string;
  huggingfaceApiKey?: string;
  togetherApiKey?: string;
  openrouterApiKey?: string;
  geminiApiKey?: string;
  cards?: Card[];
  settings?: ProjectSettings;
}

export interface UseLlmAdaptersReturn {
  adapters: LlmAdapter[];
  enabledAdapters: LlmAdapter[];
  count: number;
  hasEnabledAdapter: boolean;
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

export function useLlmAdapters(options: UseLlmAdaptersOptions = {}): UseLlmAdaptersReturn {
  const {
    cards = [],
    settings = DEFAULT_PROJECT_SETTINGS,
    ...apiKeys
  } = options;

  const adapters = useMemo(
    () => buildSovereignLlmAdapters({
      ...apiKeys,
      cards,
      settings,
    }),
    [
      apiKeys.primaryBridgeProxyUrl,
      apiKeys.primaryBridgeModel,
      apiKeys.pollinationsApiKey,
      apiKeys.groqApiKey,
      apiKeys.huggingfaceApiKey,
      apiKeys.togetherApiKey,
      apiKeys.openrouterApiKey,
      apiKeys.geminiApiKey,
      cards,
      settings,
    ],
  );

  const enabledAdapters = useMemo(() => adapters.filter((adapter) => adapter.enabled), [adapters]);

  return {
    adapters,
    enabledAdapters,
    count: adapters.length,
    hasEnabledAdapter: enabledAdapters.length > 0,
  };
}
