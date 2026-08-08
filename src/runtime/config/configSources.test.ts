import { describe, it, expect } from 'vitest';
import {
  hashConfigContent,
  extractSourceMetadata,
  validateRemoteSource,
  CONFIG_SOURCE_PRIORITIES,
  type ConfigSource,
} from './configSources';

describe('configSources', () => {
  describe('hashConfigContent', () => {
    it('should produce consistent hash for same content', () => {
      const content = { a: 1, b: 2 };
      const hash1 = hashConfigContent(content);
      const hash2 = hashConfigContent(content);
      expect(hash1).toBe(hash2);
    });

    it('should produce deterministic hash regardless of key order', () => {
      const content1 = { a: 1, b: 2 };
      const content2 = { b: 2, a: 1 };
      const hash1 = hashConfigContent(content1);
      const hash2 = hashConfigContent(content2);
      expect(hash1).toBe(hash2);
    });

    it('should produce different hash for different content', () => {
      const hash1 = hashConfigContent({ a: 1 });
      const hash2 = hashConfigContent({ a: 2 });
      expect(hash1).not.toBe(hash2);
    });

    it('should produce valid hex string', () => {
      const hash = hashConfigContent({ test: true });
      // Accept any valid hex string (sync function produces shorter hashes)
      expect(hash).toMatch(/^[a-f0-9]+$/);
    });
  });

  describe('extractSourceMetadata', () => {
    it('should extract content and schema hashes', () => {
      const content = { a: 1, b: 2 };
      const metadata = extractSourceMetadata(content);
      expect(metadata).toBeDefined();
      // Accept any valid hex string (sync function produces variable-length)
      expect(metadata?.contentHash).toMatch(/^[a-f0-9]+$/);
      expect(metadata?.schemaHash).toMatch(/^[a-f0-9]+$/);
    });

    it('should produce deterministic metadata', () => {
      const content1 = { a: 1, b: 2 };
      const content2 = { b: 2, a: 1 };
      const meta1 = extractSourceMetadata(content1);
      const meta2 = extractSourceMetadata(content2);
      expect(meta1).toEqual(meta2);
    });

    it('should return null for non-object values', () => {
      expect(extractSourceMetadata(null)).toBeNull();
      expect(extractSourceMetadata(undefined)).toBeNull();
      expect(extractSourceMetadata('string')).toBeNull();
      expect(extractSourceMetadata(123)).toBeNull();
    });

    it('should handle empty objects', () => {
      const metadata = extractSourceMetadata({});
      expect(metadata).toBeDefined();
      expect(metadata?.contentHash).toBeDefined();
      expect(metadata?.schemaHash).toBeDefined();
    });
  });

  describe('validateRemoteSource', () => {
    it('should reject source without origin', () => {
      const source: Partial<ConfigSource> = {
        revision: 'abc123',
        contentHash: 'hash123',
      };
      expect(validateRemoteSource(source)).toBe(false);
    });

    it('should reject source without revision', () => {
      const source: Partial<ConfigSource> = {
        origin: 'https://example.com/config',
        contentHash: 'hash123',
      };
      expect(validateRemoteSource(source)).toBe(false);
    });

    it('should reject source with unverified revision', () => {
      const source: Partial<ConfigSource> = {
        origin: 'https://example.com/config',
        revision: 'unverified',
        contentHash: 'hash123',
      };
      expect(validateRemoteSource(source)).toBe(false);
    });

    it('should reject source without content hash', () => {
      const source: Partial<ConfigSource> = {
        origin: 'https://example.com/config',
        revision: 'abc123',
      };
      expect(validateRemoteSource(source)).toBe(false);
    });

    it('should accept valid remote source', () => {
      const source: Partial<ConfigSource> = {
        origin: 'https://example.com/config',
        revision: 'abc123',
        contentHash: 'hash123',
      };
      expect(validateRemoteSource(source)).toBe(true);
    });
  });

  describe('CONFIG_SOURCE_PRIORITIES', () => {
    it('should have correct priority order', () => {
      expect(CONFIG_SOURCE_PRIORITIES.compiled).toBeLessThan(CONFIG_SOURCE_PRIORITIES.image);
      expect(CONFIG_SOURCE_PRIORITIES.image).toBeLessThan(CONFIG_SOURCE_PRIORITIES.deployment);
      expect(CONFIG_SOURCE_PRIORITIES.deployment).toBeLessThan(CONFIG_SOURCE_PRIORITIES.environment);
      expect(CONFIG_SOURCE_PRIORITIES.environment).toBeLessThan(CONFIG_SOURCE_PRIORITIES.overlay);
    });
  });
});
