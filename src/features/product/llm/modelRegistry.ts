/**
 * Model Registry & Cloudflare Worker Routing
 * 
 * Defines available models and their routing configuration.
 * Supports Cloudflare Workers AI Gateway as primary router with 30-min caching.
 * 
 * ROUTING PRIORITY:
 * 1. Cloudflare FREE (Qwen Coder 32B) - DEFAULT
 * 2. Cloudflare FREE (other models)
 * 3. Paid: MiniMax > Codestral > GPT-4 > Claude
 */

export type ModelProvider = 
  | 'cloudflare-worker'  // Cloudflare Workers AI Gateway (PRIMARY - Free, Cached)
  | 'openrouter'        // OpenRouter aggregator (Paid)
  | 'groq'              // Groq (ultra low latency)
  | 'huggingface'       // HuggingFace Inference
  | 'together'          // Together AI
  | 'gemini'            // Google Gemini
  | 'minimax'           // MiniMax AI
  | 'optional-user-keys' // OpenHands Bridge
  | 'local-safe';       // Local safe inference

export interface ModelInfo {
  id: string;
  name: string;
  provider: ModelProvider;
  /** Context window size in tokens */
  contextWindow?: number;
  /** Whether this model requires user API key */
  requiresUserKey: boolean;
  /** Priority for auto-selection (higher = preferred) */
  priority: number;
  /** Supported capabilities */
  capabilities: ('chat' | 'completion' | 'embedding' | 'vision' | 'code')[];
  /** Cloudflare model identifier */
  cloudflareModelId?: string;
  /** Specialized for code generation */
  codeSpecialized?: boolean;
}

export interface ModelRoutingConfig {
  primaryProvider: ModelProvider;
  fallbackProviders: ModelProvider[];
  preferLowLatency: boolean;
}

/**
 * Caching configuration for Cloudflare responses
 * 30 minutes inactivity timeout
 */
export const CACHE_CONFIG = {
  /** Cache duration in milliseconds (30 minutes) */
  durationMs: 30 * 60 * 1000,
  /** Inactivity timeout before cache invalidation */
  inactivityTimeoutMs: 30 * 60 * 1000,
  /** Enable response caching */
  enabled: true,
  /** Cache key prefix */
  prefix: 'sovereign-llm-cache-',
};

/**
 * Available models in Sovereign Studio
 * PRIORITY: Free Cloudflare models first, then paid models
 */
export const MODEL_REGISTRY: ModelInfo[] = [
  // === CLOUDFLARE WORKER (FREE - DEFAULT, CACHED 30 MIN) ===
  {
    id: '@cf/qwen/qwen2.5-coder-32b',
    name: 'Qwen Coder 32B ⭐ DEFAULT',
    provider: 'cloudflare-worker',
    contextWindow: 32000,
    requiresUserKey: false,
    priority: 100, // HIGHEST - Free, code-specialized, cached
    capabilities: ['chat', 'completion', 'code'],
    cloudflareModelId: '@cf/qwen/qwen2.5-coder-32b',
    codeSpecialized: true,
  },
  {
    id: 'deepseek-v3',
    name: 'DeepSeek V3 (Free)',
    provider: 'cloudflare-worker',
    contextWindow: 64000,
    requiresUserKey: false,
    priority: 80,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'deepseek-v3',
  },
  {
    id: 'llama-3.3-70b',
    name: 'Llama 3.3 70B (Free)',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 75,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'llama-3.3-70b-instruct',
  },
  {
    id: 'mistral-large',
    name: 'Mistral Large (Free)',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 70,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'mistral-large',
  },
  {
    id: 'qwen-2.5-72b',
    name: 'Qwen 2.5 72B (Free)',
    provider: 'cloudflare-worker',
    contextWindow: 32768,
    requiresUserKey: false,
    priority: 68,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'qwen2.5-72b-instruct',
  },
  {
    id: '@cf/meta/llama-3.1-8b-instruct',
    name: 'Llama 3.1 8B (Fast Free)',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 60,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: '@cf/meta/llama-3.1-8b-instruct',
  },
  {
    id: 'cerabras/zai-glm-4.7',
    name: 'Cerebras ZAI-GLM (Free)',
    provider: 'cloudflare-worker',
    contextWindow: 32000,
    requiresUserKey: false,
    priority: 55,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'zai-glm-4.7',
  },

  // === PAID PROVIDERS (When user has API key) ===
  
  // MiniMax (Paid - Strong Chinese model)
  {
    id: 'minimax/minimax-2.7b',
    name: 'MiniMax 2.7B (Paid)',
    provider: 'minimax',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 90,
    capabilities: ['chat', 'completion', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'minimax/abab6',
    name: 'MiniMax ABAB 6 (Paid)',
    provider: 'minimax',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 85,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'minimax/abab6.5s',
    name: 'MiniMax ABAB 6.5S (Paid)',
    provider: 'minimax',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 82,
    capabilities: ['chat', 'completion'],
  },

  // OpenRouter - Codestral (Paid - Code specialized)
  {
    id: 'codestral:latest',
    name: 'Codestral (Paid - Code)',
    provider: 'openrouter',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 88,
    capabilities: ['chat', 'completion', 'code'],
    codeSpecialized: true,
  },

  // OpenRouter - GPT-4 (Paid)
  {
    id: 'openai/gpt-4o',
    name: 'GPT-4o (Paid)',
    provider: 'openrouter',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 86,
    capabilities: ['chat', 'completion', 'vision', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'openai/gpt-4-turbo',
    name: 'GPT-4 Turbo (Paid)',
    provider: 'openrouter',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 84,
    capabilities: ['chat', 'completion', 'vision', 'code'],
    codeSpecialized: true,
  },

  // OpenRouter - Claude (Paid - Best for code)
  {
    id: 'anthropic/claude-sonnet-4-20250514',
    name: 'Claude Sonnet 4 (Paid - Best)',
    provider: 'openrouter',
    contextWindow: 200000,
    requiresUserKey: true,
    priority: 95,
    capabilities: ['chat', 'completion', 'vision', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'anthropic/claude-3.5-sonnet',
    name: 'Claude 3.5 Sonnet (Paid)',
    provider: 'openrouter',
    contextWindow: 200000,
    requiresUserKey: true,
    priority: 92,
    capabilities: ['chat', 'completion', 'vision', 'code'],
    codeSpecialized: true,
  },

  // OpenRouter - Other code models (Paid)
  {
    id: 'deepseek/deepseek-coder-v2',
    name: 'DeepSeek Coder V2 (Paid)',
    provider: 'openrouter',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 87,
    capabilities: ['chat', 'completion', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'qwen/qwen-2.5-coder-32b',
    name: 'Qwen 2.5 Coder 32B (Paid OpenRouter)',
    provider: 'openrouter',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 83,
    capabilities: ['chat', 'completion', 'code'],
    codeSpecialized: true,
  },

  // Groq (Paid - Ultra low latency)
  {
    id: 'groq/llama-3.3-70b',
    name: 'Groq Llama 3.3 70B (Fast Paid)',
    provider: 'groq',
    contextWindow: 8192,
    requiresUserKey: true,
    priority: 65,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'groq/llama-3.1-70b',
    name: 'Groq Llama 3.1 70B (Paid)',
    provider: 'groq',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 62,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'groq/mixtral-8x7b',
    name: 'Groq Mixtral 8x7B (Fast Paid)',
    provider: 'groq',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 60,
    capabilities: ['chat', 'completion'],
  },

  // User-key providers
  {
    id: 'optional-user-keys',
    name: 'Primary Bridge (Custom Key)',
    provider: 'optional-user-keys',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 50,
    capabilities: ['chat', 'completion', 'embedding', 'vision', 'code'],
  },
  {
    id: 'gemini',
    name: 'Google Gemini (Paid)',
    provider: 'gemini',
    contextWindow: 2000000,
    requiresUserKey: true,
    priority: 45,
    capabilities: ['chat', 'completion', 'vision'],
  },
  
  // No-key providers (Fallback)
  {
    id: 'mlvoca',
    name: 'MLVoca (No-Key)',
    provider: 'optional-user-keys',
    requiresUserKey: false,
    priority: 10,
    capabilities: ['chat'],
  },
  {
    id: 'pollinations',
    name: 'Pollinations (No-Key)',
    provider: 'optional-user-keys',
    requiresUserKey: false,
    priority: 5,
    capabilities: ['chat'],
  },
  {
    id: 'local-safe',
    name: 'Local Analysis',
    provider: 'local-safe',
    requiresUserKey: false,
    priority: 1,
    capabilities: ['chat'],
  },
];

/**
 * Default routing configuration
 * Cloudflare FREE is PRIMARY - Qwen Coder 32B default
 * Paid models as fallback when user has API key
 */
export const DEFAULT_ROUTING_CONFIG: ModelRoutingConfig = {
  primaryProvider: 'cloudflare-worker', // FREE - Qwen Coder 32B
  fallbackProviders: ['minimax', 'openrouter', 'groq', 'gemini'],
  preferLowLatency: true,
};

/**
 * Get model by ID
 */
export function getModelById(id: string): ModelInfo | undefined {
  return MODEL_REGISTRY.find(m => m.id === id);
}

/**
 * Get models by provider
 */
export function getModelsByProvider(provider: ModelProvider): ModelInfo[] {
  return MODEL_REGISTRY.filter(m => m.provider === provider);
}

/**
 * Get only code-specialized models
 */
export function getCodeSpecializedModels(): ModelInfo[] {
  return MODEL_REGISTRY.filter(m => m.codeSpecialized);
}

/**
 * Get best available model for routing
 * Prioritizes: free cloudflare > paid with key
 */
export function getBestAvailableModel(
  userKeyConfigured: boolean,
  config: ModelRoutingConfig = DEFAULT_ROUTING_CONFIG
): ModelInfo {
  // Priority order based on routing config
  const priorityOrder: ModelProvider[] = [
    config.primaryProvider,
    ...config.fallbackProviders,
  ];

  for (const provider of priorityOrder) {
    const models = getModelsByProvider(provider);
    
    // Filter by key availability
    const available = models.filter(m => 
      !m.requiresUserKey || (m.requiresUserKey && userKeyConfigured)
    );

    if (available.length > 0) {
      // Sort by priority and return best
      available.sort((a, b) => b.priority - a.priority);
      return available[0];
    }
  }

  // Fallback to local-safe
  return getModelById('local-safe')!;
}

/**
 * Get best code-generation model
 */
export function getBestCodeModel(userKeyConfigured: boolean): ModelInfo {
  const codeModels = getCodeSpecializedModels();
  
  // Filter by availability
  const available = codeModels.filter(m => 
    !m.requiresUserKey || (m.requiresUserKey && userKeyConfigured)
  );

  if (available.length > 0) {
    available.sort((a, b) => b.priority - a.priority);
    return available[0];
  }

  return getBestAvailableModel(userKeyConfigured);
}

/**
 * Get Cloudflare model ID for a given model
 */
export function getCloudflareModelId(modelId: string): string | undefined {
  const model = getModelById(modelId);
  return model?.cloudflareModelId;
}

/**
 * Check if model supports a capability
 */
export function modelSupportsCapability(modelId: string, capability: ModelInfo['capabilities'][number]): boolean {
  const model = getModelById(modelId);
  return model?.capabilities.includes(capability) ?? false;
}
