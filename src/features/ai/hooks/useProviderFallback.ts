/**
 * useProviderFallback Hook
 * Provides automatic fallback to free LLM providers when primary fails
 * 
 * FIXED LOGIC:
 * - No key OR any error → ALWAYS fallback to free providers
 * - Uses gemini-2.0-flash as default model
 * - Puter.js is the PRIMARY free fallback (KEYLESS, unlimited, free)
 */

import { useState, useCallback, useEffect } from 'react';
import { providerManager, FREE_PROVIDERS, type ProviderType, type ProviderConfig, type ProviderResponse, type ProviderError } from '../providerManager';
import { geminiService } from '../geminiService';
import { keyStorage } from '../keyStorage';

// Default model - updated to gemini-2.0-flash
const DEFAULT_MODEL = 'gemini-2.0-flash';

// Re-export for convenience
export { providerManager, FREE_PROVIDERS, type ProviderType, type ProviderConfig, type ProviderResponse, type ProviderError };

export interface ProviderFallbackOptions {
  model?: string;
  temperature?: number;
  maxOutputTokens?: number;
  onFallback?: (from: ProviderType, to: ProviderType, error: string) => void;
  onProviderChanged?: (provider: ProviderType) => void;
}

export interface ProviderFallbackResult {
  generateContent: (prompt: string, apiKey?: string) => Promise<string>;
  isLoading: boolean;
  error: string | null;
  currentProvider: ProviderType;
  setProviderApiKey: (provider: ProviderType, key: string) => void;
  configuredProviders: ProviderType[];
}

/**
 * Hook for generating content with automatic provider fallback
 * 
 * FIXED FALLBACK LOGIC:
 * 1. If no API key → immediate fallback to Puter.js (KEYLESS!)
 * 2. If API key provided → try Gemini first
 * 3. On ANY error (quota, auth, network, etc.) → fallback to free providers
 * 4. Free provider chain: Puter.js → Groq → OpenRouter → HuggingFace → Together
 */
export function useProviderFallback(options: ProviderFallbackOptions = {}): ProviderFallbackResult {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentProvider, setCurrentProvider] = useState<ProviderType>('gemini');

  // Set API keys from persistent storage on mount
  useEffect(() => {
    const loadKeys = async () => {
      const [groqKey, hfKey, togetherKey, openrouterKey] = await Promise.all([
        keyStorage.get('sovereign_groq_api_key'),
        keyStorage.get('sovereign_huggingface_api_key'),
        keyStorage.get('sovereign_together_api_key'),
        keyStorage.get('sovereign_openrouter_api_key'),
      ]);
      if (groqKey) providerManager.setApiKey('groq', groqKey);
      if (hfKey) providerManager.setApiKey('huggingface', hfKey);
      if (togetherKey) providerManager.setApiKey('together', togetherKey);
      if (openrouterKey) providerManager.setApiKey('openrouter', openrouterKey);
    };
    loadKeys();
  }, []);

  const handleFallback = useCallback((from: ProviderType, to: ProviderType, errorMsg: string) => {
    console.log(`🔄 Fallback: ${from} → ${to}: ${errorMsg}`);
    setCurrentProvider(to);
    options.onFallback?.(from, to, errorMsg);
  }, [options.onFallback]);

  const setProviderApiKey = useCallback((provider: ProviderType, key: string) => {
    providerManager.setApiKey(provider, key);
    void keyStorage.set(`sovereign_${provider}_api_key`, key);
  }, []);

  /**
   * FIXED: generateContent - handles all cases of no key or errors
   * 
   * Logic:
   * - If NO key provided → skip Gemini, go straight to free providers
   * - If key provided → try Gemini first
   * - On ANY error from Gemini → fallback to free providers
   */
  const generateContent = useCallback(async (prompt: string, geminiApiKey?: string): Promise<string> => {
    setIsLoading(true);
    setError(null);

    try {
      // FIXED: Determine effective model
      const effectiveModel = options.model || DEFAULT_MODEL;
      
      // FIXED: If no API key → skip to free providers immediately
      if (!geminiApiKey?.trim()) {
        console.log('🔄 No Gemini API key → using free providers');
        handleFallback('gemini', 'openrouter', 'No API key provided');
      } else {
        // Try Gemini first if key is available
        try {
          const result = await geminiService.generateText(geminiApiKey, prompt, {
            model: effectiveModel,
            temperature: options.temperature,
            maxOutputTokens: options.maxOutputTokens,
          });
          setCurrentProvider('gemini');
          return result;
        } catch (err: any) {
          // FIXED: ANY error → fallback to free providers
          // Don't check for retryable errors - just fallback on everything
          const errorMsg = err?.message || String(err);
          console.log(`🔄 Gemini failed: ${errorMsg} → falling back to free providers`);
          handleFallback('gemini', 'openrouter', errorMsg);
          // Continue to free providers - don't throw
        }
      }

      // Use provider manager for fallback chain
      const response = await providerManager.generateWithFallback(
        geminiApiKey || '',
        'gemini',
        prompt,
        {
          model: effectiveModel,
          temperature: options.temperature,
          maxOutputTokens: options.maxOutputTokens,
        },
        handleFallback
      );

      setCurrentProvider(response.provider);
      options.onProviderChanged?.(response.provider);
      return response.text;

    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      setError(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [options, handleFallback]);

  return {
    generateContent,
    isLoading,
    error,
    currentProvider,
    setProviderApiKey,
    configuredProviders: providerManager.getConfiguredProviders(),
  };
}

/**
 * Provider status info for UI display
 */
export interface ProviderStatus {
  type: ProviderType;
  name: string;
  model: string;
  hasKey: boolean;
  isFree: boolean;
  description: string;
}

export const PROVIDER_INFO: ProviderStatus[] = [
  {
    type: 'gemini',
    name: 'Google Gemini',
    model: 'gemini-2.0-flash',
    hasKey: false,
    isFree: false,
    description: 'Primary provider. Requires Google AI API key.',
  },
  {
    type: 'puter',
    name: 'Puter.js',
    model: 'gemini-2.0-flash-exp',
    hasKey: false,  // KEYLESS!
    isFree: true,
    description: '⭐ KEYLESS FREE! Puter.js provides unlimited free AI calls (OpenAI, Claude, Gemini). No API key needed!',
  },
  {
    type: 'groq',
    name: 'Groq',
    model: 'llama-3.1-8b-instant',
    hasKey: false,
    isFree: true,
    description: 'Ultra-fast LPU inference. Free tier: 14,400 requests/day.',
  },
  {
    type: 'openrouter',
    name: 'OpenRouter',
    model: 'llama-3.1-8b-instruct:free',
    hasKey: false,
    isFree: true,
    description: 'Aggregates many providers with free models.',
  },
  {
    type: 'huggingface',
    name: 'HuggingFace',
    model: 'Llama-3.2-1B-Instruct',
    hasKey: false,
    isFree: true,
    description: 'Open source models. Some require API key.',
  },
  {
    type: 'together',
    name: 'Together AI',
    model: 'Llama-3.2-1B-Instruct',
    hasKey: false,
    isFree: true,
    description: 'Many open models. Free tier available.',
  },
];

export function getProviderStatus(): ProviderStatus[] {
  const configured = providerManager.getConfiguredProviders();
  return PROVIDER_INFO.map(p => ({
    ...p,
    hasKey: configured.includes(p.type),
  }));
}