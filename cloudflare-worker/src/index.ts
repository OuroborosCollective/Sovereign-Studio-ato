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
}

const DEFAULT_TTL = 1800; // 30 minutes in seconds

// Simple hash for cache key validation
function isValidKey(key: string): boolean {
  return /^[a-z0-9_]{1,128}$/.test(key);
}

// JSON parse with error handling
function safeJsonParse<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    // Health check endpoint
    if (path === '/health') {
      return new Response(JSON.stringify({ ok: true, timestamp: Date.now() }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Cache operations
    const cacheMatch = path.match(/^\/cache\/([a-z0-9_]+)$/);
    if (!cacheMatch) {
      return new Response(JSON.stringify({ error: 'Invalid path' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const key = cacheMatch[1];
    if (!isValidKey(key)) {
      return new Response(JSON.stringify({ error: 'Invalid cache key' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const ttl = parseInt(env.CACHE_TTL_SECONDS || String(DEFAULT_TTL), 10) * 1000;

    switch (request.method) {
      case 'GET': {
        const cached = await env.CACHE.get(key, 'json');
        if (!cached) {
          return new Response(JSON.stringify({ hit: false }), {
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ hit: true, data: cached }), {
          headers: { 'Content-Type': 'application/json' },
        });
      }

      case 'PUT': {
        try {
          const body = await request.json();
          const metadata = {
            createdAt: Date.now(),
            ttl,
          };
          // Store data with metadata
          await env.CACHE.put(key, JSON.stringify({ metadata, data: body }), {
            expirationTtl: Math.floor(ttl / 1000),
          });
          return new Response(JSON.stringify({ ok: true, key }), {
            headers: { 'Content-Type': 'application/json' },
          });
        } catch {
          return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
            status: 400,
            headers: { 'Content-Type': 'application/json' },
          });
        }
      }

      case 'DELETE': {
        await env.CACHE.delete(key);
        return new Response(JSON.stringify({ ok: true, key }), {
          headers: { 'Content-Type': 'application/json' },
        });
      }

      default:
        return new Response(JSON.stringify({ error: 'Method not allowed' }), {
          status: 405,
          headers: { 'Content-Type': 'application/json' },
        });
    }
  },
};
