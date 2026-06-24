/**
 * Provider Manager - Free LLM API Fallback System
 * Auto-switches between providers when primary fails (auth errors, quota, etc.)
 * 
 * Supported Free Tier Providers (Priority Order):
 * - mlvoca.com (NO API key required, default)
 * - Groq (LPU inference, very fast, generous free tier)
 * - HuggingFace (Inference API, many free models)
 * - Together AI (free tier with many models)
 * - OpenRouter (aggregator with free models)
 * - Google Gemini (requires API key)
 */

import { GoogleGenerativeAI, GenerationConfig } from '@google/generative-ai';
import { GeminiRequestOptions } from './geminiService';
import { maskSecrets } from '../../shared/utils/crypto';

// Provider Types
export type ProviderType = 'mlvoca' | 'groq' | 'huggingface' | 'together' | 'openrouter' | 'gemini' | 'pollinations';

export interface ProviderConfig {
  type: ProviderType;
  apiKey?: string;
  baseURL: string;
  model: string;
  supportsStreaming?: boolean;
  maxTokens?: number;
  priority: number;
}

export interface ProviderResponse {
  text: string;
  provider: ProviderType;
  model: string;
  usage?: {
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
  };
}

export interface ProviderError {
  provider: ProviderType;
  error: string;
  statusCode?: number;
  isRetryable: boolean;
}

// Free Provider Configurations (Priority Order - mlvoca first as default no-key)
export const FREE_PROVIDERS: ProviderConfig[] = [
  {
    type: 'mlvoca',
    baseURL: 'https://mlvoca.com',
    model: 'deepseek-r1:1.5b',
    supportsStreaming: true,
    maxTokens: 2048,
    priority: 0, // Default - no API key needed!
  },
  {
    type: 'pollinations',
    baseURL: 'https://gen.pollinations.ai',
    model: 'openai',
    supportsStreaming: true,
    maxTokens: 4096,
    priority: 1, // Second fallback - no API key needed!
  },
  {
    type: 'groq',
    baseURL: 'https://api.groq.com/openai/v1',
    model: 'llama-3.1-8b-instant',
    supportsStreaming: true,
    maxTokens: 8192,
    priority: 2,
  },
  {
    type: 'huggingface',
    baseURL: 'https://api-inference.huggingface.co/models',
    model: 'meta-llama/Llama-3.2-1B-Instruct',
    supportsStreaming: false,
    maxTokens: 2048,
    priority: 3,
  },
  {
    type: 'together',
    baseURL: 'https://api.together.xyz/v1',
    model: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
    supportsStreaming: true,
    maxTokens: 4096,
    priority: 4,
  },
  {
    type: 'openrouter',
    baseURL: 'https://openrouter.ai/api/v1',
    model: 'meta-llama/llama-3.1-8b-instruct:free',
    supportsStreaming: true,
    maxTokens: 8192,
    priority: 5,
  },
];

// Known free API keys (demo/public keys from providers)
const PUBLIC_FREE_KEYS: Partial<Record<ProviderType, string>> = {
  // Groq - public sandbox keys for testing (rate limited)
  groq: '',
  // HuggingFace - free tier doesn't need key for basic inference
  huggingface: '',
  // Together AI - requires key
  together: '',
  // OpenRouter - requires key
  openrouter: '',
};

/**
 * Checks if error is retryable (auth issues, quota)
 */
function isRetryableError(error: ProviderError): boolean {
  const retryableCodes = [401, 403, 429, 500, 502, 503, 504];
  const retryableMessages = [
    'quota', 'rate limit', 'RESOURCE_EXHAUSTED', 'context_length',
    'authentication', 'api key', 'invalid', 'unauthorized',
    'rate_limit_exceeded', 'too many requests'
  ];
  
  if (error.statusCode && retryableCodes.includes(error.statusCode)) return true;
  if (error.isRetryable) return true;
  
  const msg = error.error.toLowerCase();
  return retryableMessages.some(m => msg.includes(m));
}

/**
 * Maps model names between providers
 */
function mapModelForProvider(model: string, targetProvider: ProviderType): string {
  // Model mapping for compatibility
  const modelMap: Partial<Record<string, Partial<Record<ProviderType, string>>>> = {
    'gemini-1.5-flash': {
      groq: 'llama-3.1-8b-instant',
      huggingface: 'meta-llama/Llama-3.2-1B-Instruct',
      together: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
      openrouter: 'meta-llama/llama-3.1-8b-instruct:free',
      pollinations: 'openai',
    },
    'gemini-1.5-pro': {
      groq: 'llama-3.1-70b-versatile',
      huggingface: 'meta-llama/Llama-3.2-3B-Instruct',
      together: 'meta-llama/Llama-3.2-70B-Instruct-Turbo',
      openrouter: 'meta-llama/llama-3.1-70b-instruct:free',
      pollinations: 'openai-large',
    },
  };
  
  // Try direct mapping first
  if (modelMap[model]?.[targetProvider]) {
    return modelMap[model][targetProvider];
  }
  
  // For unknown models, return a sensible default for the provider
  const defaults: Partial<Record<ProviderType, string>> = {
    gemini: model,
    mlvoca: 'deepseek-r1:1.5b',
    pollinations: 'openai',
    groq: 'llama-3.1-8b-instant',
    huggingface: 'meta-llama/Llama-3.2-1B-Instruct',
    together: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
    openrouter: 'meta-llama/llama-3.1-8b-instruct:free',
  };
  
  return defaults[targetProvider] || 'openai';
}

/**
 * Generic helper for provider API calls with error handling
 */
async function fetchWithProviderError(
  url: string,
  options: RequestInit,
  provider: ProviderType
): Promise<Response> {
  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      let errorMsg: string;

      if (errorData?.error?.message) {
        errorMsg = errorData.error.message;
      } else if (errorData?.error) {
        errorMsg = typeof errorData.error === 'string' ? errorData.error : JSON.stringify(errorData.error);
      } else if (Array.isArray(errorData) && errorData[0]?.error) {
        errorMsg = errorData[0].error;
      } else {
        errorMsg = await response.text().catch(() => `HTTP ${response.status}`) || `HTTP ${response.status}`;
      }

      throw {
        provider,
        error: maskSecrets(errorMsg),
        statusCode: response.status,
        isRetryable: response.status === 429 || response.status >= 500,
      };
    }
    return response;
  } catch (error: any) {
    if (error.provider) throw error; // Already formatted

    // Handle network errors
    const isNetworkError = error.name === 'TypeError' && (error.message.toLowerCase().includes('fetch') || error.message.toLowerCase().includes('network'));
    throw {
      provider,
      error: error.message || 'Network error',
      isRetryable: isNetworkError || error.status === 429 || error.status >= 500,
    };
  }
}

/**
 * Helper for OpenAI-compatible chat completion APIs
 */
async function callOpenAICompatible(
  provider: ProviderType,
  url: string,
  apiKey: string | undefined,
  model: string,
  prompt: string,
  options: GeminiRequestOptions,
  extraHeaders: Record<string, string> = {},
  defaultMaxTokens: number = 2048
): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, provider);

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...extraHeaders,
  };

  if (apiKey?.trim()) {
    headers['Authorization'] = `Bearer ${apiKey.trim()}`;
  }

  const response = await fetchWithProviderError(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model: mappedModel,
      messages: [{ role: 'user', content: prompt }],
      temperature: options.temperature ?? 0.7,
      max_tokens: options.maxOutputTokens ?? defaultMaxTokens,
      stream: false,
    }),
  }, provider);

  const data = await response.json();
  return {
    text: data.choices?.[0]?.message?.content || '',
    provider,
    model: mappedModel,
    usage: data.usage,
  };
}

// ============================================================
// MLVOCA - Free No-Key API (Default Provider)
// ============================================================
export async function callMlvoCa(model: string, prompt: string, options: GeminiRequestOptions = {}): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'mlvoca');
  
  // Timeout wrapper to prevent endless loading (10 second timeout)
  const timeoutPromise = new Promise<never>((_, reject) => {
    setTimeout(() => reject({
      provider: 'mlvoca' as ProviderType,
      error: 'MLVOCA request timed out after 10 seconds',
      isRetryable: true,
    }), 10000);
  });
  
  const fetchPromise = fetchWithProviderError('https://mlvoca.com/api/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: mappedModel,
      prompt: prompt,
      stream: false, // For simplicity, use non-streaming
      options: {
        temperature: options.temperature ?? 0.7,
      },
      keep_alive: '5m',
    }),
  }, 'mlvoca');
  
  let response: Response;
  try {
    response = await Promise.race([fetchPromise, timeoutPromise]);
  } catch (error) {
    // If timeout wins, the error is already thrown
    throw error;
  }
  
  const data = await response.json();
  return {
    text: data.response || '',
    provider: 'mlvoca',
    model: mappedModel,
  };
}

// ============================================================
// Groq - Free Tier
// ============================================================
export async function callGroq(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  return callOpenAICompatible(
    'groq',
    'https://api.groq.com/openai/v1/chat/completions',
    apiKey,
    model,
    prompt,
    options
  );
}

// ============================================================
// HuggingFace - Inference API
// ============================================================
export async function callHuggingFace(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'huggingface');
  const url = `https://api-inference.huggingface.co/models/${mappedModel}`;
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (apiKey?.trim()) {
    headers['Authorization'] = `Bearer ${apiKey.trim()}`;
  }
  
  const response = await fetchWithProviderError(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      inputs: prompt,
      parameters: {
        temperature: options.temperature ?? 0.7,
        max_new_tokens: options.maxOutputTokens ?? 2048,
      },
    }),
  }, 'huggingface');
  
  const data = await response.json();
  const text = Array.isArray(data) ? data[0]?.generated_text || '' : data.generated_text || '';
  
  return {
    text,
    provider: 'huggingface',
    model: mappedModel,
  };
}

// ============================================================
// Together AI - Free Tier
// ============================================================
export async function callTogether(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  return callOpenAICompatible(
    'together',
    'https://api.together.xyz/v1/chat/completions',
    apiKey,
    model,
    prompt,
    options
  );
}

// ============================================================
// OpenRouter - Free Models
// ============================================================
export async function callOpenRouter(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  return callOpenAICompatible(
    'openrouter',
    'https://openrouter.ai/api/v1/chat/completions',
    apiKey,
    model,
    prompt,
    options,
    {
      'HTTP-Referer': 'https://sovereign-studio.app',
      'X-Title': 'Sovereign Studio',
    }
  );
}

// ============================================================
// Pollinations - Free API with Optional Key (Ultimate Fallback)
// ============================================================
export async function callPollinations(model: string, prompt: string, options: GeminiRequestOptions = {}, apiKey?: string): Promise<ProviderResponse> {
  return callOpenAICompatible(
    'pollinations',
    'https://gen.pollinations.ai/v1/chat/completions',
    apiKey,
    model,
    prompt,
    options,
    {},
    4096
  );
}

export class ProviderManager {
  private userApiKeys: Partial<Record<ProviderType, string>> = {};
  private lastUsedProvider: ProviderType | null = null;
  private failedProviders: Set<ProviderType> = new Set();

  constructor() {
    // Initialize with empty keys - user can set them later
    this.userApiKeys = {};
  }

  /**
   * Set API key for a specific provider
   */
  setApiKey(provider: ProviderType, key: string): void {
    this.userApiKeys[provider] = key;
    this.failedProviders.delete(provider);
  }

  /**
   * Clear failed provider status (e.g., after cooldown)
   */
  resetFailedProviders(): void {
    this.failedProviders.clear();
  }

  /**
   * Get available providers sorted by priority
   */
  getAvailableProviders(): ProviderConfig[] {
    return FREE_PROVIDERS
      .filter(p => !this.failedProviders.has(p.type))
      .sort((a, b) => a.priority - b.priority);
  }

  /**
   * Main method: Try to generate text with automatic fallback
   */
  async generateWithFallback(
    primaryApiKey: string,
    primaryProvider: ProviderType = 'gemini',
    prompt: string,
    options: GeminiRequestOptions = {},
    onFallback?: (from: ProviderType, to: ProviderType, error: string) => void
  ): Promise<ProviderResponse> {
    
    // Try primary provider (Gemini) with user's key
    if (primaryApiKey && primaryProvider === 'gemini') {
      try {
        const genAI = new GoogleGenerativeAI(primaryApiKey.trim());
        const config: GenerationConfig = {
          temperature: options.temperature ?? 0.7,
          maxOutputTokens: options.maxOutputTokens ?? 2048,
        };
        const model = genAI.getGenerativeModel({
          model: options.model || 'gemini-1.5-flash',
          generationConfig: config,
        });
        
        const result = await model.generateContent(prompt);
        const response = await result.response;
        const text = response.text();
        
        return {
          text,
          provider: 'gemini',
          model: options.model || 'gemini-1.5-flash',
        };
      } catch (error: any) {
        const err: ProviderError = {
          provider: 'gemini',
          error: error?.message || 'Unknown error',
          statusCode: error?.status,
          isRetryable: error?.status === 429 || error?.message?.includes('quota'),
        };
        
        // If not retryable, throw immediately
        if (!isRetryableError(err)) {
          throw error;
        }
        
        // Otherwise, fall through to free providers
        onFallback?.('gemini', 'pollinations', err.error);
      }
    }

    // Build the fallback chain: free providers without keys first, then providers with keys
    const availableProviders = this.getAvailableProviders();
    const providers: Array<{ type: ProviderType; apiKey: string; config: ProviderConfig }> = [];
    
    // 1. Add free no-key providers first (mlvoca, pollinations)
    for (const config of availableProviders) {
      const key = this.userApiKeys[config.type];
      // Include free providers even without a key
      if (!key?.trim() && (config.type === 'mlvoca' || config.type === 'pollinations')) {
        providers.push({ type: config.type, apiKey: '', config });
      }
    }
    
    // 2. Add providers with user-configured API keys
    for (const config of availableProviders) {
      const key = this.userApiKeys[config.type];
      if (key?.trim()) {
        providers.push({ type: config.type, apiKey: key, config });
      }
    }

    // Try each provider in order
    const errors: ProviderError[] = [];
    
    for (const { type, apiKey, config } of providers) {
      try {
        let response: ProviderResponse;
        
        switch (type) {
          case 'mlvoca':
            response = await callMlvoCa(config.model, prompt, options);
            break;
          case 'pollinations':
            response = await callPollinations(config.model, prompt, options, apiKey);
            break;
          case 'groq':
            response = await callGroq(apiKey, options.model || 'gemini-1.5-flash', prompt, options);
            break;
          case 'huggingface':
            response = await callHuggingFace(apiKey, options.model || 'gemini-1.5-flash', prompt, options);
            break;
          case 'together':
            response = await callTogether(apiKey, options.model || 'gemini-1.5-flash', prompt, options);
            break;
          case 'openrouter':
            response = await callOpenRouter(apiKey, options.model || 'gemini-1.5-flash', prompt, options);
            break;
          default:
            continue;
        }
        
        this.lastUsedProvider = type;
        return response;
        
      } catch (error: any) {
        const err: ProviderError = {
          provider: type,
          error: error?.message || error?.error?.message || 'Unknown error',
          statusCode: error?.statusCode || error?.status,
          isRetryable: isRetryableError(error),
        };
        
        errors.push(err);
        
        // Mark provider as failed temporarily
        this.failedProviders.add(type);
        
        // Notify about fallback
        const nextProvider = providers.find(p => p.type !== type);
        if (nextProvider) {
          onFallback?.(type, nextProvider.type, err.error);
        }
        
        // If error is not retryable, don't try other providers
        if (!err.isRetryable) {
          break;
        }
      }
    }

    // All providers failed
    const errorSummary = errors.map(e => `${e.provider}: ${e.error}`).join('; ');
    throw new Error(`All LLM providers failed: ${maskSecrets(errorSummary)}`);
  }

  /**
   * Get last successful provider
   */
  getLastProvider(): ProviderType | null {
    return this.lastUsedProvider;
  }

  /**
   * Check which providers have valid keys configured
   */
  getConfiguredProviders(): ProviderType[] {
    return Object.entries(this.userApiKeys)
      .filter(([, key]) => key?.trim())
      .map(([type]) => type as ProviderType);
  }
}

// Singleton instance
export const providerManager = new ProviderManager();