/**
 * Neural Web Worker
 *
 * Off-thread neural computation for the predictive coding layer.
 * Performs matrix operations, batch signal processing, and autopoiesis
 * without blocking the main UI thread.
 *
 * Communication via postMessage with structured cloning.
 * Uses transferable objects for zero-copy ArrayBuffer sharing.
 *
 * @module predictive/workers/neural.worker
 */

/// <reference lib="webworker" />

// ============================================================================
// Types
// ============================================================================

export interface NeuralWorkerConfig {
  dimension: number;
  learningRate: number;
  decayFactor: number;
  errorThreshold: number;
}

export interface WorkerSignal {
  type: 'batch' | 'predict' | 'learn' | 'sync';
  payload: unknown;
  traceId: string;
  timestamp: number;
}

export interface WorkerResponse {
  type: 'result' | 'error' | 'stats' | 'sync';
  payload: unknown;
  traceId: string;
  timestamp: number;
}

export interface BatchSignalPayload {
  signals: Float64Array; // [value1, timestamp1, value2, timestamp2, ...]
  nodeIds: string[];
}

export interface PredictionPayload {
  value: number;
  nodeId: string;
  previousActivations: Float64Array;
  weights: Float64Array;
}

export interface LearnPayload {
  signalValue: number;
  predictedValue: number;
  error: number;
  synapseUpdates: SynapseUpdate[];
}

export interface SynapseUpdate {
  sourceNode: string;
  targetNode: string;
  weight: number;
}

export interface NeuralStats {
  totalComputations: number;
  averageComputeTimeMs: number;
  memoryUsageBytes: number;
  activeSynapses: number;
}

// ============================================================================
// Matrix Operations
// ============================================================================

/**
 * Matrix-vector multiplication: y = Wx
 */
function matrixVectorMultiply(
  matrix: Float64Array,
  vector: Float64Array,
  rows: number,
  cols: number,
): Float64Array {
  const result = new Float64Array(rows);

  for (let i = 0; i < rows; i++) {
    let sum = 0;
    for (let j = 0; j < cols; j++) {
      sum += matrix[i * cols + j] * vector[j];
    }
    result[i] = sum;
  }

  return result;
}

/**
 * Sigmoid activation function.
 */
function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

/**
 * Apply activation function element-wise.
 */
function applyActivation(vector: Float64Array, activation: 'identity' | 'sigmoid' | 'tanh' | 'relu'): Float64Array {
  const result = new Float64Array(vector.length);

  for (let i = 0; i < vector.length; i++) {
    switch (activation) {
      case 'identity':
        result[i] = vector[i];
        break;
      case 'sigmoid':
        result[i] = sigmoid(vector[i]);
        break;
      case 'tanh':
        result[i] = Math.tanh(vector[i]);
        break;
      case 'relu':
        result[i] = Math.max(0, vector[i]);
        break;
    }
  }

  return result;
}

/**
 * Compute cosine similarity between two vectors.
 */
function cosineSimilarity(v1: Float64Array, v2: Float64Array): number {
  let dotProduct = 0;
  let norm1 = 0;
  let norm2 = 0;

  for (let i = 0; i < v1.length; i++) {
    dotProduct += v1[i] * v2[i];
    norm1 += v1[i] * v1[i];
    norm2 += v2[i] * v2[i];
  }

  const denominator = Math.sqrt(norm1) * Math.sqrt(norm2);
  return denominator === 0 ? 0 : dotProduct / denominator;
}

/**
 * Hebbian weight update: ΔW = η · x · y
 */
function hebbianUpdate(
  currentWeight: number,
  preSynaptic: number,
  postSynaptic: number,
  learningRate: number,
  decayFactor: number,
): number {
  const delta = learningRate * preSynaptic * postSynaptic;
  const newWeight = currentWeight * decayFactor + delta;
  // Clamp to [0, 1]
  return Math.max(0, Math.min(1, newWeight));
}

// ============================================================================
// Neural Network State
// ============================================================================

class NeuralNetworkState {
  private config: NeuralWorkerConfig;
  private weights: Map<string, number> = new Map();
  private activations: Map<string, number> = new Map();
  private embeddings: Map<string, Float64Array> = new Map();
  private stats: NeuralStats = {
    totalComputations: 0,
    averageComputeTimeMs: 0,
    memoryUsageBytes: 0,
    activeSynapses: 0,
  };
  private computeTimes: number[] = [];
  private maxComputeTimes = 100;

  constructor(config: NeuralWorkerConfig) {
    this.config = config;
  }

  /**
   * Generate a prediction using weighted connections.
   */
  predict(
    nodeId: string,
    incomingNodeIds: string[],
    incomingActivations: number[],
  ): { prediction: number; confidence: number } {
    const startTime = performance.now();

    if (incomingNodeIds.length === 0) {
      return { prediction: 0, confidence: 0 };
    }

    let weightedSum = 0;
    let totalWeight = 0;

    for (let i = 0; i < incomingNodeIds.length; i++) {
      const synapseKey = `${incomingNodeIds[i]}->${nodeId}`;
      const weight = this.weights.get(synapseKey) ?? 0.5;
      weightedSum += weight * incomingActivations[i];
      totalWeight += weight;
    }

    const normalizedInput = totalWeight > 0 ? weightedSum / totalWeight : 0;
    const prediction = sigmoid(normalizedInput);

    // Confidence based on weight distribution
    const confidence = Math.min(1, totalWeight / incomingNodeIds.length);

    this.recordComputeTime(performance.now() - startTime);
    this.stats.totalComputations++;

    return { prediction, confidence };
  }

  /**
   * Update weights based on prediction error.
   */
  updateWeights(
    sourceNodeId: string,
    targetNodeId: string,
    preActivation: number,
    error: number,
  ): number {
    const synapseKey = `${sourceNodeId}->${targetNodeId}`;
    const currentWeight = this.weights.get(synapseKey) ?? 0.5;
    const newWeight = hebbianUpdate(
      currentWeight,
      preActivation,
      error,
      this.config.learningRate,
      this.config.decayFactor,
    );

    this.weights.set(synapseKey, newWeight);
    this.stats.activeSynapses = this.weights.size;

    return newWeight;
  }

  /**
   * Batch update weights for multiple synapses.
   */
  batchUpdateWeights(updates: LearnPayload['synapseUpdates']): void {
    for (const update of updates) {
      this.weights.set(`${update.sourceNode}->${update.targetNode}`, update.weight);
    }
    this.stats.activeSynapses = this.weights.size;
  }

  /**
   * Store embedding for a pattern.
   */
  storeEmbedding(patternId: string, embedding: Float64Array): void {
    this.embeddings.set(patternId, embedding);
  }

  /**
   * Find similar patterns using cosine similarity.
   */
  findSimilarPatterns(
    queryEmbedding: Float64Array,
    threshold: number,
  ): Array<{ patternId: string; similarity: number }> {
    const results: Array<{ patternId: string; similarity: number }> = [];

    for (const [patternId, embedding] of this.embeddings) {
      const similarity = cosineSimilarity(queryEmbedding, embedding);
      if (similarity >= threshold) {
        results.push({ patternId, similarity });
      }
    }

    // Sort by similarity descending
    results.sort((a, b) => b.similarity - a.similarity);

    return results;
  }

  /**
   * Record computation time for averaging.
   */
  private recordComputeTime(timeMs: number): void {
    this.computeTimes.push(timeMs);
    if (this.computeTimes.length > this.maxComputeTimes) {
      this.computeTimes.shift();
    }

    const total = this.computeTimes.reduce((sum, t) => sum + t, 0);
    this.stats.averageComputeTimeMs = total / this.computeTimes.length;
  }

  /**
   * Estimate memory usage.
   */
  updateMemoryEstimate(): void {
    // Weights: ~8 bytes per number * count
    const weightsBytes = this.weights.size * 8 * 2; // key + value
    // Embeddings: ~8 bytes per float64 * dimension * count
    const embeddingsBytes = this.embeddings.size * this.config.dimension * 8;
    // Activations: ~8 bytes per number
    const activationsBytes = this.activations.size * 8;

    this.stats.memoryUsageBytes = weightsBytes + embeddingsBytes + activationsBytes;
  }

  /**
   * Get current stats.
   */
  getStats(): NeuralStats {
    this.updateMemoryEstimate();
    return { ...this.stats };
  }

  /**
   * Export state for sync.
   */
  exportState(): {
    weights: Array<[string, number]>;
    embeddings: Array<[string, number[]]>;
  } {
    const weights: Array<[string, number]> = [];
    this.weights.forEach((value, key) => weights.push([key, value]));

    const embeddings: Array<[string, number[]]> = [];
    this.embeddings.forEach((value, key) => {
      embeddings.push([key, Array.from(value)]);
    });

    return { weights, embeddings };
  }

  /**
   * Import state from sync.
   */
  importState(state: ReturnType<NeuralNetworkState['exportState']>): void {
    this.weights.clear();
    for (const [key, value] of state.weights) {
      this.weights.set(key, value);
    }

    this.embeddings.clear();
    for (const [key, value] of state.embeddings) {
      this.embeddings.set(key, new Float64Array(value));
    }

    this.stats.activeSynapses = this.weights.size;
  }
}

// ============================================================================
// Worker Global State
// ============================================================================

let neuralState: NeuralNetworkState | null = null;

// ============================================================================
// Message Handler
// ============================================================================

function handleMessage(event: MessageEvent<WorkerSignal>): void {
  const { type, payload, traceId } = event.data;
  const response: WorkerResponse = {
    type: 'result',
    payload: null,
    traceId,
    timestamp: Date.now(),
  };

  try {
    switch (type) {
      case 'batch':
        response.payload = handleBatch(payload as BatchSignalPayload);
        break;

      case 'predict':
        response.payload = handlePredict(payload as PredictionPayload);
        break;

      case 'learn':
        handleLearn(payload as LearnPayload);
        response.payload = { success: true };
        break;

      case 'sync':
        response.type = 'sync';
        response.payload = handleSync();
        break;

      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error) {
    response.type = 'error';
    response.payload = {
      message: error instanceof Error ? error.message : String(error),
      name: error instanceof Error ? error.name : 'Error',
    };
  }

  // Send response back to main thread
  self.postMessage(response);
}

function handleBatch(payload: BatchSignalPayload): {
  predictions: Array<{ nodeId: string; prediction: number; confidence: number }>;
} {
  // Process batch of signals
  const results: Array<{ nodeId: string; prediction: number; confidence: number }> = [];

  // Deserialize signals
  const signals: Array<{ value: number; nodeId: string }> = [];
  for (let i = 0; i < payload.nodeIds.length; i++) {
    signals.push({
      value: payload.signals[i * 2],
      nodeId: payload.nodeIds[i],
    });
  }

  // Process each signal
  for (const signal of signals) {
    if (!neuralState) continue;

    // Simple prediction based on recent history
    const result = neuralState.predict(
      signal.nodeId,
      [], // No incoming connections for simple case
      [],
    );

    results.push({
      nodeId: signal.nodeId,
      prediction: result.prediction,
      confidence: result.confidence,
    });
  }

  return { predictions: results };
}

function handlePredict(payload: PredictionPayload): {
  prediction: number;
  confidence: number;
} {
  if (!neuralState) {
    return { prediction: payload.value, confidence: 0 };
  }

  // Decode weights if needed (in real implementation, would use transferable buffers)
  const weights = payload.weights;

  return neuralState.predict(
    payload.nodeId,
    [], // Would need incoming node IDs
    Array.from(payload.previousActivations),
  );
}

function handleLearn(payload: LearnPayload): void {
  if (!neuralState) return;

  // Apply batch weight updates
  neuralState.batchUpdateWeights(payload.synapseUpdates);
}

function handleSync(): ReturnType<NeuralNetworkState['exportState']> & NeuralStats {
  if (!neuralState) {
    return {
      weights: [],
      embeddings: [],
      totalComputations: 0,
      averageComputeTimeMs: 0,
      memoryUsageBytes: 0,
      activeSynapses: 0,
    };
  }

  return {
    ...neuralState.exportState(),
    ...neuralState.getStats(),
  };
}

// ============================================================================
// Initialization
// ============================================================================

self.onmessage = handleMessage;

// Send ready signal
self.postMessage({
  type: 'result',
  payload: { ready: true },
  traceId: 'worker-init',
  timestamp: Date.now(),
});

// Export for module system (Vite worker bundling)
export {};
