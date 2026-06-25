/**
 * Model Registry & Cloudflare Worker Routing
 * 
 * Defines available models and their routing configuration.
 * Supports Cloudflare Workers AI Gateway as primary router.
 */

export type ModelProvider = 
  | 'cloudflare-worker'  // Cloudflare Workers AI Gateway (PRIORITY)
  | 'openrouter'        // OpenRouter aggregator
  | 'groq'              // Groq (low latency)
  | 'huggingface'       // HuggingFace Inference
  | 'together'          // Together AI
  | 'gemini'            // Google Gemini
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
  capabilities: ('chat' | 'completion' | 'embedding' | 'vision')[];
  /** Cloudflare model identifier */
  cloudflareModelId?: string;
}

export interface ModelRoutingConfig {
  primaryProvider: ModelProvider;
  fallbackProviders: ModelProvider[];
  preferLowLatency: boolean;
}

/**
 * Available models in Sovereign Studio
 */
export const MODEL_REGISTRY: ModelInfo[] = [
  // === CLOUDFLARE WORKER (PRIORITY - Primary Router) ===
  {
    id: 'gpt-oss-120b',
    name: 'GPT-OSS 120B',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 100, // HIGHEST - Primary model via Cloudflare
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'gpt-oss-120b',
  },
  {
    id: 'llama-3.3-70b',
    name: 'Llama 3.3 70B',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 90,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'llama-3.3-70b-instruct',
  },
  {
    id: 'mistral-large',
    name: 'Mistral Large',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 85,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'mistral-large',
  },
  {
    id: 'qwen-2.5-72b',
    name: 'Qwen 2.5 72B',
    provider: 'cloudflare-worker',
    contextWindow: 32768,
    requiresUserKey: false,
    priority: 80,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'qwen2.5-72b-instruct',
  },
  {
    id: 'deepseek-v3',
    name: 'DeepSeek V3',
    provider: 'cloudflare-worker',
    contextWindow: 64000,
    requiresUserKey: false,
    priority: 75,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'deepseek-v3',
  },
  // Cerebras as fallback
  {
    id: 'cerabras/zai-glm-4.7',
    name: 'Cerebras ZAI-GLM',
    provider: 'cloudflare-worker',
    contextWindow: 32000,
    requiresUserKey: false,
    priority: 60,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'zai-glm-4.7',
  },
  
  // === USER-KEY PROVIDERS (Secondary) ===
  {
    id: 'optional-user-keys',
    name: 'Primary Bridge',
    provider: 'optional-user-keys',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 50,
    capabilities: ['chat', 'completion', 'embedding', 'vision'],
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    provider: 'gemini',
    contextWindow: 2000000,
    requiresUserKey: true,
    priority: 40,
    capabilities: ['chat', 'completion', 'vision'],
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    provider: 'openrouter',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 30,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'groq',
    name: 'Groq',
    provider: 'groq',
    contextWindow: 8192,
    requiresUserKey: true,
    priority: 25,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'huggingface',
    name: 'HuggingFace',
    provider: 'huggingface',
    contextWindow: 4096,
    requiresUserKey: true,
    priority: 20,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'together',
    name: 'Together AI',
    provider: 'together',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 15,
    capabilities: ['chat', 'completion'],
  },
  // === NO-KEY PROVIDERS ===
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
 * Cloudflare Worker is PRIMARY - all traffic routes through it first
 */
export const DEFAULT_ROUTING_CONFIG: ModelRoutingConfig = {
  primaryProvider: 'cloudflare-worker',
  fallbackProviders: ['optional-user-keys', 'openrouter', 'gemini'],
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
 * Get best available model for routing
 * Prioritizes: cloudflare-worker > user-key > no-key > local
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
