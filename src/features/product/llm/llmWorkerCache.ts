/**
 * Cloudflare Worker LLM Cache Client
 * 
 * Provides a client interface for caching LLM responses in a Cloudflare Worker.
 * Falls back to local cache when worker is unavailable.
 * 
 * Cache invalidation: entries expire after 30 minutes of inactivity.
 */

import type { LlmCache } from './llmCache';
import { createLlmCache } from './llmCache';

export interface LlmWorkerCacheConfig {
  workerUrl?: string;        // Cloudflare Worker URL (e.g., https://llm-cache.yourdomain.workers.dev)
  localCacheTtlMs?: number; // Local cache TTL when worker is unavailable
  maxLocalEntries?: number;  // Max local cache entries
}

export interface LlmWorkerCacheResult {
  ok: boolean;
  fromCache: boolean;
  providerId: string;
  latency?: number;
  error?: string;
}

/**
 * Create a hybrid cache that tries Cloudflare Worker first, falls back to local
 */
export function createLlmWorkerCache(
  config: LlmWorkerCacheConfig = {},
): LlmWorkerCache {
  const localCache = createLlmCache({
    ttlMs: config.localCacheTtlMs ?? 30 * 60 * 1000,
    maxEntries: config.maxLocalEntries ?? 100,
  });

  let workerAvailable = false;
  let lastWorkerCheck = 0;
  const WORKER_CHECK_INTERVAL = 60 * 1000; // 1 minute

  async function checkWorkerHealth(): Promise<boolean> {
    if (!config.workerUrl) return false;
    if (Date.now() - lastWorkerCheck < WORKER_CHECK_INTERVAL) return workerAvailable;

    try {
      const response = await fetch(`${config.workerUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(3000),
      });
      workerAvailable = response.ok;
    } catch {
      workerAvailable = false;
    }
    lastWorkerCheck = Date.now();
    return workerAvailable;
  }

  return {
    localCache,

    async getFromWorker(key: string): Promise<Response | null> {
      if (!config.workerUrl) return null;
      const healthy = await checkWorkerHealth();
      if (!healthy) return null;

      try {
        const response = await fetch(`${config.workerUrl}/cache/${key}`, {
          method: 'GET',
          signal: AbortSignal.timeout(5000),
        });
        if (response.ok) return response;
        return null;
      } catch {
        return null;
      }
    },

    async setInWorker(key: string, value: unknown): Promise<boolean> {
      if (!config.workerUrl) return false;
      const healthy = await checkWorkerHealth();
      if (!healthy) return false;

      try {
        const response = await fetch(`${config.workerUrl}/cache/${key}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(value),
          signal: AbortSignal.timeout(5000),
        });
        return response.ok;
      } catch {
        return false;
      }
    },

    async invalidateInWorker(key: string): Promise<boolean> {
      if (!config.workerUrl) return false;
      const healthy = await checkWorkerHealth();
      if (!healthy) return false;

      try {
        const response = await fetch(`${config.workerUrl}/cache/${key}`, {
          method: 'DELETE',
          signal: AbortSignal.timeout(5000),
        });
        return response.ok;
      } catch {
        return false;
      }
    },

    async healthCheck(): Promise<boolean> {
      return checkWorkerHealth();
    },

    getStats() {
      return {
        localStats: localCache.stats(),
        workerAvailable,
        workerUrl: config.workerUrl ?? null,
      };
    },
  };
}

export interface LlmWorkerCache {
  localCache: LlmCache;
  getFromWorker(key: string): Promise<Response | null>;
  setInWorker(key: string, value: unknown): Promise<boolean>;
  invalidateInWorker(key: string): Promise<boolean>;
  healthCheck(): Promise<boolean>;
  getStats(): { localStats: ReturnType<LlmCache['stats']>; workerAvailable: boolean; workerUrl: string | null };
}
