/**
 * Sovereign LLM Cache Worker
 * 
 * Cloudflare Worker for caching LLM responses.
 * - GET /health - Health check
 * - GET /cache/:key - Get cached response
 * - PUT /cache/:key - Set cached response
 * - DELETE /cache/:key - Invalidate cache entry
 */

interface Env {
  CACHE: KVNamespace;
  ANALYTICS?: AnalyticsEngineDataset;
  CACHE_TTL_SECONDS: string;
  CACHE_API_KEY?: string;
}

const DEFAULT_TTL = 1800; // 30 minutes in seconds

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-API-Key',
  'Access-Control-Max-Age': '86400',
};

// Simple hash for cache key validation
function isValidKey(key: string): boolean {
  return /^[a-z0-9_]{1,128}$/.test(key);
}

function validateAuth(request: Request, env: Env): boolean {
  if (!env.CACHE_API_KEY) {
    return true;
  }
  const authHeader = request.headers.get('Authorization');
  const apiKeyHeader = request.headers.get('X-API-Key');
  const token = authHeader?.startsWith('Bearer ') ? authHeader.substring(7) : apiKeyHeader;
  return token === env.CACHE_API_KEY;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Authenticate all operations if CACHE_API_KEY is configured
    if (!validateAuth(request, env)) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), {
        status: 401,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    // Health check endpoint
    if (path === '/health') {
      return new Response(JSON.stringify({ ok: true, timestamp: Date.now() }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Cache operations
    const cacheMatch = path.match(/^\/cache\/([a-z0-9_]+)$/);
    if (!cacheMatch) {
      return new Response(JSON.stringify({ error: 'Invalid path' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const key = cacheMatch[1];
    if (!isValidKey(key)) {
      return new Response(JSON.stringify({ error: 'Invalid cache key' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const ttl = parseInt(env.CACHE_TTL_SECONDS || String(DEFAULT_TTL), 10) * 1000;

    switch (request.method) {
      case 'GET': {
        const cached = await env.CACHE.get(key, 'json');
        if (!cached) {
          return new Response(JSON.stringify({ hit: false }), {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ hit: true, data: cached }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }

      case 'PUT': {
        try {
          const body = await request.json();
          const metadata = {
            createdAt: Date.now(),
            ttl,
          };
          // Store data with metadata, ensuring expirationTtl is at least 60 seconds
          const expirationTtl = Math.max(60, Math.floor(ttl / 1000));
          await env.CACHE.put(key, JSON.stringify({ metadata, data: body }), {
            expirationTtl,
          });
          return new Response(JSON.stringify({ ok: true, key }), {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          });
        } catch {
          return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          });
        }
      }

      case 'DELETE': {
        await env.CACHE.delete(key);
        return new Response(JSON.stringify({ ok: true, key }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }

      default:
        return new Response(JSON.stringify({ error: 'Method not allowed' }), {
          status: 405,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
    }
  },
};
