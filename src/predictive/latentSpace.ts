/**
 * Latent Space Navigator
 *
 * Deterministic vector store with cosine similarity search for predictive
 * runtime patterns. No random sampling is used in the live path.
 *
 * @module predictive/latentSpace
 */

import type { PatternEmbedding, SimilarityMatch } from './types';

const DEFAULT_DIMENSION = 64;
const DEFAULT_MAX_PATTERNS = 10000;
const DEFAULT_SIMILARITY_THRESHOLD = 0.7;
const DEFAULT_K_NEIGHBORS = 10;

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

function stableHash(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

export class LatentSpaceNavigator {
  private patterns: Map<string, PatternEmbedding> = new Map();
  private dimension: number;
  private maxPatterns: number;
  private similarityThreshold: number;
  private kNeighbors: number;
  private nodeIndex: Map<string, Set<string>> = new Map();
  private insertionOrder: string[] = [];

  constructor(config: Partial<LatentSpaceConfig> = {}) {
    this.dimension = config.dimension ?? DEFAULT_DIMENSION;
    this.maxPatterns = config.maxPatterns ?? DEFAULT_MAX_PATTERNS;
    this.similarityThreshold = config.similarityThreshold ?? DEFAULT_SIMILARITY_THRESHOLD;
    this.kNeighbors = config.kNeighbors ?? DEFAULT_K_NEIGHBORS;
  }

  getPatternCount(): number {
    return this.patterns.size;
  }

  getConfig(): LatentSpaceConfig {
    return {
      dimension: this.dimension,
      maxPatterns: this.maxPatterns,
      similarityThreshold: this.similarityThreshold,
      kNeighbors: this.kNeighbors,
    };
  }

  addPattern(pattern: PatternEmbedding): boolean {
    if (pattern.embedding.length !== this.dimension) return false;

    while (this.patterns.size >= this.maxPatterns && this.insertionOrder.length > 0) {
      const oldestId = this.insertionOrder.shift();
      if (oldestId) this.evictPattern(oldestId);
    }

    this.patterns.set(pattern.id, {
      ...pattern,
      norm: this.computeNorm(pattern.embedding),
    });

    if (!this.nodeIndex.has(pattern.node)) this.nodeIndex.set(pattern.node, new Set());
    this.nodeIndex.get(pattern.node)?.add(pattern.id);
    this.insertionOrder.push(pattern.id);
    return true;
  }

  evictPattern(patternId: string): void {
    const pattern = this.patterns.get(patternId);
    if (!pattern) return;

    const nodePatterns = this.nodeIndex.get(pattern.node);
    if (nodePatterns) {
      nodePatterns.delete(patternId);
      if (nodePatterns.size === 0) this.nodeIndex.delete(pattern.node);
    }

    this.patterns.delete(patternId);
    const orderIndex = this.insertionOrder.indexOf(patternId);
    if (orderIndex !== -1) this.insertionOrder.splice(orderIndex, 1);
  }

  findSimilar(
    value: number,
    node: string,
    options: LatentSpaceSearchOptions = {},
  ): SimilarityMatch | null {
    const k = options.k ?? this.kNeighbors;
    const threshold = options.threshold ?? this.similarityThreshold;
    const queryEmbedding = this.createQueryEmbedding(value);
    const queryNorm = this.computeNorm(queryEmbedding);
    const candidates = this.getCandidates(node, options.nodeFilter);
    if (candidates.length === 0) return null;

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

    if (similarities.length === 0) return null;
    similarities.sort((a, b) => b.score - a.score || a.patternId.localeCompare(b.patternId));

    for (const match of similarities.slice(0, k)) {
      const pattern = this.patterns.get(match.patternId);
      if (!pattern) continue;
      pattern.matchCount += 1;
      pattern.avgConfidence = (pattern.avgConfidence * (pattern.matchCount - 1) + match.score) / pattern.matchCount;
    }

    return similarities[0];
  }

  findTopK(
    value: number,
    node: string,
    k: number = this.kNeighbors,
    options: LatentSpaceSearchOptions = {},
  ): SimilarityMatch[] {
    const threshold = options.threshold ?? -1;
    const queryEmbedding = this.createQueryEmbedding(value);
    const queryNorm = this.computeNorm(queryEmbedding);
    const candidates = this.getCandidates(node, options.nodeFilter);
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

    similarities.sort((a, b) => b.score - a.score || a.patternId.localeCompare(b.patternId));
    return similarities.slice(0, k);
  }

  getPattern(patternId: string): PatternEmbedding | undefined {
    return this.patterns.get(patternId);
  }

  getPatternsForNode(node: string): PatternEmbedding[] {
    const patternIds = this.nodeIndex.get(node);
    if (!patternIds) return [];
    return Array.from(patternIds)
      .map((id) => this.patterns.get(id))
      .filter((pattern): pattern is PatternEmbedding => pattern !== undefined);
  }

  getAllPatterns(): PatternEmbedding[] {
    return Array.from(this.patterns.values());
  }

  cosineSimilarity(v1: number[], v2: number[], norm1?: number, norm2?: number): number {
    if (v1.length !== v2.length) throw new Error('Vector dimension mismatch');
    const n1 = norm1 ?? this.computeNorm(v1);
    const n2 = norm2 ?? this.computeNorm(v2);
    if (n1 === 0 || n2 === 0) return 0;

    let dotProduct = 0;
    for (let index = 0; index < v1.length; index += 1) {
      dotProduct += v1[index] * v2[index];
    }

    return dotProduct / (n1 * n2);
  }

  computeNorm(vector: number[]): number {
    let sum = 0;
    for (const value of vector) sum += value * value;
    return Math.sqrt(sum);
  }

  private createQueryEmbedding(value: number): number[] {
    const embedding: number[] = [];
    for (let index = 0; index < this.dimension; index += 1) {
      const s = value * (index + 1) * 7919;
      embedding.push((Math.sin(s) + 1) / 2);
    }
    return embedding;
  }

  private getCandidates(node: string, nodeFilter?: string): PatternEmbedding[] {
    if (nodeFilter) return this.getPatternsForNode(nodeFilter);

    const sameNode = this.getPatternsForNode(node);
    const crossNode = this.getAllPatterns()
      .filter((pattern) => pattern.node !== node)
      .filter((pattern) => stableHash(`${node}:${pattern.id}`) % 10 === 0);

    return [...sameNode, ...crossNode];
  }

  computeCorrelationMatrix(node?: string): Map<string, Map<string, number>> {
    const patterns = node ? this.getPatternsForNode(node) : this.getAllPatterns();
    const correlations = new Map<string, Map<string, number>>();

    for (const first of patterns) {
      const row = new Map<string, number>();
      for (const second of patterns) {
        row.set(
          second.id,
          first.id === second.id ? 1 : this.cosineSimilarity(first.embedding, second.embedding, first.norm, second.norm),
        );
      }
      correlations.set(first.id, row);
    }

    return correlations;
  }

  clear(): void {
    this.patterns.clear();
    this.nodeIndex.clear();
    this.insertionOrder = [];
  }

  estimateMemoryUsage(): number {
    const bytesPerPattern = 50 + this.dimension * 8 + 100;
    return this.patterns.size * bytesPerPattern;
  }

  exportPatterns(): PatternEmbedding[] {
    return this.getAllPatterns();
  }

  importPatterns(patterns: PatternEmbedding[]): number {
    let imported = 0;
    for (const pattern of patterns) {
      if (this.addPattern(pattern)) imported += 1;
    }
    return imported;
  }
}

export function createLatentSpace(config?: Partial<LatentSpaceConfig>): LatentSpaceNavigator {
  return new LatentSpaceNavigator(config);
}
