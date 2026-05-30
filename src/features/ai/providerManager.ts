/**
 * Provider Manager - Free LLM API Fallback System
 * Auto-switches between providers when primary fails (auth errors, quota, etc.)
 * 
 * Supported Free Tier Providers:
 * - Puter.js (puter.com) - KEYLESS, FREE, unlimited API calls to OpenAI, Claude, Gemini
 * - Groq (LPU inference, very fast, generous free tier)
 * - OpenRouter (aggregator with free models)
 * - HuggingFace (Inference API, many free models)
 * - Together AI (free tier with many models)
 */

import { GoogleGenerativeAI, GenerationConfig } from '@google/generative-ai';
import { GeminiRequestOptions } from './geminiService';

// Provider Types
export type ProviderType = 'gemini' | 'puter' | 'groq' | 'huggingface' | 'together' | 'openrouter';

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

// Free Provider Configurations - Priority order: Puter.js first (keyless), then other free providers
export const FREE_PROVIDERS: ProviderConfig[] = [
  {
    type: 'puter',
    baseURL: 'https://api.puter.com',
    model: 'gemini-2.0-flash-exp',  // Puter.js uses Gemini through their service
    supportsStreaming: false,
    maxTokens: 8192,
    priority: 0,  // HIGHEST priority - keyless!
  },
  {
    type: 'groq',
    baseURL: 'https://api.groq.com/openai/v1',
    model: 'llama-3.1-8b-instant',
    supportsStreaming: true,
    maxTokens: 8192,
    priority: 1,
  },
  {
    type: 'openrouter',
    baseURL: 'https://openrouter.ai/api/v1',
    model: 'meta-llama/llama-3.1-8b-instruct:free',
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
];

// Known free API keys (demo/public keys from providers)
const PUBLIC_FREE_KEYS: Partial<Record<ProviderType, string>> = {
  // Puter.js - KEYLESS, no API key needed!
  puter: '',
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
 * Updated to support gemini-2.0-flash as the primary model
 */
function mapModelForProvider(model: string, targetProvider: ProviderType): string {
  // Model mapping for compatibility - Updated with gemini-2.0-flash
  const modelMap: Partial<Record<string, Partial<Record<ProviderType, string>>>> = {
    'gemini-2.0-flash': {
      groq: 'llama-3.1-8b-instant',
      huggingface: 'meta-llama/Llama-3.2-1B-Instruct',
      together: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
      openrouter: 'meta-llama/llama-3.1-8b-instruct:free',
    },
    'gemini-1.5-flash': {
      groq: 'llama-3.1-8b-instant',
      huggingface: 'meta-llama/Llama-3.2-1B-Instruct',
      together: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
      openrouter: 'meta-llama/llama-3.1-8b-instruct:free',
    },
    'gemini-1.5-pro': {
      groq: 'llama-3.1-70b-versatile',
      huggingface: 'meta-llama/Llama-3.2-3B-Instruct',
      together: 'meta-llama/Llama-3.2-70B-Instruct-Turbo',
      openrouter: 'meta-llama/llama-3.1-70b-instruct:free',
    },
  };
  
  // Try direct mapping first
  if (modelMap[model]?.[targetProvider]) {
    return modelMap[model][targetProvider];
  }
  
  // For unknown models, return a sensible default for the provider
  const defaults: Partial<Record<ProviderType, string>> = {
    gemini: model,
    puter: 'gemini-2.0-flash-exp',  // Puter.js default
    groq: 'llama-3.1-8b-instant',
    huggingface: 'meta-llama/Llama-3.2-1B-Instruct',
    together: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
    openrouter: 'meta-llama/llama-3.1-8b-instruct:free',
  };
  
  return defaults[targetProvider] || 'llama-3.1-8b-instant';
}

/**
 * Maps model names for Puter.js API
 * Puter.js supports: claude-3-haiku, claude-3-sonnet, gpt-4o-mini, gemini-2.0-flash-exp, etc.
 */
function mapModelForPuter(model: string): string {
  // Map common model names to Puter.js compatible models
  const puterModelMap: Record<string, string> = {
    'gemini-2.0-flash': 'gemini-2.0-flash-exp',
    'gemini-1.5-flash': 'gemini-2.0-flash-exp',
    'gemini-2.0-flash-exp': 'gemini-2.0-flash-exp',
    'gpt-4o-mini': 'gpt-4o-mini',
    'gpt-4o': 'gpt-4o',
    'claude-3-haiku': 'claude-3-haiku-20240307',
    'claude-3-sonnet': 'claude-3-sonnet-20240229',
  };
  
  return puterModelMap[model] || 'gemini-2.0-flash-exp';
}

// Provider implementation functions
export async function callGroq(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'groq');
  
  const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: mappedModel,
      messages: [{ role: 'user', content: prompt }],
      temperature: options.temperature ?? 0.7,
      max_tokens: options.maxOutputTokens ?? 2048,
      stream: false,
    }),
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw {
      provider: 'groq' as ProviderType,
      error: errorData.error?.message || `HTTP ${response.status}`,
      statusCode: response.status,
      isRetryable: response.status === 429 || response.status >= 500,
    };
  }
  
  const data = await response.json();
  return {
    text: data.choices?.[0]?.message?.content || '',
    provider: 'groq',
    model: mappedModel,
    usage: data.usage,
  };
}

export async function callHuggingFace(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'huggingface');
  const url = `https://api-inference.huggingface.co/models/${mappedModel}`;
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`;
  }
  
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      inputs: prompt,
      parameters: {
        temperature: options.temperature ?? 0.7,
        max_new_tokens: options.maxOutputTokens ?? 2048,
      },
    }),
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw {
      provider: 'huggingface' as ProviderType,
      error: Array.isArray(errorData) ? errorData[0]?.error || `HTTP ${response.status}` : errorData.error || `HTTP ${response.status}`,
      statusCode: response.status,
      isRetryable: response.status === 429 || response.status >= 500,
    };
  }
  
  const data = await response.json();
  // HuggingFace returns array of generated texts
  const text = Array.isArray(data) ? data[0]?.generated_text || '' : data.generated_text || '';
  
  return {
    text,
    provider: 'huggingface',
    model: mappedModel,
  };
}

export async function callTogether(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'together');
  
  const response = await fetch('https://api.together.xyz/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: mappedModel,
      messages: [{ role: 'user', content: prompt }],
      temperature: options.temperature ?? 0.7,
      max_tokens: options.maxOutputTokens ?? 2048,
    }),
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw {
      provider: 'together' as ProviderType,
      error: errorData.error?.message || `HTTP ${response.status}`,
      statusCode: response.status,
      isRetryable: response.status === 429 || response.status >= 500,
    };
  }
  
  const data = await response.json();
  return {
    text: data.choices?.[0]?.message?.content || '',
    provider: 'together',
    model: mappedModel,
    usage: data.usage,
  };
}

export async function callOpenRouter(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'openrouter');
  
  const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': 'https://sovereign-studio.app',
      'X-Title': 'Sovereign Studio',
    },
    body: JSON.stringify({
      model: mappedModel,
      messages: [{ role: 'user', content: prompt }],
      temperature: options.temperature ?? 0.7,
      max_tokens: options.maxOutputTokens ?? 2048,
    }),
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw {
      provider: 'openrouter' as ProviderType,
      error: errorData.error?.message || `HTTP ${response.status}`,
      statusCode: response.status,
      isRetryable: response.status === 429 || response.status >= 500,
    };
  }
  
  const data = await response.json();
  return {
    text: data.choices?.[0]?.message?.content || '',
    provider: 'openrouter',
    model: mappedModel,
    usage: data.usage,
  };
}

/**
 * Call Puter.js API - KEYLESS, FREE, unlimited AI API calls
 * 
 * Puter.js (puter.com) provides completely free, keyless API access to:
 * - OpenAI models (gpt-4o-mini, gpt-4o, etc.)
 * - Claude models (claude-3-haiku, claude-3-sonnet, etc.)
 * - Gemini models (gemini-2.0-flash-exp, etc.)
 * 
 * This uses the browser-based Puter.js library (loaded via script tag)
 * which handles the API calls internally.
 */
export async function callPuter(apiKey: string, model: string, prompt: string, options: GeminiRequestOptions): Promise<ProviderResponse> {
  // Puter.js uses the browser's global 'puter' object
  // We need to check if it's available (loaded via index.html script tag)
  
  const puterModel = mapModelForPuter(model);
  
  // Check if puter is available in the browser
  if (typeof (window as any).puter === 'undefined') {
    throw {
      provider: 'puter' as ProviderType,
      error: 'Puter.js not loaded. Please refresh the page.',
      statusCode: 0,
      isRetryable: true,
    };
  }
  
  try {
    // Use puter.ai.chat() which returns a Promise
    const response: any = await (window as any).puter.ai.chat(prompt, {
      model: puterModel,
      temperature: options.temperature ?? 0.7,
    });
    
    // Extract the text from the response
    // Puter.js response structure: { message: { content: '...' } }
    const text = response?.message?.content || response?.text || '';
    
    return {
      text: text,
      provider: 'puter',
      model: puterModel,
    };
  } catch (error: any) {
    throw {
      provider: 'puter' as ProviderType,
      error: error?.message || 'Puter.js call failed',
      statusCode: 0,
      isRetryable: true,
    };
  }
}

/**
 * ProviderManager - Main class for automatic provider fallback
 * 
 * KEY FEATURES:
 * - Always fallback to free providers on ANY error or when no API key is provided
 * - Puter.js is the PRIMARY free fallback (KEYLESS, unlimited, free)
 * - Groq is the secondary fallback (very fast, generous free tier)
 * - OpenRouter is the tertiary fallback (has :free models)
 */
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
   * Get the effective model (fallback to gemini-2.0-flash if not specified)
   */
  private getEffectiveModel(options: GeminiRequestOptions): string {
    const model = options.model || 'gemini-2.0-flash';
    // If model starts with 'gemini', default to flash
    if (model.startsWith('gemini') && !model.includes('flash')) {
      return 'gemini-2.0-flash';
    }
    return model;
  }

  /**
   * Main method: Try to generate text with automatic fallback
   * 
   * FIXED LOGIC:
   * - If no primary key OR any error → ALWAYS fallback to free providers
   * - No key entered → immediate fallback to Puter.js (KEYLESS!)
   * - Any error (auth, quota, network, etc.) → fallback to next provider
   * - Puter.js is the PRIMARY free fallback (KEYLESS, unlimited, free)
   */
  async generateWithFallback(
    primaryApiKey: string,
    primaryProvider: ProviderType = 'gemini',
    prompt: string,
    options: GeminiRequestOptions = {},
    onFallback?: (from: ProviderType, to: ProviderType, error: string) => void
  ): Promise<ProviderResponse> {
    
    const effectiveModel = this.getEffectiveModel(options);
    let primaryError: string | null = null;

    // Try primary provider if key is provided
    if (primaryApiKey?.trim() && primaryProvider === 'gemini') {
      try {
        const genAI = new GoogleGenerativeAI(primaryApiKey.trim());
        const config: GenerationConfig = {
          temperature: options.temperature ?? 0.7,
          maxOutputTokens: options.maxOutputTokens ?? 2048,
        };
        const model = genAI.getGenerativeModel({
          model: effectiveModel,
          generationConfig: config,
        });
        
        const result = await model.generateContent(prompt);
        const response = await result.response;
        const text = response.text();
        
        // Success with primary - return immediately
        return {
          text,
          provider: 'gemini',
          model: effectiveModel,
        };
      } catch (error: any) {
        // ANY error with primary → fallback to free providers
        primaryError = error?.message || 'Unknown error';
        console.log(`🔄 Primary provider (gemini) failed: ${primaryError}`);
        // Continue to free providers - do NOT throw here
      }
    } else if (!primaryApiKey?.trim()) {
      // No key entered → immediate fallback to Puter.js (KEYLESS!)
      console.log('🔄 No API key provided → falling back to free providers (Puter.js first)');
    }

    // Get list of free providers to try (prioritized by FREE_PROVIDERS order)
    const freeProviders = this.getAvailableProviders();
    const errors: ProviderError[] = [];
    let lastError: string = primaryError || 'No primary provider';

    // Try each free provider in order (Puter.js first - KEYLESS!)
    for (const config of freeProviders) {
      // SPECIAL CASE: Puter.js does NOT require an API key!
      const requiresApiKey = config.type !== 'puter';
      const apiKey = this.userApiKeys[config.type];
      
      // Skip if API key is required but not provided
      if (requiresApiKey && !apiKey?.trim()) {
        console.log(`⏭️ Skipping ${config.type} - no API key configured`);
        continue;
      }

      try {
        let response: ProviderResponse;
        
        switch (config.type) {
          case 'puter':
            // Puter.js is KEYLESS - no API key needed!
            response = await callPuter(apiKey || '', effectiveModel, prompt, options);
            break;
          case 'groq':
            response = await callGroq(apiKey, effectiveModel, prompt, options);
            break;
          case 'openrouter':
            response = await callOpenRouter(apiKey, effectiveModel, prompt, options);
            break;
          case 'huggingface':
            response = await callHuggingFace(apiKey, effectiveModel, prompt, options);
            break;
          case 'together':
            response = await callTogether(apiKey, effectiveModel, prompt, options);
            break;
          default:
            continue;
        }
        
        this.lastUsedProvider = config.type;
        console.log(`✅ Success with ${config.type}`);
        return response;
        
      } catch (error: any) {
        const errMsg = error?.message || error?.error?.message || 'Unknown error';
        lastError = errMsg;
        
        const err: ProviderError = {
          provider: config.type,
          error: errMsg,
          statusCode: error?.statusCode || error?.status,
          isRetryable: isRetryableError(error),
        };
        
        errors.push(err);
        console.log(`❌ ${config.type} failed: ${errMsg}`);
        
        // Mark provider as failed temporarily
        this.failedProviders.add(config.type);
        
        // Find next provider to notify about fallback
        const nextProvider = freeProviders.find(p => p.type !== config.type);
        if (nextProvider) {
          onFallback?.(config.type, nextProvider.type, errMsg);
        }
        
        // Continue to next provider - we want to try ALL free options
        continue;
      }
    }

    // ALL free providers failed
    const errorSummary = errors.length > 0 
      ? errors.map(e => `${e.provider}: ${e.error}`).join('; ')
      : lastError;
    
    console.error(`💥 All LLM providers failed: ${errorSummary}`);
    throw new Error(`All LLM providers failed. Last error: ${errorSummary}`);
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