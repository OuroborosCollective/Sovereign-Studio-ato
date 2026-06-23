/**
 * Latent Space Navigator
 *
 * Vector store with cosine similarity search for pattern matching.
 * Implements the Hippocampus component that stores and retrieves
 * embeddings of signal patterns.
 *
 * Mathematical Foundation:
 * - Cosine Similarity: S_C(v₁, v₂) = (v₁ · v₂) / (||v₁|| × ||v₂||)
 *
 * @module predictive/latentSpace
 */

import type {
  PatternEmbedding,
  SimilarityMatch,
  Signal,
  LatentSpaceSearchResult,
} from './types';

import { DEFAULT_PREDICTIVE_CONFIG } from './types';

// ============================================================================
// Constants
// ============================================================================

const DEFAULT_DIMENSION = 64;
const DEFAULT_MAX_PATTERNS = 10000;
const DEFAULT_SIMILARITY_THRESHOLD = 0.7;
const DEFAULT_K_NEIGHBORS = 10;

// ============================================================================
// Latent Space Navigator
// ============================================================================

export interface LatentSpaceConfig {
  dimension: number;
  maxPatterns: number;
  similarityThreshold: number;
  kNeighbors?: number;
}

export interface LatentSpaceSearchOptions {
  k?: number;
  threshold?: number;
  nodeFilter?: string;
}

/**
 * Latent Space Navigator for vector-based pattern storage and retrieval.
 * Uses cosine similarity for nearest-neighbor search.
 */
export class LatentSpaceNavigator {
  private patterns: Map<string, PatternEmbedding> = new Map();
  private dimension: number;
  private maxPatterns: number;
  private similarityThreshold: number;
  private kNeighbors: number;
  private nodeIndex: Map<string, Set<string>> = new Map(); // node -> pattern IDs
  private insertionOrder: string[] = []; // For LRU-style eviction

  constructor(config: Partial<LatentSpaceConfig> = {}) {
    this.dimension = config.dimension ?? DEFAULT_DIMENSION;
    this.maxPatterns = config.maxPatterns ?? DEFAULT_MAX_PATTERNS;
    this.similarityThreshold = config.similarityThreshold ?? DEFAULT_SIMILARITY_THRESHOLD;
    this.kNeighbors = config.kNeighbors ?? DEFAULT_K_NEIGHBORS;
  }

  /**
   * Get current pattern count.
   */
  getPatternCount(): number {
    return this.patterns.size;
  }

  /**
   * Get configuration.
   */
  getConfig(): LatentSpaceConfig {
    return {
      dimension: this.dimension,
      maxPatterns: this.maxPatterns,
      similarityThreshold: this.similarityThreshold,
      kNeighbors: this.kNeighbors,
    };
  }

  /**
   * Add a pattern embedding to the latent space.
   */
  addPattern(pattern: PatternEmbedding): boolean {
    // Validate dimension
    if (pattern.embedding.length !== this.dimension) {
      console.warn(
        `[LatentSpace] Pattern dimension mismatch: expected ${this.dimension}, got ${pattern.embedding.length}`,
      );
      return false;
    }

    // Evict old patterns if at capacity
    while (this.patterns.size >= this.maxPatterns && this.insertionOrder.length > 0) {
      const oldestId = this.insertionOrder.shift();
      if (oldestId) {
        this.evictPattern(oldestId);
      }
    }

    // Add to main store
    this.patterns.set(pattern.id, {
      ...pattern,
      norm: this.computeNorm(pattern.embedding),
    });

    // Add to node index
    if (!this.nodeIndex.has(pattern.node)) {
      this.nodeIndex.set(pattern.node, new Set());
    }
    this.nodeIndex.get(pattern.node)!.add(pattern.id);

    // Track insertion order
    this.insertionOrder.push(pattern.id);

    return true;
  }

  /**
   * Remove a pattern from the latent space.
   */
  evictPattern(patternId: string): void {
    const pattern = this.patterns.get(patternId);
    if (!pattern) return;

    // Remove from node index
    const nodePatterns = this.nodeIndex.get(pattern.node);
    if (nodePatterns) {
      nodePatterns.delete(patternId);
      if (nodePatterns.size === 0) {
        this.nodeIndex.delete(pattern.node);
      }
    }

    // Remove from main store
    this.patterns.delete(patternId);

    // Remove from insertion order
    const orderIndex = this.insertionOrder.indexOf(patternId);
    if (orderIndex !== -1) {
      this.insertionOrder.splice(orderIndex, 1);
    }
  }

  /**
   * Find similar patterns using cosine similarity.
   * Returns patterns with similarity >= threshold.
   */
  findSimilar(
    value: number,
    node: string,
    options: LatentSpaceSearchOptions = {},
  ): SimilarityMatch | null {
    const k = options.k ?? this.kNeighbors;
    const threshold = options.threshold ?? this.similarityThreshold;

    // Create query embedding from value
    const queryEmbedding = this.createQueryEmbedding(value);
    const queryNorm = this.computeNorm(queryEmbedding);

    // Get candidate patterns
    const candidates = this.getCandidates(node, options.nodeFilter);

    if (candidates.length === 0) {
      return null;
    }

    // Compute similarities
    const similarities: SimilarityMatch[] = [];

    for (const pattern of candidates) {
      const score = this.cosineSimilarity(queryEmbedding, pattern.embedding, queryNorm, pattern.norm);

      if (score >= threshold) {
        similarities.push({
          patternId: pattern.id,
          score,
          normalizedScore: (score + 1) / 2, // Normalize from [-1, 1] to [0, 1]
          pattern,
          isStrongMatch: score >= 0.9,
        });
      }
    }

    if (similarities.length === 0) {
      return null;
    }

    // Sort by score descending
    similarities.sort((a, b) => b.score - a.score);

    // Update match counts
    for (const match of similarities.slice(0, k)) {
      const pattern = this.patterns.get(match.patternId);
      if (pattern) {
        pattern.matchCount++;
        pattern.avgConfidence = (pattern.avgConfidence * (pattern.matchCount - 1) + match.score) / pattern.matchCount;
      }
    }

    // Return best match
    return similarities[0];
  }

  /**
   * Find top-k similar patterns.
   */
  findTopK(
    value: number,
    node: string,
    k: number = this.kNeighbors,
    options: LatentSpaceSearchOptions = {},
  ): SimilarityMatch[] {
    const threshold = options.threshold ?? -1; // No threshold for top-k

    const queryEmbedding = this.createQueryEmbedding(value);
    const queryNorm = this.computeNorm(queryEmbedding);

    const candidates = this.getCandidates(node, options.nodeFilter);

    if (candidates.length === 0) {
      return [];
    }

    const similarities: SimilarityMatch[] = [];

    for (const pattern of candidates) {
      const score = this.cosineSimilarity(queryEmbedding, pattern.embedding, queryNorm, pattern.norm);

      if (score >= threshold) {
        similarities.push({
          patternId: pattern.id,
          score,
          normalizedScore: (score + 1) / 2,
          pattern,
          isStrongMatch: score >= 0.9,
        });
      }
    }

    similarities.sort((a, b) => b.score - a.score);
    return similarities.slice(0, k);
  }

  /**
   * Get pattern by ID.
   */
  getPattern(patternId: string): PatternEmbedding | undefined {
    return this.patterns.get(patternId);
  }

  /**
   * Get all patterns for a node.
   */
  getPatternsForNode(node: string): PatternEmbedding[] {
    const patternIds = this.nodeIndex.get(node);
    if (!patternIds) return [];

    return Array.from(patternIds)
      .map((id) => this.patterns.get(id))
      .filter((p): p is PatternEmbedding => p !== undefined);
  }

  /**
   * Get all patterns.
   */
  getAllPatterns(): PatternEmbedding[] {
    return Array.from(this.patterns.values());
  }

  /**
   * Compute cosine similarity between two vectors.
   * S_C(v₁, v₂) = (v₁ · v₂) / (||v₁|| × ||v₂||)
   */
  cosineSimilarity(
    v1: number[],
    v2: number[],
    norm1?: number,
    norm2?: number,
  ): number {
    if (v1.length !== v2.length) {
      throw new Error('Vector dimension mismatch');
    }

    const n1 = norm1 ?? this.computeNorm(v1);
    const n2 = norm2 ?? this.computeNorm(v2);

    if (n1 === 0 || n2 === 0) {
      return 0; // Avoid division by zero
    }

    let dotProduct = 0;
    for (let i = 0; i < v1.length; i++) {
      dotProduct += v1[i] * v2[i];
    }

    return dotProduct / (n1 * n2);
  }

  /**
   * Compute L2 norm of a vector.
   */
  computeNorm(vector: number[]): number {
    let sum = 0;
    for (const v of vector) {
      sum += v * v;
    }
    return Math.sqrt(sum);
  }

  /**
   * Create a query embedding from a signal value.
   * Uses a deterministic hash-like function.
   */
  private createQueryEmbedding(value: number): number[] {
    const embedding: number[] = [];
    const seed = value;

    for (let i = 0; i < this.dimension; i++) {
      // Deterministic pseudo-random based on value and position
      const s = seed * (i + 1) * 7919;
      embedding.push((Math.sin(s) + 1) / 2);
    }

    return embedding;
  }

  /**
   * Get candidate patterns based on node filter.
   */
  private getCandidates(node: string, nodeFilter?: string): PatternEmbedding[] {
    if (nodeFilter) {
      const patternIds = this.nodeIndex.get(nodeFilter);
      if (!patternIds) return [];
      return Array.from(patternIds)
        .map((id) => this.patterns.get(id))
        .filter((p): p is PatternEmbedding => p !== undefined);
    }

    // Include patterns from the same node and general patterns
    const patterns: PatternEmbedding[] = [];

    const nodePatterns = this.nodeIndex.get(node);
    if (nodePatterns) {
      for (const id of nodePatterns) {
        const p = this.patterns.get(id);
        if (p) patterns.push(p);
      }
    }

    // Also include patterns without specific node association
    for (const p of this.patterns.values()) {
      if (p.node === node) continue;
      // Include some cross-node patterns (10% sample)
      if (Math.random() < 0.1) {
        patterns.push(p);
      }
    }

    return patterns;
  }

  /**
   * Compute pattern correlation matrix.
   * Returns Pearson correlation coefficients between patterns.
   */
  computeCorrelationMatrix(node?: string): Map<string, Map<string, number>> {
    const patterns = node ? this.getPatternsForNode(node) : this.getAllPatterns();
    const correlations = new Map<string, Map<string, number>>();

    for (const p1 of patterns) {
      const row = new Map<string, number>();
      for (const p2 of patterns) {
        if (p1.id === p2.id) {
          row.set(p2.id, 1);
        } else {
          const score = this.cosineSimilarity(p1.embedding, p2.embedding, p1.norm, p2.norm);
          row.set(p2.id, score);
        }
      }
      correlations.set(p1.id, row);
    }

    return correlations;
  }

  /**
   * Clear all patterns.
   */
  clear(): void {
    this.patterns.clear();
    this.nodeIndex.clear();
    this.insertionOrder = [];
  }

  /**
   * Get memory usage estimate in bytes.
   */
  estimateMemoryUsage(): number {
    // Approximate: patterns * (id + embedding + metadata)
    const bytesPerPattern = 50 + this.dimension * 8 + 100; // strings + float64 array + metadata
    return this.patterns.size * bytesPerPattern;
  }

  /**
   * Export patterns for serialization.
   */
  exportPatterns(): PatternEmbedding[] {
    return this.getAllPatterns();
  }

  /**
   * Import patterns from serialization.
   */
  importPatterns(patterns: PatternEmbedding[]): number {
    let imported = 0;
    for (const pattern of patterns) {
      if (this.addPattern(pattern)) {
        imported++;
      }
    }
    return imported;
  }
}

// ============================================================================
// Default Factory
// ============================================================================

export function createLatentSpace(
  config?: Partial<LatentSpaceConfig>,
): LatentSpaceNavigator {
  return new LatentSpaceNavigator({
    dimension: config?.dimension ?? DEFAULT_PREDICTIVE_CONFIG.latentSpace.dimension,
    maxPatterns: config?.maxPatterns ?? DEFAULT_PREDICTIVE_CONFIG.latentSpace.maxPatterns,
    similarityThreshold: config?.similarityThreshold ?? DEFAULT_PREDICTIVE_CONFIG.latentSpace.similarityThreshold,
    kNeighbors: config?.kNeighbors,
  });
}

// ============================================================================
// Type Alias for Search Results
// ============================================================================

export type { LatentSpaceSearchResult as LatentSpaceSearchResult };
