/**
 * LLM Provider Manager - Free LLM API Fallback System
 * Auto-switches between providers when primary fails
 * 
 * Supported Free Tier Providers:
 * - MLVOCA (NO API key required, default)
 * - Groq (LPU inference, very fast, generous free tier)
 * - HuggingFace (Inference API, many free models)
 * - Together AI (free tier with many models)
 * - OpenRouter (aggregator with free models)
 * - Google Gemini (requires API key)
 */

import { GoogleGenerativeAI, GenerationConfig } from '@google/generative-ai';
import type { 
  ProviderType, 
  ProviderConfig, 
  ProviderResponse, 
  ProviderError,
  AwarenessSyncResult 
} from '../../types';
import { maskSecrets } from '../../utils/crypto';

// Free Provider Configurations (Priority Order)
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
    type: 'groq',
    baseURL: 'https://api.groq.com/openai/v1',
    model: 'llama-3.1-8b-instant',
    supportsStreaming: true,
    maxTokens: 8192,
    priority: 1,
  },
  {
    type: 'huggingface',
    baseURL: 'https://api-inference.huggingface.co/models',
    model: 'meta-llama/Llama-3.2-1B-Instruct',
    supportsStreaming: false,
    maxTokens: 2048,
    priority: 2,
  },
  {
    type: 'together',
    baseURL: 'https://api.together.xyz/v1',
    model: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
    supportsStreaming: true,
    maxTokens: 4096,
    priority: 3,
  },
  {
    type: 'openrouter',
    baseURL: 'https://openrouter.ai/api/v1',
    model: 'meta-llama/llama-3.1-8b-instruct:free',
    supportsStreaming: true,
    maxTokens: 8192,
    priority: 4,
  },
];

export interface RequestOptions {
  model?: string;
  temperature?: number;
  topK?: number;
  topP?: number;
  maxOutputTokens?: number;
  stopSequences?: string[];
}

/**
 * Checks if error is retryable
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
  const modelMap: Record<string, Partial<Record<ProviderType, string>>> = {
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
  
  if (modelMap[model]?.[targetProvider]) {
    return modelMap[model][targetProvider]!;
  }
  
  const defaults: Partial<Record<ProviderType, string>> = {
    gemini: model,
    mlvoca: 'deepseek-r1:1.5b',
    groq: 'llama-3.1-8b-instant',
    huggingface: 'meta-llama/Llama-3.2-1B-Instruct',
    together: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
    openrouter: 'meta-llama/llama-3.1-8b-instruct:free',
  };
  
  return defaults[targetProvider] || 'deepseek-r1:1.5b';
}

// ============================================================
// MLVOCA - Free No-Key API (Default Provider)
// ============================================================
export async function callMlvoCa(
  model: string, 
  prompt: string, 
  options: RequestOptions = {}
): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'mlvoca');
  
  try {
    const response = await fetch('https://mlvoca.com/api/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: mappedModel,
        prompt: prompt,
        stream: false,
        options: {
          temperature: options.temperature ?? 0.7,
        },
        keep_alive: '5m',
      }),
    });
    
    if (!response.ok) {
      const errorText = await response.text().catch(() => `HTTP ${response.status}`);
      throw {
        provider: 'mlvoca' as ProviderType,
        error: maskSecrets(errorText || `HTTP ${response.status}`),
        statusCode: response.status,
        isRetryable: response.status >= 500 || response.status === 429,
      };
    }
    
    const data = await response.json();
    return {
      text: data.response || '',
      provider: 'mlvoca',
      model: mappedModel,
    };
  } catch (error: any) {
    throw {
      provider: 'mlvoca' as ProviderType,
      error: maskSecrets(error?.message || String(error)),
      statusCode: error?.statusCode,
      isRetryable: error?.isRetryable ?? true,
    };
  }
}

// ============================================================
// Groq - Free Tier
// ============================================================
export async function callGroq(
  apiKey: string, 
  model: string, 
  prompt: string, 
  options: RequestOptions
): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'groq');
  
  try {
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
        error: maskSecrets(errorData.error?.message || `HTTP ${response.status}`),
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
  } catch (error: any) {
    throw {
      provider: 'groq' as ProviderType,
      error: maskSecrets(error?.error?.message || error?.message || String(error)),
      statusCode: error?.statusCode,
      isRetryable: error?.isRetryable ?? true,
    };
  }
}

// ============================================================
// HuggingFace
// ============================================================
export async function callHuggingFace(
  apiKey: string, 
  model: string, 
  prompt: string, 
  options: RequestOptions
): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'huggingface');
  const url = `https://api-inference.huggingface.co/models/${mappedModel}`;
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`;
  }
  
  try {
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
      const errorText = await response.text().catch(() => `HTTP ${response.status}`);
      throw {
        provider: 'huggingface' as ProviderType,
        error: maskSecrets(errorText || `HTTP ${response.status}`),
        statusCode: response.status,
        isRetryable: response.status >= 500 || response.status === 429,
      };
    }
    
    const data = await response.json();
    const text = Array.isArray(data) ? data[0]?.generated_text : data.generated_text || '';
    
    return {
      text,
      provider: 'huggingface',
      model: mappedModel,
    };
  } catch (error: any) {
    throw {
      provider: 'huggingface' as ProviderType,
      error: maskSecrets(error?.message || String(error)),
      statusCode: error?.statusCode,
      isRetryable: error?.isRetryable ?? true,
    };
  }
}

// ============================================================
// Together AI
// ============================================================
export async function callTogether(
  apiKey: string, 
  model: string, 
  prompt: string, 
  options: RequestOptions
): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'together');
  
  try {
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
        error: maskSecrets(errorData.error?.message || `HTTP ${response.status}`),
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
  } catch (error: any) {
    throw {
      provider: 'together' as ProviderType,
      error: maskSecrets(error?.error?.message || error?.message || String(error)),
      statusCode: error?.statusCode,
      isRetryable: error?.isRetryable ?? true,
    };
  }
}

// ============================================================
// OpenRouter
// ============================================================
export async function callOpenRouter(
  apiKey: string, 
  model: string, 
  prompt: string, 
  options: RequestOptions
): Promise<ProviderResponse> {
  const mappedModel = mapModelForProvider(model, 'openrouter');
  
  try {
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
        error: maskSecrets(errorData.error?.message || `HTTP ${response.status}`),
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
  } catch (error: any) {
    throw {
      provider: 'openrouter' as ProviderType,
      error: maskSecrets(error?.error?.message || error?.message || String(error)),
      statusCode: error?.statusCode,
      isRetryable: error?.isRetryable ?? true,
    };
  }
}

// ============================================================
// Gemini Service
// ============================================================
async function withRetry<T>(fn: () => Promise<T>, retries = 2, delayMs = 2000): Promise<T> {
  try {
    return await fn();
  } catch (error: any) {
    const is429 = error?.status === 429 || 
                  error?.message?.includes('429') || 
                  error?.message?.includes('quota') || 
                  error?.message?.includes('RESOURCE_EXHAUSTED');
    if (is429 && retries > 0) {
      // Simple delay without Promise
      const start = Date.now();
      while (Date.now() - start < delayMs) {}
      return withRetry(fn, retries - 1, delayMs * 2);
    }
    throw error;
  }
}

export const geminiService = {
  async generateText(apiKey: string, prompt: string, options: RequestOptions = {}) {
    if (!apiKey?.trim()) {
      throw new Error('Kein Gemini API-Key angegeben.');
    }
    
    const genAI = new GoogleGenerativeAI(apiKey.trim());
    const config: GenerationConfig = {
      temperature: options.temperature ?? 0.7,
      topK: options.topK,
      topP: options.topP,
      maxOutputTokens: options.maxOutputTokens ?? 2048,
      stopSequences: options.stopSequences,
    };
    const model = genAI.getGenerativeModel({
      model: options.model || 'gemini-1.5-flash',
      generationConfig: config,
    });
    
    return withRetry(async () => {
      const result = await model.generateContent(prompt);
      const response = await result.response;
      return response.text();
    });
  },

  async generateFromMedia(apiKey: string, prompt: string, parts: any[], options: RequestOptions = {}) {
    if (!apiKey?.trim()) {
      throw new Error('Kein Gemini API-Key angegeben.');
    }
    
    const genAI = new GoogleGenerativeAI(apiKey.trim());
    const model = genAI.getGenerativeModel({
      model: options.model || 'gemini-1.5-flash',
    });
    
    return withRetry(async () => {
      const result = await model.generateContent([prompt, ...parts]);
      const response = await result.response;
      return response.text();
    });
  },
};

// ============================================================
// ProviderManager - Main class for automatic provider fallback
// ============================================================
export class ProviderManager {
  private userApiKeys: Partial<Record<ProviderType, string>> = {};
  private lastUsedProvider: ProviderType | null = null;
  private failedProviders: Set<ProviderType> = new Set();

  setApiKey(provider: ProviderType, key: string): void {
    this.userApiKeys[provider] = key;
    this.failedProviders.delete(provider);
  }

  resetFailedProviders(): void {
    this.failedProviders.clear();
  }

  getAvailableProviders(): ProviderConfig[] {
    return FREE_PROVIDERS
      .filter(p => !this.failedProviders.has(p.type))
      .sort((a, b) => a.priority - b.priority);
  }

  getConfiguredProviders(): ProviderType[] {
    return Object.entries(this.userApiKeys)
      .filter(([, key]) => key?.trim())
      .map(([type]) => type as ProviderType);
  }

  getLastProvider(): ProviderType | null {
    return this.lastUsedProvider;
  }

  /**
   * Main method: Try to generate text with automatic fallback
   */
  async generateWithFallback(
    primaryApiKey: string,
    primaryProvider: ProviderType = 'gemini',
    prompt: string,
    options: RequestOptions = {},
    onFallback?: (from: ProviderType, to: ProviderType, error: string) => void
  ): Promise<ProviderResponse> {
    // Try mlvoca first (free, no key required!)
    try {
      const response = await callMlvoCa(options.model || 'gemini-1.5-flash', prompt, options);
      this.lastUsedProvider = 'mlvoca';
      return response;
    } catch (mlvocaError) {
      // mlvoca failed, continue to next
    }

    // Try Gemini if key is provided
    if (primaryApiKey?.trim()) {
      try {
        const text = await geminiService.generateText(primaryApiKey, prompt, {
          model: options.model || 'gemini-1.5-flash',
          temperature: options.temperature,
          maxOutputTokens: options.maxOutputTokens,
        });
        this.lastUsedProvider = 'gemini';
        return { text, provider: 'gemini', model: options.model || 'gemini-1.5-flash' };
      } catch (geminiError) {
      onFallback?.('gemini', 'groq', maskSecrets((geminiError as Error)?.message || 'Unknown error'));
      }
    }

    // Try providers with user keys
    const providers = this.getAvailableProviders();
    
    for (const config of providers) {
      const key = this.userApiKeys[config.type];
      if (!key?.trim()) continue;

      try {
        let response: ProviderResponse;
        
        switch (config.type) {
          case 'groq':
            response = await callGroq(key, options.model || 'gemini-1.5-flash', prompt, options);
            break;
          case 'huggingface':
            response = await callHuggingFace(key, options.model || 'gemini-1.5-flash', prompt, options);
            break;
          case 'together':
            response = await callTogether(key, options.model || 'gemini-1.5-flash', prompt, options);
            break;
          case 'openrouter':
            response = await callOpenRouter(key, options.model || 'gemini-1.5-flash', prompt, options);
            break;
          default:
            continue;
        }
        
        this.lastUsedProvider = config.type;
        return response;
      } catch (error: any) {
        this.failedProviders.add(config.type);
        const nextConfig = providers.find(p => p.type !== config.type);
        if (nextConfig) {
          onFallback?.(config.type, nextConfig.type, maskSecrets(error?.message || 'Unknown error'));
        }
        
        if (!isRetryableError(error)) {
          break;
        }
      }
    }

    throw new Error('Alle LLM Provider sind fehlgeschlagen.');
  }
}

// Singleton instance
export const providerManager = new ProviderManager();

// ============================================================
// Awareness Sync - Analyze GitHub Repository
// ============================================================
export async function runAwarenessSync(
  geminiApiKey: string,
  repoFiles: Array<{ path: string; type: string; size?: number }>,
  repoUrl: string,
  fallbackProviders: {
    groqKey?: string;
    hfKey?: string;
    togetherKey?: string;
    openrouterKey?: string;
  } = {},
  model: string = 'gemini-1.5-flash',
  onProviderSwitch?: (from: ProviderType, to: ProviderType, error: string) => void
): Promise<AwarenessSyncResult> {
  const filePaths = repoFiles
    .filter((f) => f.type === 'blob')
    .slice(0, 80)
    .map((f) => f.path)
    .join('\n');

  const prompt = `Du bist ein erfahrener Software-Architekt. Analysiere das folgende GitHub-Repository und gib eine strukturierte Übersicht zurück.

Repository: ${repoUrl}

Dateiliste (Auszug):
${filePaths}

Antworte auf Deutsch in diesem exakten Format:

ZUSAMMENFASSUNG:
[2-3 Sätze was dieses Projekt ist und macht]

TECHNOLOGIEN:
[Komma-getrennte Liste der erkannten Technologien, Frameworks, Tools]

STRUKTUR:
[Kurze Beschreibung der Ordnerstruktur und Architektur in 2-3 Sätzen]

VERBESSERUNGSVORSCHLÄGE:
- [Vorschlag 1]
- [Vorschlag 2]
- [Vorschlag 3]`;

  let rawText: string = '';
  let usedProvider: ProviderType = 'mlvoca';

  // Priority 1: Try mlvoca (free, no API key required!)
  try {
    const response = await callMlvoCa(model, prompt, {
      temperature: 0.3,
      maxOutputTokens: 1024,
    });
    rawText = response.text;
    usedProvider = 'mlvoca';
  } catch (mlvocaError: any) {
    onProviderSwitch?.('mlvoca', 'gemini', maskSecrets(mlvocaError?.message || 'MLVOCA failed'));
  }

  // Priority 2: Try Gemini if key is provided
  if (!rawText && geminiApiKey?.trim()) {
    try {
      rawText = await geminiService.generateText(geminiApiKey, prompt, {
        model,
        temperature: 0.3,
        maxOutputTokens: 1024,
      });
      usedProvider = 'gemini';
    } catch (geminiError: any) {
      onProviderSwitch?.('gemini', 'groq', maskSecrets(geminiError?.message || 'Gemini failed'));
    }
  }

  // Priority 3: Try Groq
  if (!rawText && fallbackProviders.groqKey?.trim()) {
    try {
      const response = await callGroq(fallbackProviders.groqKey, model, prompt, {
        temperature: 0.3,
        maxOutputTokens: 1024,
      });
      rawText = response.text;
      usedProvider = 'groq';
    } catch (err: any) {
      onProviderSwitch?.('groq', 'huggingface', maskSecrets(err?.message || 'Groq failed'));
    }
  }

  // Priority 4: Try HuggingFace
  if (!rawText && fallbackProviders.hfKey?.trim()) {
    try {
      const response = await callHuggingFace(fallbackProviders.hfKey, model, prompt, {
        temperature: 0.3,
        maxOutputTokens: 1024,
      });
      rawText = response.text;
      usedProvider = 'huggingface';
    } catch (err: any) {
      onProviderSwitch?.('huggingface', 'together', maskSecrets(err?.message || 'HF failed'));
    }
  }

  // Priority 5: Try Together AI
  if (!rawText && fallbackProviders.togetherKey?.trim()) {
    try {
      const response = await callTogether(fallbackProviders.togetherKey, model, prompt, {
        temperature: 0.3,
        maxOutputTokens: 1024,
      });
      rawText = response.text;
      usedProvider = 'together';
    } catch (err: any) {
      onProviderSwitch?.('together', 'openrouter', maskSecrets(err?.message || 'Together failed'));
    }
  }

  if (!rawText) {
    throw new Error('Alle AI-Provider sind fehlgeschlagen. Bitte versuche es später erneut.');
  }

  const summary = extractSection(rawText, 'ZUSAMMENFASSUNG');
  const techLine = extractSection(rawText, 'TECHNOLOGIEN');
  const structure = extractSection(rawText, 'STRUKTUR');
  const suggestionsText = extractSection(rawText, 'VERBESSERUNGSVORSCHLÄGE');

  const technologies = techLine
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);

  const suggestions = suggestionsText
    .split('\n')
    .map((s) => s.replace(/^[-•*]\s*/, '').trim())
    .filter(Boolean);

  return { 
    summary, 
    technologies, 
    structure, 
    suggestions, 
    rawText 
  };
}

function extractSection(text: string, heading: string): string {
  const regex = new RegExp(`${heading}:\\s*([\\s\\S]*?)(?=\\n[A-ZÄÖÜ]+:|$)`, 'i');
  const match = text.match(regex);
  return match ? match[1].trim() : '';
}

// ============================================================
// Provider Info for UI Display
// ============================================================
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
    model: 'gemini-1.5-flash',
    hasKey: false,
    isFree: false,
    description: 'Primary provider. Requires Google AI API key.',
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
  {
    type: 'openrouter',
    name: 'OpenRouter',
    model: 'llama-3.1-8b-instruct:free',
    hasKey: false,
    isFree: true,
    description: 'Aggregates many providers. Has free models.',
  },
  {
    type: 'mlvoca',
    name: 'MLVOCA (Free)',
    model: 'deepseek-r1:1.5b',
    hasKey: false,
    isFree: true,
    description: 'No API key required. Default provider.',
  },
];