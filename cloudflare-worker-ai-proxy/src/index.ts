/**
 * Sovereign LLM Proxy - Cloudflare Worker AI Router
 * 
 * Proxies requests to Cloudflare Workers AI.
 * Uses Cloudflare Service Token for authentication.
 * 
 * Usage:
 *   POST /v1/chat/completions
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

interface ChatCompletionResponse {
  id: string;
  object: string;
  created: number;
  model: string;
  choices: Array<{
    index: number;
    message: {
      role: string;
      content: string;
    };
    finish_reason: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

// Rate limiting store (in-memory for demo; use KV for production)
const rateLimitStore = new Map<string, { count: number; resetTime: number }>();

/**
 * Get rate limit config
 */
function getRateLimit(env: Env): { requests: number; windowMs: number } {
  const config = env.RATE_LIMIT?.split(':') ?? ['100', '60000'];
  return {
    requests: parseInt(config[0], 10),
    windowMs: parseInt(config[1] ?? '60000', 10)
  };
}

/**
 * Check rate limit for a client (using IP or fallback)
 */
function checkRateLimit(clientIp: string, env: Env): { allowed: boolean; remaining: number; resetIn: number } {
  const { requests, windowMs } = getRateLimit(env);
  const now = Date.now();
  
  const clientData = rateLimitStore.get(clientIp);
  
  if (!clientData || now > clientData.resetTime) {
    rateLimitStore.set(clientIp, { count: 1, resetTime: now + windowMs });
    return { allowed: true, remaining: requests - 1, resetIn: windowMs };
  }
  
  if (clientData.count >= requests) {
    return { 
      allowed: false, 
      remaining: 0, 
      resetIn: clientData.resetTime - now 
    };
  }
  
  clientData.count++;
  return { 
    allowed: true, 
    remaining: requests - clientData.count, 
    resetIn: clientData.resetTime - now 
  };
}

/**
 * Check if model is allowed
 */
function isModelAllowed(model: string, env: Env): boolean {
  if (!env.ALLOWED_MODELS) return true;
  
  const allowed = env.ALLOWED_MODELS.split(',').map(m => m.trim());
  return allowed.includes(model);
}

/**
 * Convert OpenAI-style request to Cloudflare AI format
 */
function convertToCFAIFormat(request: ChatCompletionRequest, model: string): {
  messages: ChatMessage[];
  model: string;
} {
  return {
    messages: request.messages,
    model: model || '@cf/meta/llama-3-8b-instruct'
  };
}

/**
 * Convert Cloudflare AI response to OpenAI-style format
 */
function convertToOpenAIFormat(
  cfResponse: any, 
  model: string, 
  requestId: string
): ChatCompletionResponse {
  return {
    id: requestId,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model: model,
    choices: [
      {
        index: 0,
        message: {
          role: 'assistant',
          content: cfResponse.response || cfResponse.result?.response || ''
        },
        finish_reason: 'stop'
      }
    ],
    usage: {
      prompt_tokens: cfResponse.usage?.prompt_tokens || 0,
      completion_tokens: cfResponse.usage?.completion_tokens || 0,
      total_tokens: (cfResponse.usage?.prompt_tokens || 0) + (cfResponse.usage?.completion_tokens || 0)
    }
  };
}

/**
 * Generate a request ID
 */
function generateRequestId(): string {
  return `chatcmpl-${Date.now().toString(36)}${Math.random().toString(36).substring(2, 9)}`;
}

export default {
  async fetch(request: Request, env: Env, _ctx: unknown): Promise<Response> {
    const startTime = Date.now();
    
    // Only handle POST requests
    if (request.method !== 'POST') {
      return new Response(
        JSON.stringify({ error: { message: 'Method not allowed', type: 'invalid_request_error' } }),
        { status: 405, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Get client IP for rate limiting
    const clientIp = request.headers.get('CF-Connecting-IP') || 
                     request.headers.get('X-Forwarded-For')?.split(',')[0] || 
                     'unknown';
    
    // Check rate limit
    const rateLimit = checkRateLimit(clientIp, env);
    if (!rateLimit.allowed) {
      return new Response(
        JSON.stringify({ 
          error: { 
            message: 'Rate limit exceeded', 
            type: 'rate_limit_error',
            retry_after: Math.ceil(rateLimit.resetIn / 1000)
          } 
        }),
        { 
          status: 429, 
          headers: { 
            'Content-Type': 'application/json',
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': String(Math.ceil(rateLimit.resetIn / 1000)),
            'Retry-After': String(Math.ceil(rateLimit.resetIn / 1000))
          } 
        }
      );
    }

    try {
      // Parse request body
      const body: ChatCompletionRequest = await request.json();
      
      // Determine model
      const model = body.model || env.DEFAULT_MODEL || '@cf/meta/llama-3-8b-instruct';
      
      // Validate model
      if (!isModelAllowed(model, env)) {
        return new Response(
          JSON.stringify({ 
            error: { 
              message: `Model '${model}' is not allowed`, 
              type: 'invalid_request_error' 
            } 
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        );
      }

      // Validate messages
      if (!body.messages || !Array.isArray(body.messages) || body.messages.length === 0) {
        return new Response(
          JSON.stringify({ 
            error: { 
              message: 'messages is required and must be a non-empty array', 
              type: 'invalid_request_error' 
            } 
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        );
      }

      // Convert to Cloudflare AI format
      const cfRequest = convertToCFAIFormat(body, model);
      
      // Build Cloudflare AI API URL
      const cfApiUrl = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai/run/${model}`;
      
      // Forward request to Cloudflare AI
      const cfResponse = await fetch(cfApiUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.CF_AI_TOKEN}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          messages: cfRequest.messages
        })
      });

      const duration = Date.now() - startTime;
      
      if (!cfResponse.ok) {
        const errorBody = await cfResponse.text();
        console.error(`Cloudflare AI error: ${cfResponse.status}`, errorBody);
        
        return new Response(
          JSON.stringify({ 
            error: { 
              message: `AI service error: ${cfResponse.status}`, 
              type: 'service_error' 
            } 
          }),
          { 
            status: 502, 
            headers: { 
              'Content-Type': 'application/json',
              'X-Response-Time': String(duration)
            } 
          }
        );
      }

      const cfResult = await cfResponse.json();
      const requestId = generateRequestId();
      
      // Convert response to OpenAI format
      const openAIResponse = convertToOpenAIFormat(cfResult, model, requestId);
      
      return new Response(
        JSON.stringify(openAIResponse),
        {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'X-Request-Id': requestId,
            'X-Response-Time': String(duration),
            'X-RateLimit-Remaining': String(rateLimit.remaining)
          }
        }
      );

    } catch (error) {
      console.error('Proxy error:', error);
      
      return new Response(
        JSON.stringify({ 
          error: { 
            message: error instanceof Error ? error.message : 'Internal proxy error', 
            type: 'internal_error' 
          } 
        }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }
  }
};