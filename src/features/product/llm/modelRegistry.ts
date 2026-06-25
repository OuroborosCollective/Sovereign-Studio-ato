/**
 * Model Registry & Cloudflare Worker Routing
 * 
 * Defines available models and their routing configuration.
 * Supports Cloudflare Workers AI Gateway as primary router.
 * 
 * RECOMMENDED MODELS FOR GITHUB CODE GENERATION:
 * - Claude (via OpenRouter) - Best for code
 * - MiniMax 2.7 (via OpenRouter) - Strong Chinese model
 * - GPT-4o (via OpenRouter) - Strong general
 * - DeepSeek Coder (via Cloudflare) - Specialized for code
 * - Qwen 2.5 Coder (via Cloudflare) - Specialized for code
 */

export type ModelProvider = 
  | 'cloudflare-worker'  // Cloudflare Workers AI Gateway
  | 'openrouter'        // OpenRouter aggregator (BEST for code)
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
 * Available models in Sovereign Studio
 * PRIORITY: Code-specialized models first
 */
export const MODEL_REGISTRY: ModelInfo[] = [
  // === OPENROUTER (BEST for Code - requires user key) ===
  {
    id: 'anthropic/claude-sonnet-4-20250514',
    name: 'Claude Sonnet 4 (Code-Optimized)',
    provider: 'openrouter',
    contextWindow: 200000,
    requiresUserKey: true,
    priority: 95,
    capabilities: ['chat', 'completion', 'vision', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'anthropic/claude-3.5-sonnet',
    name: 'Claude 3.5 Sonnet',
    provider: 'openrouter',
    contextWindow: 200000,
    requiresUserKey: true,
    priority: 90,
    capabilities: ['chat', 'completion', 'vision', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'openai/gpt-4o',
    name: 'GPT-4o (Code-Optimized)',
    provider: 'openrouter',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 85,
    capabilities: ['chat', 'completion', 'vision', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'openai/gpt-4-turbo',
    name: 'GPT-4 Turbo',
    provider: 'openrouter',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 80,
    capabilities: ['chat', 'completion', 'vision', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'deepseek/deepseek-coder-v2',
    name: 'DeepSeek Coder V2 (Code-Specialized)',
    provider: 'openrouter',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 88,
    capabilities: ['chat', 'completion', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'qwen/qwen-2.5-coder-32b',
    name: 'Qwen 2.5 Coder 32B',
    provider: 'openrouter',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 82,
    capabilities: ['chat', 'completion', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'codestral:latest',
    name: 'Codestral (Code-Specialized)',
    provider: 'openrouter',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 86,
    capabilities: ['chat', 'completion', 'code'],
    codeSpecialized: true,
  },

  // === MINIMAX (Strong Chinese model) ===
  {
    id: 'minimax/minimax-2.7b',
    name: 'MiniMax 2.7B (Fast)',
    provider: 'minimax',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 75,
    capabilities: ['chat', 'completion', 'code'],
    codeSpecialized: true,
  },
  {
    id: 'minimax/abab6',
    name: 'MiniMax ABAB 6 (Balanced)',
    provider: 'minimax',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 72,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'minimax/abab6.5s',
    name: 'MiniMax ABAB 6.5S (Speed)',
    provider: 'minimax',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 70,
    capabilities: ['chat', 'completion'],
  },

  // === CLOUDFLARE WORKER (Free tier, good for general) ===
  {
    id: 'deepseek-v3',
    name: 'DeepSeek V3',
    provider: 'cloudflare-worker',
    contextWindow: 64000,
    requiresUserKey: false,
    priority: 70,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'deepseek-v3',
  },
  {
    id: 'llama-3.3-70b',
    name: 'Llama 3.3 70B',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 65,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'llama-3.3-70b-instruct',
  },
  {
    id: 'mistral-large',
    name: 'Mistral Large',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 60,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'mistral-large',
  },
  {
    id: 'qwen-2.5-72b',
    name: 'Qwen 2.5 72B',
    provider: 'cloudflare-worker',
    contextWindow: 32768,
    requiresUserKey: false,
    priority: 55,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'qwen2.5-72b-instruct',
  },
  {
    id: '@cf/qwen/qwen2.5-coder-32b',
    name: 'Qwen Coder 32B (Cloudflare)',
    provider: 'cloudflare-worker',
    contextWindow: 32000,
    requiresUserKey: false,
    priority: 75, // Higher because code-specialized AND free
    capabilities: ['chat', 'completion', 'code'],
    cloudflareModelId: '@cf/qwen/qwen2.5-coder-32b',
    codeSpecialized: true,
  },
  {
    id: '@cf/meta/llama-3.1-8b-instruct',
    name: 'Llama 3.1 8B (Fast)',
    provider: 'cloudflare-worker',
    contextWindow: 128000,
    requiresUserKey: false,
    priority: 45,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: '@cf/meta/llama-3.1-8b-instruct',
  },
  {
    id: 'cerabras/zai-glm-4.7',
    name: 'Cerebras ZAI-GLM',
    provider: 'cloudflare-worker',
    contextWindow: 32000,
    requiresUserKey: false,
    priority: 40,
    capabilities: ['chat', 'completion'],
    cloudflareModelId: 'zai-glm-4.7',
  },
  
  // === GROQ (Ultra low latency - requires user key) ===
  {
    id: 'groq/llama-3.3-70b',
    name: 'Groq Llama 3.3 70B (Ultra Fast)',
    provider: 'groq',
    contextWindow: 8192,
    requiresUserKey: true,
    priority: 50,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'groq/mixtral-8x7b',
    name: 'Groq Mixtral 8x7B (Fast)',
    provider: 'groq',
    contextWindow: 32000,
    requiresUserKey: true,
    priority: 45,
    capabilities: ['chat', 'completion'],
  },
  {
    id: 'groq/llama-3.1-70b',
    name: 'Groq Llama 3.1 70B',
    provider: 'groq',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 48,
    capabilities: ['chat', 'completion'],
  },

  // === USER-KEY PROVIDERS ===
  {
    id: 'optional-user-keys',
    name: 'Primary Bridge (Custom)',
    provider: 'optional-user-keys',
    contextWindow: 128000,
    requiresUserKey: true,
    priority: 35,
    capabilities: ['chat', 'completion', 'embedding', 'vision', 'code'],
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    provider: 'gemini',
    contextWindow: 2000000,
    requiresUserKey: true,
    priority: 30,
    capabilities: ['chat', 'completion', 'vision'],
  },
  
  // === NO-KEY PROVIDERS (Free) ===
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
 * OpenRouter (code-optimized) is PRIMARY for best code generation
 */
export const DEFAULT_ROUTING_CONFIG: ModelRoutingConfig = {
  primaryProvider: 'openrouter',
  fallbackProviders: ['minimax', 'cloudflare-worker', 'groq', 'gemini'],
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
 * Prioritizes: code-specialized > user-key > no-key > local
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
