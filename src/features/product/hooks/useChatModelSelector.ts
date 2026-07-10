import { useMemo, useCallback } from 'react';
import type { LlmAdapter } from '../llm/llmAdapter';
import type { LlmModelInfo } from '../components/ChatSidebar';

/**
 * Maps adapter kinds to readable provider names
 */
function getProviderLabel(id: string, kind: string): string {
  switch (id) {
    case 'optional-user-keys':
      return 'Sovereign Agent Bridge';
    case 'mlvoca':
      return 'MLVoca';
    case 'pollinations':
      return 'Pollinations';
    case 'groq':
      return 'Groq';
    case 'huggingface':
      return 'HuggingFace';
    case 'together':
      return 'Together AI';
    case 'openrouter':
      return 'OpenRouter';
    case 'gemini':
      return 'Google Gemini';
    case 'local-safe':
      return 'Local Safe';
    default:
      return id;
  }
}

/**
 * Maps adapter kinds to display labels
 */
function getModelLabel(id: string, kind: string): string {
  switch (id) {
    case 'optional-user-keys':
      return 'Primary Bridge';
    case 'mlvoca':
      return 'MLVoca (No-Key)';
    case 'pollinations':
      return 'Pollinations (No-Key)';
    case 'groq':
      return 'Groq';
    case 'huggingface':
      return 'HuggingFace';
    case 'together':
      return 'Together AI';
    case 'openrouter':
      return 'OpenRouter';
    case 'gemini':
      return 'Gemini';
    case 'local-safe':
      return 'Local Analysis';
    default:
      return id;
  }
}

/**
 * Extract available models from LLM adapters
 */
export function extractModelsFromAdapters(adapters: LlmAdapter[]): LlmModelInfo[] {
  return adapters
    .filter(adapter => adapter.enabled)
    .map(adapter => {
      // Normalize kind to supported types
      let kind: LlmModelInfo['kind'] = 'local-safe';
      if (adapter.kind === 'user-key' || adapter.kind === 'no-key' || adapter.kind === 'opt-in' || adapter.kind === 'local-safe') {
        kind = adapter.kind;
      }
      return {
        id: adapter.id,
        label: getModelLabel(adapter.id, adapter.kind),
        provider: getProviderLabel(adapter.id, adapter.kind),
        kind,
      };
    });
}

/**
 * Hook to manage model selection state and auto-detection
 */
export function useChatModelSelector(
  adapters: LlmAdapter[],
  defaultModelId?: string,
) {
  // Extract available models from adapters
  const availableModels = useMemo(() => extractModelsFromAdapters(adapters), [adapters]);

  // Select default model (user-key first, then no-key)
  const selectedModelId = useMemo(() => {
    if (defaultModelId && availableModels.some(m => m.id === defaultModelId)) {
      return defaultModelId;
    }
    // Prefer user-key providers
    const userKey = availableModels.find(m => m.kind === 'user-key');
    if (userKey) return userKey.id;
    // Fall back to first available
    return availableModels[0]?.id;
  }, [availableModels, defaultModelId]);

  const selectedModel = useMemo(
    () => availableModels.find(m => m.id === selectedModelId),
    [availableModels, selectedModelId],
  );

  // Change model handler
  const handleModelChange = useCallback((modelId: string) => {
    // This callback will be passed to the chat component
    // The parent should update the active adapter based on selection
    return modelId;
  }, []);

  return {
    availableModels,
    selectedModelId,
    selectedModel,
    handleModelChange,
  };
}

/**
 * Get adapter by ID from the adapter list
 */
export function getAdapterById(adapters: LlmAdapter[], id: string): LlmAdapter | undefined {
  return adapters.find(adapter => adapter.id === id);
}

/**
 * Reorder adapters to prioritize selected model
 */
export function prioritizeAdapter(adapters: LlmAdapter[], selectedId: string): LlmAdapter[] {
  const selected = adapters.find(a => a.id === selectedId);
  if (!selected) return adapters;

  // Move selected adapter to front with highest priority
  return [
    { ...selected, priority: -100 },
    ...adapters.filter(a => a.id !== selectedId),
  ];
}
