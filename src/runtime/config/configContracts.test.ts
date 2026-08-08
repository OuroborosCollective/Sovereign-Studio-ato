/**
 * Configuration Contracts Tests
 */

import {
  validateConfigSource,
  validateConfigResolution,
  generateConfigSourceSchemaHash,
  generateConfigResolutionSchemaHash,
  CONFIG_SOURCE_SCHEMA_ID,
  CONFIG_RESOLUTION_SCHEMA_ID,
} from './configSources';

import {
  resolveConfig,
  validateConfigConsistency,
  createConfigSource,
  deepMerge,
  arrayMerge,
  EXPLICIT_DELETE,
} from './configResolver';

describe('ConfigSource Contract', () => {
  const validSource = {
    schemaId: 'config-source.v1',
    schemaVersion: 'v1',
    id: 'source-001',
    type: 'compiled-defaults',
    priority: 0,
    contentHash: 'abc123',
    schemaHash: 'def456',
    timestamp: 1234567890,
    hasSecrets: false,
  };

  describe('validateConfigSource', () => {
    it('accepts valid config source', () => {
      const result = validateConfigSource(validSource);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects non-object input', () => {
      const result = validateConfigSource(null);
      expect(result.valid).toBe(false);
    });

    it('rejects wrong schemaId', () => {
      const result = validateConfigSource({ ...validSource, schemaId: 'wrong' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'schemaId')).toBe(true);
    });

    it('rejects invalid schemaVersion', () => {
      const result = validateConfigSource({ ...validSource, schemaVersion: '1.0' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'schemaVersion')).toBe(true);
    });

    it('rejects missing required fields', () => {
      const result = validateConfigSource({ schemaId: 'config-source.v1', schemaVersion: 'v1' });
      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
    });

    it('rejects negative priority', () => {
      const result = validateConfigSource({ ...validSource, priority: -1 });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'priority')).toBe(true);
    });

    it('rejects invalid type', () => {
      const result = validateConfigSource({ ...validSource, type: 'invalid' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'type')).toBe(true);
    });

    it('accepts all valid types', () => {
      const types = [
        'compiled-defaults', 'image-manifest', 'deployment-config',
        'environment-projection', 'runtime-overlay', 'user-override',
      ];
      for (const type of types) {
        const result = validateConfigSource({ ...validSource, type });
        expect(result.valid).toBe(true);
      }
    });

    it('rejects unknown fields in strict mode', () => {
      const result = validateConfigSource({ ...validSource, unknown: 'field' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'UNKNOWN_FIELD')).toBe(true);
    });

    it('accepts unknown fields in non-strict mode', () => {
      const result = validateConfigSource({ ...validSource, unknown: 'field' }, { strict: false });
      expect(result.valid).toBe(true);
    });

    it('warns for remote sources without digest', () => {
      const result = validateConfigSource({
        ...validSource,
        type: 'image-manifest',
        origin: 'https://example.com/manifest.json',
        revision: 'abc123',
      });
      expect(result.warnings.some(w => w.field === 'digest')).toBe(true);
    });
  });
});

describe('ConfigResolution Contract', () => {
  const validSource = {
    schemaId: 'config-source.v1',
    schemaVersion: 'v1',
    id: 'source-001',
    type: 'compiled-defaults' as const,
    priority: 0,
    contentHash: 'abc123',
    schemaHash: 'def456',
    timestamp: 1234567890,
    hasSecrets: false,
  };

  const validResolution = {
    schemaId: 'config-resolution.v1',
    schemaVersion: 'v1',
    id: 'res-001',
    config: { setting: 'value' },
    sources: [validSource],
    contentHash: 'merged123',
    schemaHash: 'schema456',
    redactedFingerprint: 'fingerprint789',
    timestamp: 1234567890,
  };

  describe('validateConfigResolution', () => {
    it('accepts valid config resolution', () => {
      const result = validateConfigResolution(validResolution);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects non-object input', () => {
      const result = validateConfigResolution(null);
      expect(result.valid).toBe(false);
    });

    it('rejects wrong schemaId', () => {
      const result = validateConfigResolution({ ...validResolution, schemaId: 'wrong' });
      expect(result.valid).toBe(false);
    });

    it('rejects non-object config', () => {
      const result = validateConfigResolution({ ...validResolution, config: 'string' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'config')).toBe(true);
    });

    it('rejects non-array sources', () => {
      const result = validateConfigResolution({ ...validResolution, sources: {} });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'sources')).toBe(true);
    });

    it('rejects unknown fields in strict mode', () => {
      const result = validateConfigResolution({ ...validResolution, unknown: 'field' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'UNKNOWN_FIELD')).toBe(true);
    });
  });
});

describe('Config Resolver', () => {
  describe('deepMerge', () => {
    it('merges nested objects', () => {
      const base = { a: { b: 1 }, c: 2 };
      const overlay = { a: { d: 3 }, e: 4 };
      const result = deepMerge(base, overlay);
      expect(result).toEqual({ a: { b: 1, d: 3 }, c: 2, e: 4 });
    });

    it('overwrites primitive values', () => {
      const base = { a: 1 };
      const overlay = { a: 2 };
      const result = deepMerge(base, overlay);
      expect(result).toEqual({ a: 2 });
    });

    it('supports explicit delete', () => {
      const base = { a: 1, b: 2 };
      const overlay = { a: EXPLICIT_DELETE };
      const result = deepMerge(base, overlay);
      expect(result).toEqual({ b: 2 });
    });

    it('merges arrays by concatenation', () => {
      const base = { items: [1, 2] };
      const overlay = { items: [3, 4] };
      const result = deepMerge(base, overlay);
      expect(result).toEqual({ items: [1, 2, 3, 4] });
    });

    it('deduplicates array items', () => {
      const base = { items: [1, 2] };
      const overlay = { items: [2, 3] };
      const result = deepMerge(base, overlay);
      expect(result).toEqual({ items: [1, 2, 3] });
    });
  });

  describe('arrayMerge', () => {
    it('concatenates arrays', () => {
      const result = arrayMerge([1, 2], [3, 4]);
      expect(result).toEqual([1, 2, 3, 4]);
    });

    it('deduplicates primitives', () => {
      const result = arrayMerge(['a', 'b'], ['b', 'c']);
      expect(result).toEqual(['a', 'b', 'c']);
    });

    it('deduplicates objects by deep equality', () => {
      const result = arrayMerge([{ x: 1 }], [{ x: 1 }]);
      expect(result).toEqual([{ x: 1 }]);
    });
  });

  describe('createConfigSource', () => {
    it('creates a valid config source', () => {
      const source = createConfigSource('compiled-defaults', 'test-source', { setting: 'value' });
      expect(source.schemaId).toBe(CONFIG_SOURCE_SCHEMA_ID);
      expect(source.id).toBe('test-source');
      expect(source.type).toBe('compiled-defaults');
      expect(source.contentHash).toBeTruthy();
      expect(source.schemaHash).toBeTruthy();
    });

    it('detects secrets in config', () => {
      const sourceWithSecret = createConfigSource('compiled-defaults', 'test', { api_key: 'secret' });
      expect(sourceWithSecret.hasSecrets).toBe(true);

      const sourceNoSecret = createConfigSource('compiled-defaults', 'test', { name: 'value' });
      expect(sourceNoSecret.hasSecrets).toBe(false);
    });

    it('assigns correct priorities by type', () => {
      const defaults = createConfigSource('compiled-defaults', 'test', {});
      const overlay = createConfigSource('runtime-overlay', 'test', {});
      const userOverride = createConfigSource('user-override', 'test', {});

      expect(defaults.priority).toBe(0);
      expect(overlay.priority).toBe(40);
      expect(userOverride.priority).toBe(50);
    });
  });

  describe('resolveConfig', () => {
    it('resolves with valid sources', () => {
      const sources = [
        createConfigSource('compiled-defaults', 'defaults', { base: true }),
        createConfigSource('runtime-overlay', 'overlay', { overlay: true }),
      ];
      const result = resolveConfig(sources);
      expect(result.resolution).not.toBeNull();
      expect(result.resolution?.sources).toHaveLength(2);
    });

    it('sorts sources by priority', () => {
      const sources = [
        createConfigSource('user-override', 'high', { priority: 50 }),
        createConfigSource('compiled-defaults', 'low', { priority: 0 }),
      ];
      const result = resolveConfig(sources);
      expect(result.resolution?.sources[0].type).toBe('compiled-defaults');
      expect(result.resolution?.sources[1].type).toBe('user-override');
    });

    it('fails in strict mode with missing revision on remote source', () => {
      const sources = [createConfigSource('image-manifest', 'test', {})];
      const result = resolveConfig(sources, { strict: true });
      expect(result.resolution).toBeNull();
      expect(result.error).toContain('requires revision');
    });

    it('allows missing revision in non-strict mode', () => {
      const sources = [createConfigSource('image-manifest', 'test', {})];
      const result = resolveConfig(sources, { strict: false });
      expect(result.resolution).not.toBeNull();
    });
  });

  describe('validateConfigConsistency', () => {
    it('detects revision drift', () => {
      const resolution = {
        schemaId: 'config-resolution.v1',
        schemaVersion: 'v1',
        id: 'res-001',
        config: {},
        sources: [{ schemaId: 'config-source.v1', schemaVersion: 'v1', id: 's1', type: 'compiled-defaults' as const, priority: 0, contentHash: 'abc', schemaHash: 'def', timestamp: 1, hasSecrets: false, revision: 'old-rev' }],
        contentHash: 'merged',
        schemaHash: 'schema',
        redactedFingerprint: 'fp',
        timestamp: 1,
      };

      const readback = {
        revision: 'new-rev',
        imageDigest: 'digest',
        schemaHash: 'schema',
        configFingerprint: 'fp',
      };

      const result = validateConfigConsistency(resolution, readback);
      expect(result.consistent).toBe(false);
      expect(result.drift.some(d => d.includes('revision mismatch'))).toBe(true);
    });
  });
});

describe('Schema Hash Generation', () => {
  it('generates consistent hashes', () => {
    const hash1 = generateConfigSourceSchemaHash();
    const hash2 = generateConfigSourceSchemaHash();
    expect(hash1).toBe(hash2);
  });

  it('generates different hashes for different schemas', () => {
    const hash1 = generateConfigSourceSchemaHash();
    const hash2 = generateConfigResolutionSchemaHash();
    expect(hash1).not.toBe(hash2);
  });
});
