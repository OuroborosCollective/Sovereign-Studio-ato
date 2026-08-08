import { describe, it, expect } from 'vitest';
import {
  createPublicReceiptHash,
  createConfigReceipt,
  verifyConfigReceipt,
  getPatchMonProjection,
  isReceiptBound,
  type ConfigReceipt,
} from './configReceipt';
import type { ResolvedConfig } from './configResolver';

function createMockResolvedConfig(overrides: Partial<ResolvedConfig> = {}): ResolvedConfig {
  return {
    value: { a: 1 },
    sourceOrder: [],
    sourceHashes: ['hash1'],
    schemaHash: 'schema1',
    resolvedHash: 'resolved1',
    resolvedAt: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('configReceipt', () => {
  describe('createPublicReceiptHash', () => {
    it('should create deterministic hash', () => {
      const hash1 = createPublicReceiptHash('fp1', 'schema1', ['hash1']);
      const hash2 = createPublicReceiptHash('fp1', 'schema1', ['hash1']);
      expect(hash1).toBe(hash2);
    });

    it('should produce different hash for different input', () => {
      const hash1 = createPublicReceiptHash('fp1', 'schema1', ['hash1']);
      const hash2 = createPublicReceiptHash('fp2', 'schema1', ['hash1']);
      expect(hash1).not.toBe(hash2);
    });

    it('should be independent of source order', () => {
      const hash1 = createPublicReceiptHash('fp', 'schema', ['a', 'b']);
      const hash2 = createPublicReceiptHash('fp', 'schema', ['b', 'a']);
      expect(hash1).toBe(hash2);
    });
  });

  describe('createConfigReceipt', () => {
    it('should create receipt with required fields', () => {
      const resolved = createMockResolvedConfig();
      const receipt = createConfigReceipt(resolved);

      expect(receipt.id).toBeDefined();
      expect(receipt.id).toMatch(/^cfg_rcpt_/);
      expect(receipt.configFingerprint).toBe('resolved1');
      expect(receipt.schemaHash).toBe('schema1');
      expect(receipt.sourceHashes).toEqual(['hash1']);
      expect(receipt.publicReceiptHash).toBeDefined();
      expect(receipt.sources).toHaveLength(0);
      expect(receipt.createdAt).toBeDefined();
    });

    it('should include optional bindings', () => {
      const resolved = createMockResolvedConfig();
      const receipt = createConfigReceipt(resolved, {
        imageDigest: 'sha256:abc123',
        revision: 'main@abc123',
      });

      expect(receipt.imageDigest).toBe('sha256:abc123');
      expect(receipt.revision).toBe('main@abc123');
    });

    it('should map sources correctly', () => {
      const resolved = createMockResolvedConfig({
        sourceOrder: [
          {
            id: 'source1',
            priority: 'compiled',
            revision: 'rev1',
            contentHash: 'ch1',
            schemaHash: 'sh1',
            hasSecrets: true,
            origin: '/config/defaults.json',
          },
          {
            id: 'source2',
            priority: 'environment',
            revision: 'rev2',
            contentHash: 'ch2',
            schemaHash: 'sh2',
            hasSecrets: false,
            origin: 'env:RUNTIME_CONFIG',
          },
        ],
      });

      const receipt = createConfigReceipt(resolved);

      expect(receipt.sources).toHaveLength(2);
      expect(receipt.sources[0]).toEqual({
        id: 'source1',
        origin: '/config/defaults.json',
        hasSecrets: true,
      });
      expect(receipt.sources[1]).toEqual({
        id: 'source2',
        origin: 'env:RUNTIME_CONFIG',
        hasSecrets: false,
      });
    });
  });

  describe('verifyConfigReceipt', () => {
    it('should verify valid receipt', () => {
      const resolved = createMockResolvedConfig();
      const receipt = createConfigReceipt(resolved);

      const result = verifyConfigReceipt(receipt, resolved);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should detect fingerprint mismatch', () => {
      const resolved = createMockResolvedConfig({ resolvedHash: 'original' });
      const receipt = createConfigReceipt(resolved);
      receipt.configFingerprint = 'tampered';

      const result = verifyConfigReceipt(receipt, resolved);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Config fingerprint mismatch');
    });

    it('should detect schema hash mismatch', () => {
      const resolved = createMockResolvedConfig({ schemaHash: 'original' });
      const receipt = createConfigReceipt(resolved);
      receipt.schemaHash = 'tampered';

      const result = verifyConfigReceipt(receipt, resolved);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Schema hash mismatch');
    });

    it('should detect source hash mismatch', () => {
      const resolved = createMockResolvedConfig({
        sourceHashes: ['hash1', 'hash2'],
      });
      const receipt = createConfigReceipt(resolved);
      receipt.sourceHashes = ['hash1', 'hash3'];

      const result = verifyConfigReceipt(receipt, resolved);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Source hashes mismatch');
    });

    it('should detect source count mismatch', () => {
      const resolved = createMockResolvedConfig({
        sourceOrder: [
          {
            id: 's1',
            priority: 'compiled',
            revision: 'r1',
            contentHash: 'h1',
            schemaHash: 'sh1',
            hasSecrets: false,
            origin: 'test',
          },
        ],
      });
      const receipt = createConfigReceipt(resolved);
      receipt.sources.push({ id: 'extra', origin: 'test', hasSecrets: false });

      const result = verifyConfigReceipt(receipt, resolved);
      expect(result.valid).toBe(false);
      expect(result.errors.some((e) => e.includes('Source count mismatch'))).toBe(true);
    });
  });

  describe('getPatchMonProjection', () => {
    it('should return PatchMon-compatible projection', () => {
      const resolved = createMockResolvedConfig();
      const receipt = createConfigReceipt(resolved, {
        imageDigest: 'sha256:abc',
        revision: 'main@123',
      });

      const projection = getPatchMonProjection(receipt);

      expect(projection).toEqual({
        revision: 'main@123',
        imageDigest: 'sha256:abc',
        schemaHash: 'schema1',
        configHash: 'resolved1',
        sourceCount: 0,
      });
    });

    it('should handle unbound receipt', () => {
      const resolved = createMockResolvedConfig();
      const receipt = createConfigReceipt(resolved);

      const projection = getPatchMonProjection(receipt);

      expect(projection.revision).toBeUndefined();
      expect(projection.imageDigest).toBeUndefined();
    });
  });

  describe('isReceiptBound', () => {
    it('should return true when revision is set', () => {
      const resolved = createMockResolvedConfig();
      const receipt = createConfigReceipt(resolved, { revision: 'main@123' });
      expect(isReceiptBound(receipt)).toBe(true);
    });

    it('should return true when imageDigest is set', () => {
      const resolved = createMockResolvedConfig();
      const receipt = createConfigReceipt(resolved, { imageDigest: 'sha256:abc' });
      expect(isReceiptBound(receipt)).toBe(true);
    });

    it('should return false when neither is set', () => {
      const resolved = createMockResolvedConfig();
      const receipt = createConfigReceipt(resolved);
      expect(isReceiptBound(receipt)).toBe(false);
    });
  });
});
