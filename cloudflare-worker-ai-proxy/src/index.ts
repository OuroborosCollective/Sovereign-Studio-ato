/**
 * Sovereign LLM Proxy - Cloudflare Worker AI Router
 * 
 * Proxies requests to Cloudflare Workers AI.
 * Uses Cloudflare Service Token for authentication.
 * 
 * Usage:
 *   POST /v1/chat/completions
 *   POST /v1/embeddings
 *   Body: { "model": "@cf/meta/llama-3-8b-instruct", "messages": [...] }
 */

interface Env {
  // Cloudflare API Token for Workers AI
  CF_AI_TOKEN: string;
  
  // Cloudflare Account ID
  CF_ACCOUNT_ID: string;
  
  // Default model if not specified
  DEFAULT_MODEL?: string;
  
  // Optional: Rate limiting (requests per minute)
  RATE_LIMIT?: string;
  
  // Optional: Allowed models (comma-separated)
  ALLOWED_MODELS?: string;

  // Optional: Allowed 768-dimensional embedding models (comma-separated)
  ALLOWED_EMBEDDING_MODELS?: string;

  // Optional: Proxy API Key for authentication
  PROXY_API_KEY?: string;
}

interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

interface ChatCompletionRequest {
  model?: string;
  messages: ChatMessage[];
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
}

interface EmbeddingRequest {
  model?: string;
  input: string | string[];
}

interface EmbeddingResponse {
  object: 'list';
  data: Array<{
    object: 'embedding';
    index: number;
    embedding: number[];
  }>;
  model: string;
  usage: {
    prompt_tokens: number;
    total_tokens: number;
  };
}

interface ChatCompletionResponse {
  id: string;
  object: string;
  created: number;
  model: string;
  choices: Array<{
    index: number;
    message: ChatMessage;
    finish_reason: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

interface CloudflareAIResponse {
  result?: {
    response?: string;
    tool_calls?: unknown[];
  };
  success: boolean;
  errors?: Array<{ message: string }>;
}

interface ProviderEndpoint {
  name: string;
  url: string;
  requiresAuth: boolean;
  authHeader?: string;
}

/**
 * Provider configurations for different LLM backends
 */
const PROVIDERS: Record<string, ProviderEndpoint> = {
  cloudflare: {
    name: 'Cloudflare Workers AI',
    url: 'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}',
    requiresAuth: true,
    authHeader: 'Bearer {token}',
  },
  openrouter: {
    name: 'OpenRouter',
    url: 'https://openrouter.ai/api/v1/chat/completions',
    requiresAuth: true,
    authHeader: 'Bearer {token}',
  },
  openai: {
    name: 'OpenAI',
    url: 'https://api.openai.com/v1/chat/completions',
    requiresAuth: true,
    authHeader: 'Bearer {token}',
  },
};

/**
 * Model routing configuration
 */
const MODEL_ROUTES: Record<string, { provider: string; actualModel: string }> = {
  // Cloudflare Workers AI models - verified reachable and non-deprecated on 2026-07-03.
  // '@cf/meta/llama-3-8b-instruct' and '@cf/qwen/qwen1.5-14b-chat-awq' were removed here:
  // Cloudflare returns HTTP 410 "Model has been deprecated" for both as of this date.
  '@cf/meta/llama-3.1-8b-instruct': { provider: 'cloudflare', actualModel: '@cf/meta/llama-3.1-8b-instruct' },
  '@cf/meta/llama-3.3-70b-instruct-fp8-fast': { provider: 'cloudflare', actualModel: '@cf/meta/llama-3.3-70b-instruct-fp8-fast' },
  '@cf/mistral/mistral-7b-instruct-v0.1': { provider: 'cloudflare', actualModel: '@cf/mistral/mistral-7b-instruct-v0.1' },
  '@cf/deepseek-ai/deepseek-r1-distill-qwen-32b': { provider: 'cloudflare', actualModel: '@cf/deepseek-ai/deepseek-r1-distill-qwen-32b' },

  // Alias models for easier use
  'llama-3-8b': { provider: 'cloudflare', actualModel: '@cf/meta/llama-3.1-8b-instruct' },
  'llama-3.1-8b': { provider: 'cloudflare', actualModel: '@cf/meta/llama-3.1-8b-instruct' },
  'llama-3.3-70b': { provider: 'cloudflare', actualModel: '@cf/meta/llama-3.3-70b-instruct-fp8-fast' },
  'mistral-7b': { provider: 'cloudflare', actualModel: '@cf/mistral/mistral-7b-instruct-v0.1' },
  'qwen-14b': { provider: 'cloudflare', actualModel: '@cf/deepseek-ai/deepseek-r1-distill-qwen-32b' },
  'deepseek-r1': { provider: 'cloudflare', actualModel: '@cf/deepseek-ai/deepseek-r1-distill-qwen-32b' },

  // The Android app (primaryBridgeConfig.ts / devChatWorkerBridge.ts) currently requests these
  // exact strings. They were never registered here, so every real chat request fell through to
  // the "forward literal model string to Cloudflare" branch and Cloudflare rejected them with
  // "No route for that URI" (error 7000) - the actual root cause of "Worker offline" in the app.
  // No Cerebras/Gemini provider or secret exists in this Worker, so these route to a verified
  // working Cloudflare model instead of a fabricated Cerebras/Gemini response.
  'cerebras/gpt-oss-120b': { provider: 'cloudflare', actualModel: '@cf/meta/llama-3.3-70b-instruct-fp8-fast' },
  'cerebras/zai-glm-4.7': { provider: 'cloudflare', actualModel: '@cf/meta/llama-3.1-8b-instruct' },

  // Legacy compatibility alias (added 2026-07-03): older APK/app bundles may still send
  // "gemini-2.0-flash". There is no Gemini provider or secret configured in this Worker, so this
  // is NOT a real Gemini call - it is routed to the same verified-working Cloudflare model used
  // for "llama-3.1-8b" so old clients get a real chat response instead of a 400 model_not_found.
  'gemini-2.0-flash': { provider: 'cloudflare', actualModel: '@cf/meta/llama-3.1-8b-instruct' },
};

/**
 * CORS headers for all responses
 */
const DEFAULT_EMBEDDING_MODEL = '@cf/google/embeddinggemma-300m';
const EMBEDDING_DIMENSIONS = 768;
const MAX_EMBEDDING_INPUTS = 32;
const MAX_EMBEDDING_TEXT_CHARS = 8_000;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-API-Key, X-Sovereign-Client',
  'Access-Control-Max-Age': '86400',
};

/**
 * Simple in-memory rate limiter (per Worker instance)
 */
const rateLimitMap = new Map<string, { count: number; resetTime: number }>();

function checkRateLimit(clientId: string, limit: number): boolean {
  const now = Date.now();
  const windowMs = 60 * 1000; // 1 minute
  const record = rateLimitMap.get(clientId);
  
  if (!record || now > record.resetTime) {
    rateLimitMap.set(clientId, { count: 1, resetTime: now + windowMs });
    return true;
  }
  
  if (record.count >= limit) {
    return false;
  }
  
  record.count++;
  return true;
}

/**
 * Redacts sensitive credentials from strings.
 */
function maskSecrets(text: string): string {
  if (!text) return text;
  let masked = text;
  // GitHub
  masked = masked.replace(/(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9_]{8,100}/g, '$1_****');
  masked = masked.replace(/github_pat_[a-zA-Z0-9_]{20,200}/g, 'github_pat_****');
  // Google
  masked = masked.replace(/AIza[a-zA-Z0-9_-]{26,60}/g, 'AIza****');
  // AI keys
  masked = masked.replace(/sk-or-v1-[a-zA-Z0-9_-]{20,120}/g, 'sk-or-v1-****');
  masked = masked.replace(/sk-proj-[a-zA-Z0-9_-]{20,120}/g, 'sk-proj-****');
  masked = masked.replace(/sk-[a-zA-Z0-9_-]{20,120}/g, 'sk-****');
  masked = masked.replace(/gsk_[a-zA-Z0-9_-]{20,120}/g, 'gsk_****');
  // HuggingFace, Together AI and Pollinations AI
  masked = masked.replace(/hf_[a-zA-Z0-9]{8,100}/g, 'hf_****');
  masked = masked.replace(/together_[a-zA-Z0-9]{8,100}/g, 'together_****');
  masked = masked.replace(/pollinations_[a-zA-Z0-9]{8,100}/g, 'pollinations_****');
  // Bearer
  masked = masked.replace(/Bearer\s+[a-zA-Z0-9._~+/-]+=*/gi, 'Bearer ****');
  // Label-based
  masked = masked.replace(
    /(["']?)(password|passwd|token|secret|api[_-]?key|access[_-]?token)\1(\s*[:=]\s*)["']?[a-zA-Z0-9_@#$%^&*.\-~+/=]+["']?/gi,
    '$1$2$1$3****',
  );
  return masked;
}

function getClientId(request: Request): string {
  return request.headers.get('CF-Connecting-IP') || 
         request.headers.get('X-Forwarded-For') || 
         'unknown';
}

/**
 * Convert messages to Cloudflare Workers AI format
 */
function formatForCloudflare(messages: ChatMessage[]): { messages: ChatMessage[] } {
  return { messages };
}

/**
 * Calculate approximate token count (rough estimate)
 */
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

function calculateUsage(messages: ChatMessage[], response: string) {
  const promptTokens = messages.reduce((sum, msg) => sum + estimateTokens(msg.content), 0);
  const completionTokens = estimateTokens(response);
  return {
    prompt_tokens: promptTokens,
    completion_tokens: completionTokens,
    total_tokens: promptTokens + completionTokens,
  };
}

/**
 * Create OpenAI-compatible response
 */
function createChatResponse(
  model: string,
  content: string,
  messages: ChatMessage[]
): ChatCompletionResponse {
  return {
    id: `chatcmpl-${crypto.randomUUID()}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        message: {
          role: 'assistant',
          content,
        },
        finish_reason: 'stop',
      },
    ],
    usage: calculateUsage(messages, content),
  };
}

/**
 * Create streaming response (SSE format)
 */
function createStreamResponse(model: string, content: string): ReadableStream {
  const encoder = new TextEncoder();
  const words = content.split(' ');
  
  return new ReadableStream({
    async start(controller) {
      // Initial chunk
      controller.enqueue(encoder.encode(`data: ${JSON.stringify({
        id: `chatcmpl-${crypto.randomUUID()}`,
        object: 'chat.completion.chunk',
        created: Math.floor(Date.now() / 1000),
        model,
        choices: [{
          index: 0,
          delta: { role: 'assistant' },
          finish_reason: null,
        }],
      })}\n\n`));
      
      // Content chunks
      for (let i = 0; i < words.length; i++) {
        const chunk = words[i] + (i < words.length - 1 ? ' ' : '');
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({
          id: `chatcmpl-${crypto.randomUUID()}`,
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model,
          choices: [{
            index: 0,
            delta: { content: chunk },
            finish_reason: null,
          }],
        })}\n\n`));
        
        // Small delay to simulate streaming
        await new Promise(resolve => setTimeout(resolve, 20));
      }
      
      // Final chunk
      controller.enqueue(encoder.encode(`data: ${JSON.stringify({
        id: `chatcmpl-${crypto.randomUUID()}`,
        object: 'chat.completion.chunk',
        created: Math.floor(Date.now() / 1000),
        model,
        choices: [{
          index: 0,
          delta: {},
          finish_reason: 'stop',
        }],
      })}\n\n`));
      
      controller.enqueue(encoder.encode('data: [DONE]\n\n'));
      controller.close();
    },
  });
}

/**
 * Call Cloudflare Workers AI
 */
async function callCloudflareAI(
  env: Env,
  model: string,
  messages: ChatMessage[],
  temperature?: number,
  maxTokens?: number
): Promise<string> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai/run/${model}`;
  
  const payload = {
    messages,
    ...(temperature !== undefined && { temperature }),
    ...(maxTokens !== undefined && { max_tokens: maxTokens }),
  };
  
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.CF_AI_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Cloudflare AI error ${response.status}: ${errorText}`);
  }
  
  const data = await response.json() as CloudflareAIResponse;
  
  if (!data.success) {
    const errorMessage = data.errors?.map(e => e.message).join(', ') || 'Unknown error';
    throw new Error(`Cloudflare AI failed: ${errorMessage}`);
  }
  
  return data.result?.response || '';
}

function allowedEmbeddingModels(env: Env): string[] {
  const configured = (env.ALLOWED_EMBEDDING_MODELS || '')
    .split(',')
    .map(model => model.trim())
    .filter(Boolean);
  return configured.length > 0 ? configured : [DEFAULT_EMBEDDING_MODEL];
}

function validateEmbeddingRequest(body: unknown, env: Env):
  | { valid: true; model: string; texts: string[] }
  | { valid: false; error: string } {
  if (!body || typeof body !== 'object') {
    return { valid: false, error: 'Request body must be an object' };
  }
  const request = body as Partial<EmbeddingRequest>;
  const rawInputs = typeof request.input === 'string' ? [request.input] : request.input;
  if (!Array.isArray(rawInputs) || rawInputs.length === 0) {
    return { valid: false, error: 'input must be a non-empty string or string array' };
  }
  if (rawInputs.length > MAX_EMBEDDING_INPUTS) {
    return { valid: false, error: `At most ${MAX_EMBEDDING_INPUTS} inputs are allowed` };
  }
  const texts: string[] = [];
  for (const value of rawInputs) {
    if (typeof value !== 'string' || !value.trim()) {
      return { valid: false, error: 'Every embedding input must be a non-empty string' };
    }
    if (value.length > MAX_EMBEDDING_TEXT_CHARS) {
      return { valid: false, error: `Embedding input exceeds ${MAX_EMBEDDING_TEXT_CHARS} characters` };
    }
    texts.push(value.trim());
  }
  const model = String(request.model || DEFAULT_EMBEDDING_MODEL).trim();
  if (!allowedEmbeddingModels(env).includes(model)) {
    return { valid: false, error: `Embedding model ${model} is not allowed` };
  }
  return { valid: true, model, texts };
}

async function callCloudflareEmbeddings(
  env: Env,
  model: string,
  texts: string[],
): Promise<number[][]> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai/run/${model}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.CF_AI_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text: texts }),
  });
  if (!response.ok) {
    throw new Error(`Cloudflare embedding error ${response.status}: ${await response.text()}`);
  }
  const payload = await response.json() as {
    success?: boolean;
    result?: { data?: unknown; embeddings?: unknown };
    errors?: Array<{ message?: string }>;
  };
  if (!payload.success) {
    const reason = payload.errors?.map(item => item.message || 'Unknown error').join(', ') || 'Unknown error';
    throw new Error(`Cloudflare embedding failed: ${reason}`);
  }
  const rawVectors = payload.result?.data ?? payload.result?.embeddings;
  if (!Array.isArray(rawVectors) || rawVectors.length !== texts.length) {
    throw new Error('Cloudflare embedding count did not match input count');
  }
  return rawVectors.map((rawVector, index) => {
    if (!Array.isArray(rawVector) || rawVector.length !== EMBEDDING_DIMENSIONS) {
      throw new Error(`Embedding ${index} did not contain ${EMBEDDING_DIMENSIONS} dimensions`);
    }
    const vector = rawVector.map(value => Number(value));
    if (vector.some(value => !Number.isFinite(value))) {
      throw new Error(`Embedding ${index} contained a non-finite value`);
    }
    return vector;
  });
}

async function handleEmbeddings(request: Request, env: Env): Promise<Response> {
  try {
    const rateLimit = env.RATE_LIMIT ? parseInt(env.RATE_LIMIT, 10) : 60;
    if (!checkRateLimit(getClientId(request), rateLimit)) {
      return new Response(JSON.stringify({
        error: { message: 'Rate limit exceeded', type: 'rate_limit_error', code: 'rate_limit_exceeded' },
      }), { status: 429, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    }

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({
        error: { message: 'Invalid JSON', type: 'invalid_request_error' },
      }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    }

    const validation = validateEmbeddingRequest(body, env);
    if (!validation.valid) {
      return new Response(JSON.stringify({
        error: { message: validation.error, type: 'invalid_request_error' },
      }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    }

    const vectors = await callCloudflareEmbeddings(env, validation.model, validation.texts);
    const promptTokens = validation.texts.reduce((sum, text) => sum + estimateTokens(text), 0);
    const result: EmbeddingResponse = {
      object: 'list',
      data: vectors.map((embedding, index) => ({ object: 'embedding', index, embedding })),
      model: validation.model,
      usage: { prompt_tokens: promptTokens, total_tokens: promptTokens },
    };
    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Embedding error:', error);
    return new Response(JSON.stringify({
      error: {
        message: error instanceof Error ? maskSecrets(error.message) : 'Internal server error',
        type: 'server_error',
      },
    }), { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
  }
}

/**
 * Validate request payload
 */
function validateChatRequest(body: unknown): { valid: boolean; error?: string; data?: ChatCompletionRequest } {
  if (!body || typeof body !== 'object') {
    return { valid: false, error: 'Request body must be an object' };
  }
  
  const req = body as Partial<ChatCompletionRequest>;
  
  if (!Array.isArray(req.messages) || req.messages.length === 0) {
    return { valid: false, error: 'messages must be a non-empty array' };
  }
  
  for (const msg of req.messages) {
    if (!msg || typeof msg !== 'object') {
      return { valid: false, error: 'Each message must be an object' };
    }
    const message = msg as ChatMessage;
    if (!['system', 'user', 'assistant'].includes(message.role)) {
      return { valid: false, error: 'Message role must be system, user, or assistant' };
    }
    if (typeof message.content !== 'string') {
      return { valid: false, error: 'Message content must be a string' };
    }
  }
  
  if (req.temperature !== undefined && (typeof req.temperature !== 'number' || req.temperature < 0 || req.temperature > 2)) {
    return { valid: false, error: 'temperature must be a number between 0 and 2' };
  }
  
  if (req.max_tokens !== undefined && (typeof req.max_tokens !== 'number' || req.max_tokens < 1 || req.max_tokens > 32000)) {
    return { valid: false, error: 'max_tokens must be a number between 1 and 32000' };
  }
  
  return { valid: true, data: req as ChatCompletionRequest };
}

/**
 * Check if model is allowed
 */
function isModelAllowed(model: string, env: Env): boolean {
  if (!env.ALLOWED_MODELS) {
    return true; // All models allowed by default
  }
  
  const allowedModels = env.ALLOWED_MODELS.split(',').map(m => m.trim());
  return allowedModels.includes(model) || allowedModels.includes(MODEL_ROUTES[model]?.actualModel);
}

/**
 * Simple authentication check
 */
function validateAuth(request: Request, env: Env): boolean {
  if (!env.PROXY_API_KEY) {
    return true; // No auth required if secret not set
  }
  const authHeader = request.headers.get('Authorization');
  const apiKeyHeader = request.headers.get('X-API-Key');
  const token = authHeader?.startsWith('Bearer ') ? authHeader.substring(7) : apiKeyHeader;
  return token === env.PROXY_API_KEY;
}

/**
 * Handle chat completions endpoint
 */
async function handleChatCompletions(request: Request, env: Env): Promise<Response> {
  try {
    // Rate limiting
    const rateLimit = env.RATE_LIMIT ? parseInt(env.RATE_LIMIT, 10) : 60;
    const clientId = getClientId(request);
    
    if (!checkRateLimit(clientId, rateLimit)) {
      return new Response(JSON.stringify({
        error: {
          message: 'Rate limit exceeded',
          type: 'rate_limit_error',
          code: 'rate_limit_exceeded',
        },
      }), {
        status: 429,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    
    // Parse request
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({
        error: {
          message: 'Invalid JSON',
          type: 'invalid_request_error',
        },
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    
    // Validate request
    const validation = validateChatRequest(body);
    if (!validation.valid) {
      return new Response(JSON.stringify({
        error: {
          message: validation.error,
          type: 'invalid_request_error',
        },
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    
    const chatRequest = validation.data!;
    const requestedModel = chatRequest.model || env.DEFAULT_MODEL || '@cf/meta/llama-3.1-8b-instruct';
    
    // Check model allowed
    if (!isModelAllowed(requestedModel, env)) {
      return new Response(JSON.stringify({
        error: {
          message: `Model ${requestedModel} is not allowed`,
          type: 'invalid_request_error',
          code: 'model_not_allowed',
        },
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    
    // Resolve model route. Only pass a model through unmapped when it is itself a literal
    // Cloudflare Workers AI id ('@cf/...') - previously *any* unrecognized string (e.g. a client
    // requesting an alias that was never registered here) was silently forwarded as-is and
    // Cloudflare rejected it with a generic 400 "No route for that URI", which looked like a
    // network failure to the app instead of a clear "unknown model" error.
    const knownRoute = MODEL_ROUTES[requestedModel];
    if (!knownRoute && !requestedModel.startsWith('@cf/')) {
      return new Response(JSON.stringify({
        error: {
          message: `Unknown model "${requestedModel}". Use one of: ${Object.keys(MODEL_ROUTES).join(', ')}`,
          type: 'invalid_request_error',
          code: 'model_not_found',
        },
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    const route = knownRoute || { provider: 'cloudflare', actualModel: requestedModel };
    
    // Currently only Cloudflare is implemented
    if (route.provider !== 'cloudflare') {
      return new Response(JSON.stringify({
        error: {
          message: `Provider ${route.provider} is not yet configured`,
          type: 'invalid_request_error',
          code: 'provider_not_configured',
        },
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    
    // Call AI provider
    const aiResponse = await callCloudflareAI(
      env,
      route.actualModel,
      chatRequest.messages,
      chatRequest.temperature,
      chatRequest.max_tokens
    );
    
    // Return streaming or regular response
    if (chatRequest.stream) {
      return new Response(createStreamResponse(requestedModel, aiResponse), {
        headers: {
          ...corsHeaders,
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }
    
    return new Response(JSON.stringify(createChatResponse(
      requestedModel,
      aiResponse,
      chatRequest.messages
    )), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
    
  } catch (error) {
    console.error('Chat completion error:', error);
    return new Response(JSON.stringify({
      error: {
        message: error instanceof Error ? maskSecrets(error.message) : 'Internal server error',
        type: 'server_error',
      },
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
}

/**
 * Handle models list endpoint
 */
function handleModels(env: Env): Response {
  const models = Object.keys(MODEL_ROUTES)
    .filter(model => isModelAllowed(model, env))
    .map(id => ({
      id,
      object: 'model',
      created: 1686935002,
      owned_by: MODEL_ROUTES[id].provider,
    }));
  
  return new Response(JSON.stringify({
    object: 'list',
    data: models,
  }), {
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

/**
 * Handle health check endpoint
 */
function handleHealth(env: Env): Response {
  const configured = !!(env.CF_AI_TOKEN && env.CF_ACCOUNT_ID);
  
  return new Response(JSON.stringify({
    status: configured ? 'healthy' : 'not_configured',
    service: 'sovereign-llm-proxy',
    version: '1.1.0',
    configured,
    providers: {
      cloudflare: configured,
      embeddings: configured,
    },
    models: Object.keys(MODEL_ROUTES).length,
    embeddingModel: DEFAULT_EMBEDDING_MODEL,
    embeddingDimensions: EMBEDDING_DIMENSIONS,
    timestamp: new Date().toISOString(),
  }), {
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

/**
 * Handle root endpoint with API documentation
 */
function handleRoot(): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sovereign LLM Proxy</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 800px;
      margin: 0 auto;
      padding: 40px 20px;
      line-height: 1.6;
      background: #0f172a;
      color: #e2e8f0;
    }
    h1 { color: #38bdf8; }
    h2 { color: #818cf8; margin-top: 2rem; }
    code {
      background: #1e293b;
      padding: 2px 6px;
      border-radius: 4px;
      color: #fbbf24;
    }
    pre {
      background: #1e293b;
      padding: 16px;
      border-radius: 8px;
      overflow-x: auto;
    }
    .endpoint {
      border-left: 4px solid #38bdf8;
      padding-left: 16px;
      margin: 16px 0;
    }
  </style>
</head>
<body>
  <h1>🧠 Sovereign LLM Proxy</h1>
  <p>OpenAI-compatible API proxy for Cloudflare Workers AI.</p>
  
  <h2>Endpoints</h2>
  <div class="endpoint">
    <h3>POST /v1/chat/completions</h3>
    <p>OpenAI-compatible chat completions endpoint.</p>
    <pre><code>{
  "model": "llama-3-8b",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000
}</code></pre>
  </div>
  
  <div class="endpoint">
    <h3>POST /v1/embeddings</h3>
    <p>OpenAI-compatible 768-dimensional text embeddings endpoint.</p>
    <pre><code>{
  "model": "@cf/google/embeddinggemma-300m",
  "input": ["Knowledge text"]
}</code></pre>
  </div>

  <div class="endpoint">
    <h3>GET /v1/models</h3>
    <p>List available models.</p>
  </div>
  
  <div class="endpoint">
    <h3>GET /health</h3>
    <p>Health check endpoint.</p>
  </div>
  
  <h2>Available Models</h2>
  <ul>
    <li><code>llama-3-8b</code> - Meta Llama 3 8B Instruct</li>
    <li><code>llama-3.1-8b</code> - Meta Llama 3.1 8B Instruct</li>
    <li><code>mistral-7b</code> - Mistral 7B Instruct</li>
    <li><code>gemma-7b</code> - Google Gemma 7B IT</li>
    <li><code>qwen-14b</code> - Qwen 1.5 14B Chat AWQ</li>
    <li><code>deepseek-r1</code> - DeepSeek R1 Distill Qwen 32B</li>
  </ul>
</body>
</html>`;
  
  return new Response(html, {
    headers: { ...corsHeaders, 'Content-Type': 'text/html' },
  });
}

/**
 * Main Worker export
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }
    
    // Route requests
    if (url.pathname === '/' || url.pathname === '') {
      return handleRoot();
    }
    
    if (url.pathname === '/health') {
      return handleHealth(env);
    }
    
    if (url.pathname === '/v1/models' && request.method === 'GET') {
      if (!validateAuth(request, env)) {
        return new Response(JSON.stringify({ error: { message: 'Unauthorized', type: 'invalid_request_error' } }), {
          status: 401,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }
      return handleModels(env);
    }
    
    if (url.pathname === '/v1/embeddings' && request.method === 'POST') {
      if (!validateAuth(request, env)) {
        return new Response(JSON.stringify({ error: { message: 'Unauthorized', type: 'invalid_request_error' } }), {
          status: 401,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }
      return handleEmbeddings(request, env);
    }

    if (url.pathname === '/v1/chat/completions' && request.method === 'POST') {
      if (!validateAuth(request, env)) {
        return new Response(JSON.stringify({ error: { message: 'Unauthorized', type: 'invalid_request_error' } }), {
          status: 401,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }
      return handleChatCompletions(request, env);
    }
    
    return new Response(JSON.stringify({
      error: {
        message: 'Not found',
        type: 'not_found_error',
      },
    }), {
      status: 404,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  },
};
