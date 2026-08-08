import { describe, it, expect } from 'vitest';
import {
  resolveConfig,
  verifyConfigDrift,
  getConfigFingerprint,
  getRedactedSources,
  type ResolvedConfig,
} from './configResolver';
import type { ConfigSource } from './configSources';

function createMockSource(overrides: Partial<ConfigSource> = {}): ConfigSource {
  return {
    id: 'test-source',
    priority: 'compiled',
    revision: 'abc123',
    contentHash: 'hash123',
    schemaHash: 'schema123',
    hasSecrets: false,
    origin: 'compiled',
    ...overrides,
  };
}

describe('configResolver', () => {
  describe('resolveConfig', () => {
    it('should resolve single source', () => {
      const sources = [createMockSource({ id: 'env:api', priority: 'environment' })];
      const values = new Map([['env:api', { apiUrl: 'https://example.com' }]]);

      const result = resolveConfig(sources, values);

      expect(result.value).toEqual({ apiUrl: 'https://example.com' });
      expect(result.sourceOrder).toHaveLength(1);
      expect(result.sourceHashes).toHaveLength(1);
      expect(result.schemaHash).toBeDefined();
      expect(result.resolvedHash).toBeDefined();
      expect(result.resolvedAt).toBeDefined();
    });

    it('should merge multiple sources by priority', () => {
      const sources = [
        createMockSource({ id: 'compiled', priority: 'compiled', contentHash: 'hash1' }),
        createMockSource({ id: 'overlay', priority: 'overlay', contentHash: 'hash2' }),
      ];
      const values = new Map([
        ['compiled', { a: 1, b: 2 }],
        ['overlay', { b: 3, c: 4 }],
      ]);

      const result = resolveConfig(sources, values);

      // Overlay (priority=5) takes precedence over compiled (priority=1)
      expect(result.value).toEqual({ a: 1, b: 3, c: 4 });
    });

    it('should fail on unknown sources when configured', () => {
      const sources = [createMockSource({ id: 'unknown-source', origin: 'unknown' })];
      const values = new Map();

      expect(() => {
        resolveConfig(sources, values, { failOnUnknown: true });
      }).toThrow('Unknown config source: unknown-source');
    });

    it('should fail on unbound remote sources when configured', () => {
      const sources = [
        createMockSource({
          id: 'remote',
          origin: 'https://example.com/config',
          revision: 'unverified',
        }),
      ];
      const values = new Map([['remote', { test: true }]]);

      expect(() => {
        resolveConfig(sources, values, { failOnUnboundRemote: true });
      }).toThrow(/Remote source remote missing required bindings/);
    });

    it('should allow unbound remote sources when not configured to fail', () => {
      const sources = [
        createMockSource({
          id: 'remote',
          origin: 'https://example.com/config',
          revision: 'unverified',
        }),
      ];
      const values = new Map([['remote', { test: true }]]);

      const result = resolveConfig(sources, values, { failOnUnboundRemote: false });
      expect(result.value).toEqual({ test: true });
    });

    it('should provide source order (highest precedence first)', () => {
      const sources = [
        createMockSource({ id: 'low', priority: 'environment' }),
        createMockSource({ id: 'high', priority: 'compiled' }),
      ];
      const values = new Map([
        ['low', { source: 'low' }],
        ['high', { source: 'high' }],
      ]);

      const result = resolveConfig(sources, values);
      expect(result.sourceOrder[0].id).toBe('high');
      expect(result.sourceOrder[1].id).toBe('low');
    });
  });

  describe('verifyConfigDrift', () => {
    it('should detect no drift when configs match', () => {
      const before: ResolvedConfig = {
        value: { a: 1 },
        sourceOrder: [],
        sourceHashes: ['hash1'],
        schemaHash: 'schema1',
        resolvedHash: 'same',
        resolvedAt: '2024-01-01',
      };

      const after: ResolvedConfig = {
        ...before,
        resolvedAt: '2024-01-02',
      };

      const result = verifyConfigDrift(before, after);
      expect(result.hasDrift).toBe(false);
      expect(result.details).toHaveLength(0);
    });

    it('should detect drift on hash change', () => {
      const before: ResolvedConfig = {
        value: { a: 1 },
        sourceOrder: [],
        sourceHashes: ['hash1'],
        schemaHash: 'schema1',
        resolvedHash: 'before',
        resolvedAt: '2024-01-01',
      };

      const after: ResolvedConfig = {
        ...before,
        resolvedHash: 'after',
      };

      const result = verifyConfigDrift(before, after);
      expect(result.hasDrift).toBe(true);
      expect(result.details).toContain('Resolved hash mismatch');
    });

    it('should identify schema drift', () => {
      const before: ResolvedConfig = {
        value: { a: 1 },
        sourceOrder: [],
        sourceHashes: [],
        schemaHash: 'old-schema',
        resolvedHash: 'before-hash',
        resolvedAt: '2024-01-01',
      };

      const after: ResolvedConfig = {
        ...before,
        resolvedHash: 'after-hash',
        schemaHash: 'new-schema',
      };

      const result = verifyConfigDrift(before, after);
      expect(result.hasDrift).toBe(true);
      expect(result.details).toContain('Resolved hash mismatch');
      expect(result.details).toContain('Schema hash changed (keys differ)');
    });

    it('should identify added sources', () => {
      const before: ResolvedConfig = {
        value: {},
        sourceOrder: [
          createMockSource({ id: 'existing' }),
        ],
        sourceHashes: ['hash1'],
        schemaHash: 'schema',
        resolvedHash: 'before-hash',
        resolvedAt: '2024-01-01',
      };

      const after: ResolvedConfig = {
        value: {},
        sourceOrder: [
          createMockSource({ id: 'existing' }),
          createMockSource({ id: 'new-source' }),
        ],
        sourceHashes: ['hash1', 'hash2'],
        schemaHash: 'schema',
        resolvedHash: 'after-hash',
        resolvedAt: '2024-01-01',
      };

      const result = verifyConfigDrift(before, after);
      expect(result.hasDrift).toBe(true);
      expect(result.details.some((d) => d.includes('Added sources'))).toBe(true);
    });
  });

  describe('getConfigFingerprint', () => {
    it('should return truncated hash', () => {
      const config: ResolvedConfig = {
        value: {},
        sourceOrder: [],
        sourceHashes: [],
        schemaHash: 'schema',
        resolvedHash: '1234567890abcdef',
        resolvedAt: '2024-01-01',
      };

      const fingerprint = getConfigFingerprint(config);
      expect(fingerprint).toBe('1234567890ab...');
    });
  });

  describe('getRedactedSources', () => {
    it('should return sources without secrets', () => {
      const config: ResolvedConfig = {
        value: {},
        sourceOrder: [
          createMockSource({
            id: 'source1',
            origin: '/path/to/config',
            hasSecrets: true,
            schemaHash: 'secret-schema',
          }),
          createMockSource({
            id: 'source2',
            origin: 'env:API_KEY',
            hasSecrets: false,
          }),
        ],
        sourceHashes: [],
        schemaHash: 'schema',
        resolvedHash: 'hash',
        resolvedAt: '2024-01-01',
      };

      const redacted = getRedactedSources(config);
      expect(redacted).toHaveLength(2);
      expect(redacted[0]).toEqual({
        id: 'source1',
        origin: '/path/to/config',
        hasSecrets: true,
        contentHash: 'hash123',
      });
      expect(redacted[1]).toEqual({
        id: 'source2',
        origin: 'env:API_KEY',
        hasSecrets: false,
        contentHash: 'hash123',
      });
    });
  });
});
