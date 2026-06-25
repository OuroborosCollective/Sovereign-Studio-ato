/**
 * LLM Response Cache with TTL support
 * 
 * Caches LLM responses to reduce API calls and improve response times.
 * Cache entries expire after 30 minutes of inactivity.
 */

import type { LlmAdapterResult } from './llmAdapter';

export interface LlmCacheEntry {
  result: LlmAdapterResult;
  createdAt: number;
  lastAccessedAt: number;
  hitCount: number;
}

export interface LlmCacheOptions {
  ttlMs?: number;        // Time to live in milliseconds (default: 30 minutes)
  maxEntries?: number;   // Maximum cache entries (default: 100)
}

/**
 * Create a new LLM cache with TTL support
 */
export function createLlmCache(options: LlmCacheOptions = {}): LlmCache {
  const ttlMs = options.ttlMs ?? 30 * 60 * 1000; // 30 minutes default
  const maxEntries = options.maxEntries ?? 100;

  const cache = new Map<string, LlmCacheEntry>();

  function generateKey(mission: string, repoPaths: string[]): string {
    // Simple hash function for cache key
    const input = `${mission}|${repoPaths.slice(0, 50).join('|')}`;
    let hash = 0;
    for (let i = 0; i < input.length; i++) {
      const char = input.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return `llm_cache_${Math.abs(hash).toString(16)}`;
  }

  function isExpired(entry: LlmCacheEntry): boolean {
    return Date.now() - entry.lastAccessedAt > ttlMs;
  }

  function evictExpired(): void {
    for (const [key, entry] of cache.entries()) {
      if (isExpired(entry)) {
        cache.delete(key);
      }
    }
  }

  function evictOldest(): void {
    if (cache.size >= maxEntries) {
      let oldestKey: string | null = null;
      let oldestTime = Infinity;
      for (const [key, entry] of cache.entries()) {
        if (entry.lastAccessedAt < oldestTime) {
          oldestTime = entry.lastAccessedAt;
          oldestKey = key;
        }
      }
      if (oldestKey) {
        cache.delete(oldestKey);
      }
    }
  }

  return {
    get(mission: string, repoPaths: string[]): LlmAdapterResult | null {
      const key = generateKey(mission, repoPaths);
      const entry = cache.get(key);

      if (!entry) {
        return null;
      }

      if (isExpired(entry)) {
        cache.delete(key);
        return null;
      }

      // Update access time and hit count
      entry.lastAccessedAt = Date.now();
      entry.hitCount += 1;

      return entry.result;
    },

    set(mission: string, repoPaths: string[], result: LlmAdapterResult): void {
      const key = generateKey(mission, repoPaths);

      // Evict expired entries and oldest if full
      evictExpired();
      evictOldest();

      cache.set(key, {
        result,
        createdAt: Date.now(),
        lastAccessedAt: Date.now(),
        hitCount: 0,
      });
    },

    invalidate(mission: string, repoPaths: string[]): void {
      const key = generateKey(mission, repoPaths);
      cache.delete(key);
    },

    clear(): void {
      cache.clear();
    },

    stats(): { size: number; hits: number; oldest: number; newest: number } {
      evictExpired(); // Clean up first

      let totalHits = 0;
      let oldest = Infinity;
      let newest = 0;

      for (const entry of cache.values()) {
        totalHits += entry.hitCount;
        if (entry.createdAt < oldest) oldest = entry.createdAt;
        if (entry.createdAt > newest) newest = entry.createdAt;
      }

      return {
        size: cache.size,
        hits: totalHits,
        oldest: cache.size > 0 ? Date.now() - oldest : 0,
        newest: cache.size > 0 ? Date.now() - newest : 0,
      };
    },
  };
}

export interface LlmCache {
  get(mission: string, repoPaths: string[]): LlmAdapterResult | null;
  set(mission: string, repoPaths: string[], result: LlmAdapterResult): void;
  invalidate(mission: string, repoPaths: string[]): void;
  clear(): void;
  stats(): { size: number; hits: number; oldest: number; newest: number };
}
