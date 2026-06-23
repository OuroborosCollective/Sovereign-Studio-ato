/**
 * Latent Space Navigator Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { LatentSpaceNavigator, createLatentSpace } from './latentSpace';
import type { PatternEmbedding } from './types';

describe('LatentSpaceNavigator', () => {
  let latentSpace: LatentSpaceNavigator;

  beforeEach(() => {
    latentSpace = new LatentSpaceNavigator({
      dimension: 64,
      maxPatterns: 100,
      similarityThreshold: 0.7,
      kNeighbors: 5,
    });
  });

  describe('addPattern', () => {
    it('should add a valid pattern', () => {
      const pattern: PatternEmbedding = {
        id: 'pattern-1',
        embedding: new Array(64).fill(0.5),
        norm: Math.sqrt(64 * 0.25),
        signalValue: 0.8,
        node: 'runtime.decision',
        createdAt: Date.now(),
        matchCount: 0,
        avgConfidence: 0,
      };

      expect(latentSpace.addPattern(pattern)).toBe(true);
      expect(latentSpace.getPatternCount()).toBe(1);
    });

    it('should reject pattern with wrong dimension', () => {
      const pattern: PatternEmbedding = {
        id: 'pattern-1',
        embedding: new Array(32).fill(0.5), // Wrong dimension
        norm: 1,
        signalValue: 0.8,
        node: 'runtime.decision',
        createdAt: Date.now(),
        matchCount: 0,
        avgConfidence: 0,
      };

      expect(latentSpace.addPattern(pattern)).toBe(false);
      expect(latentSpace.getPatternCount()).toBe(0);
    });

    it('should evict old patterns when at capacity', () => {
      // Add patterns up to capacity
      for (let i = 0; i < 100; i++) {
        const pattern: PatternEmbedding = {
          id: `pattern-${i}`,
          embedding: new Array(64).fill(Math.random()),
          norm: 1,
          signalValue: Math.random(),
          node: 'runtime.decision',
          createdAt: Date.now(),
          matchCount: 0,
          avgConfidence: 0,
        };
        latentSpace.addPattern(pattern);
      }

      expect(latentSpace.getPatternCount()).toBe(100);

      // Add one more - should evict oldest
      const newPattern: PatternEmbedding = {
        id: 'pattern-new',
        embedding: new Array(64).fill(0.5),
        norm: 1,
        signalValue: 0.8,
        node: 'runtime.decision',
        createdAt: Date.now(),
        matchCount: 0,
        avgConfidence: 0,
      };
      latentSpace.addPattern(newPattern);

      // Count should still be 100
      expect(latentSpace.getPatternCount()).toBe(100);
      // Oldest pattern should be evicted
      expect(latentSpace.getPattern('pattern-0')).toBeUndefined();
    });
  });

  describe('findSimilar', () => {
    it('should find similar patterns', () => {
      // Add a pattern with known embedding
      const basePattern: PatternEmbedding = {
        id: 'pattern-base',
        embedding: new Array(64).fill(0.5),
        norm: 1,
        signalValue: 0.8,
        node: 'runtime.decision',
        createdAt: Date.now(),
        matchCount: 0,
        avgConfidence: 0,
      };
      latentSpace.addPattern(basePattern);

      // Search for similar - should match with high similarity
      const result = latentSpace.findSimilar(0.8, 'runtime.decision');

      expect(result).not.toBeNull();
      expect(result!.patternId).toBe('pattern-base');
      expect(result!.score).toBeGreaterThan(0.9);
    });

    it('should return null when no patterns exist', () => {
      const result = latentSpace.findSimilar(0.5, 'runtime.decision');
      expect(result).toBeNull();
    });
  });

  describe('findTopK', () => {
    it('should return top k similar patterns', () => {
      // Add multiple patterns
      for (let i = 0; i < 10; i++) {
        const pattern: PatternEmbedding = {
          id: `pattern-${i}`,
          embedding: new Array(64).fill(i / 10),
          norm: 1,
          signalValue: i / 10,
          node: 'runtime.decision',
          createdAt: Date.now(),
          matchCount: 0,
          avgConfidence: 0,
        };
        latentSpace.addPattern(pattern);
      }

      const results = latentSpace.findTopK(0.5, 'runtime.decision', 3);

      expect(results.length).toBeLessThanOrEqual(3);
      // Should be sorted by score descending
      for (let i = 1; i < results.length; i++) {
        expect(results[i - 1].score).toBeGreaterThanOrEqual(results[i].score);
      }
    });
  });

  describe('cosineSimilarity', () => {
    it('should return 1 for identical vectors', () => {
      const vector = new Array(64).fill(0.5);
      const similarity = latentSpace.cosineSimilarity(vector, vector);
      expect(similarity).toBeCloseTo(1, 5);
    });

    it('should return 0 for orthogonal vectors', () => {
      const vector1 = new Array(64).fill(0);
      vector1[0] = 1;
      const vector2 = new Array(64).fill(0);
      vector2[1] = 1;
      const similarity = latentSpace.cosineSimilarity(vector1, vector2);
      expect(similarity).toBeCloseTo(0, 5);
    });

    it('should handle pre-computed norms', () => {
      const vector1 = new Array(64).fill(0.5);
      const vector2 = new Array(64).fill(0.5);
      const norm1 = latentSpace.computeNorm(vector1);
      const norm2 = latentSpace.computeNorm(vector2);
      const similarity = latentSpace.cosineSimilarity(vector1, vector2, norm1, norm2);
      expect(similarity).toBeCloseTo(1, 5);
    });
  });

  describe('getPatternsForNode', () => {
    it('should return patterns for specific node', () => {
      const pattern1: PatternEmbedding = {
        id: 'pattern-1',
        embedding: new Array(64).fill(0.5),
        norm: 1,
        signalValue: 0.8,
        node: 'node-a',
        createdAt: Date.now(),
        matchCount: 0,
        avgConfidence: 0,
      };
      const pattern2: PatternEmbedding = {
        id: 'pattern-2',
        embedding: new Array(64).fill(0.3),
        norm: 1,
        signalValue: 0.6,
        node: 'node-b',
        createdAt: Date.now(),
        matchCount: 0,
        avgConfidence: 0,
      };

      latentSpace.addPattern(pattern1);
      latentSpace.addPattern(pattern2);

      const nodeAPatterns = latentSpace.getPatternsForNode('node-a');
      expect(nodeAPatterns.length).toBe(1);
      expect(nodeAPatterns[0].id).toBe('pattern-1');
    });
  });

  describe('clear', () => {
    it('should clear all patterns', () => {
      for (let i = 0; i < 5; i++) {
        const pattern: PatternEmbedding = {
          id: `pattern-${i}`,
          embedding: new Array(64).fill(0.5),
          norm: 1,
          signalValue: 0.8,
          node: 'runtime.decision',
          createdAt: Date.now(),
          matchCount: 0,
          avgConfidence: 0,
        };
        latentSpace.addPattern(pattern);
      }

      expect(latentSpace.getPatternCount()).toBe(5);
      latentSpace.clear();
      expect(latentSpace.getPatternCount()).toBe(0);
    });
  });

  describe('computeCorrelationMatrix', () => {
    it('should compute correlation matrix', () => {
      // Add some patterns
      for (let i = 0; i < 3; i++) {
        const pattern: PatternEmbedding = {
          id: `pattern-${i}`,
          embedding: new Array(64).fill(i * 0.3),
          norm: 1,
          signalValue: i * 0.3,
          node: 'runtime.decision',
          createdAt: Date.now(),
          matchCount: 0,
          avgConfidence: 0,
        };
        latentSpace.addPattern(pattern);
      }

      const matrix = latentSpace.computeCorrelationMatrix();

      expect(matrix.size).toBe(3);
      // Diagonal should be 1
      for (const [id, row] of matrix) {
        expect(row.get(id)).toBeCloseTo(1, 5);
      }
    });
  });

  describe('estimateMemoryUsage', () => {
    it('should estimate memory usage', () => {
      const initialMemory = latentSpace.estimateMemoryUsage();

      const pattern: PatternEmbedding = {
        id: 'pattern-1',
        embedding: new Array(64).fill(0.5),
        norm: 1,
        signalValue: 0.8,
        node: 'runtime.decision',
        createdAt: Date.now(),
        matchCount: 0,
        avgConfidence: 0,
      };
      latentSpace.addPattern(pattern);

      const newMemory = latentSpace.estimateMemoryUsage();
      expect(newMemory).toBeGreaterThan(initialMemory);
    });
  });

  describe('exportPatterns / importPatterns', () => {
    it('should export and import patterns', () => {
      const patterns: PatternEmbedding[] = [];
      for (let i = 0; i < 5; i++) {
        const pattern: PatternEmbedding = {
          id: `pattern-${i}`,
          embedding: new Array(64).fill(0.5),
          norm: 1,
          signalValue: 0.8,
          node: 'runtime.decision',
          createdAt: Date.now(),
          matchCount: i,
          avgConfidence: 0.5 + i * 0.1,
        };
        patterns.push(pattern);
        latentSpace.addPattern(pattern);
      }

      const exported = latentSpace.exportPatterns();
      expect(exported.length).toBe(5);

      // Clear and import
      latentSpace.clear();
      expect(latentSpace.getPatternCount()).toBe(0);

      const imported = latentSpace.importPatterns(patterns);
      expect(imported).toBe(5);
      expect(latentSpace.getPatternCount()).toBe(5);
    });
  });
});

describe('createLatentSpace factory', () => {
  it('should create with default config', () => {
    const ls = createLatentSpace();
    expect(ls.getPatternCount()).toBe(0);
  });

  it('should create with custom config', () => {
    const ls = createLatentSpace({
      dimension: 128,
      maxPatterns: 500,
      similarityThreshold: 0.8,
    });
    const config = ls.getConfig();
    expect(config.dimension).toBe(128);
    expect(config.maxPatterns).toBe(500);
    expect(config.similarityThreshold).toBe(0.8);
  });
});
