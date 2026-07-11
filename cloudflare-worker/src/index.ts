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
  // Optional: Cache API Key for authentication
  CACHE_API_KEY?: string;
}

const DEFAULT_TTL = 1800; // 30 minutes in seconds

/**
 * CORS headers for all responses
 */
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-API-Key',
  'Access-Control-Max-Age': '86400',
};

// Simple hash for cache key validation
function isValidKey(key: string): boolean {
  return /^[a-z0-9_]{1,128}$/.test(key);
}

/**
 * Simple authentication check
 */
function validateAuth(request: Request, env: Env): boolean {
  if (!env.CACHE_API_KEY) {
    return true; // No auth required if secret not set
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

    // Authentication check for all operations except preflight
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

    // CACHE_TTL_SECONDS and DEFAULT_TTL are already in seconds.
    const ttlSeconds = parseInt(env.CACHE_TTL_SECONDS || String(DEFAULT_TTL), 10);

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
        let body: unknown;
        try {
          body = await request.json();
        } catch {
          return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          });
        }

        try {
          const metadata = {
            createdAt: Date.now(),
            ttlSeconds,
          };
          // Store data with metadata. expirationTtl must be in seconds and at least 60.
          await env.CACHE.put(key, JSON.stringify({ metadata, data: body }), {
            expirationTtl: Math.max(60, ttlSeconds),
          });
          return new Response(JSON.stringify({ ok: true, key }), {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          });
        } catch (error) {
          return new Response(
            JSON.stringify({ error: 'Cache storage failed', details: error instanceof Error ? error.message : 'Unknown' }),
            {
              status: 500,
              headers: { ...corsHeaders, 'Content-Type': 'application/json' },
            },
          );
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
