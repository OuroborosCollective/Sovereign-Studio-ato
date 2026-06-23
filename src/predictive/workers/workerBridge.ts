/**
 * Neural Worker Bridge
 *
 * Connects the main thread to the neural web worker.
 * Buffers signals and sends batched updates to the worker every N ms.
 * Falls back to main-thread processing if worker is unavailable.
 *
 * @module predictive/workers/workerBridge
 */

import type {
  Signal,
  TraceId,
  Prediction,
  WeightUpdateResult,
} from '../types';

import { PredictiveLayer } from '../predictiveLayer';

// ============================================================================
// Types
// ============================================================================

export interface WorkerBridgeConfig {
  /** Buffer signals for batch processing */
  batchSize: number;
  /** Flush interval in milliseconds */
  flushIntervalMs: number;
  /** Enable worker (disable for fallback) */
  enabled: boolean;
  /** Fallback to main thread if worker fails */
  fallbackToMainThread: boolean;
}

export interface WorkerMessage {
  type: 'batch' | 'predict' | 'learn' | 'sync' | 'config';
  payload: unknown;
  traceId: string;
  timestamp: number;
}

export interface WorkerResult {
  type: 'result' | 'error' | 'stats' | 'sync';
  payload: unknown;
  traceId: string;
  timestamp: number;
}

// ============================================================================
// Default Configuration
// ============================================================================

const DEFAULT_CONFIG: WorkerBridgeConfig = {
  batchSize: 50,
  flushIntervalMs: 50,
  enabled: true,
  fallbackToMainThread: true,
};

// ============================================================================
// Signal Batcher
// ============================================================================

interface BufferedSignal {
  signal: Signal;
  traceId: TraceId;
}

/**
 * Batches signals for efficient worker communication.
 */
class SignalBatcher {
  private buffer: BufferedSignal[] = [];
  private maxSize: number;

  constructor(maxSize: number = 50) {
    this.maxSize = maxSize;
  }

  /**
   * Add a signal to the batch.
   */
  push(signal: Signal, traceId: TraceId): void {
    this.buffer.push({ signal, traceId });

    // Auto-flush when buffer is full
    if (this.buffer.length >= this.maxSize) {
      this.flush();
    }
  }

  /**
   * Get and clear the current batch.
   */
  flush(): BufferedSignal[] {
    const batch = [...this.buffer];
    this.buffer = [];
    return batch;
  }

  /**
   * Get current buffer size without clearing.
   */
  size(): number {
    return this.buffer.length;
  }

  /**
   * Clear the buffer.
   */
  clear(): void {
    this.buffer = [];
  }
}

// ============================================================================
// Neural Worker Bridge
// ============================================================================

let bridgeSequence = 0;

function generateBridgeId(): string {
  bridgeSequence = (bridgeSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `bridge-${bridgeSequence.toString(36).padStart(8, '0')}`;
}

/**
 * Bridge between main thread and neural web worker.
 */
export class NeuralWorkerBridge {
  private config: WorkerBridgeConfig;
  private worker: Worker | null = null;
  private batcher: SignalBatcher;
  private flushInterval: ReturnType<typeof setInterval> | null = null;
  private isReady: boolean = false;
  private pendingCallbacks: Map<string, (result: WorkerResult) => void> = new Map();
  private fallbackMode: boolean = false;
  private predictiveLayer: PredictiveLayer | null = null;
  private bridgeId: string;
  private onStatsCallback: ((stats: WorkerStats) => void) | null = null;

  constructor(
    config: Partial<WorkerBridgeConfig> = {},
    predictiveLayer?: PredictiveLayer,
  ) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.batcher = new SignalBatcher(this.config.batchSize);
    this.predictiveLayer = predictiveLayer ?? null;
    this.bridgeId = generateBridgeId();
  }

  /**
   * Initialize the worker.
   */
  async start(): Promise<boolean> {
    if (!this.config.enabled) {
      console.log(`[NeuralWorkerBridge:${this.bridgeId}] Worker disabled, using main thread`);
      this.fallbackMode = true;
      return true;
    }

    try {
      // Create worker using Vite worker syntax
      this.worker = new Worker(
        new URL('./neural.worker.ts', import.meta.url),
        { type: 'module' },
      );

      // Set up message handler
      this.worker.onmessage = this.handleWorkerMessage.bind(this);
      this.worker.onerror = this.handleWorkerError.bind(this);

      // Start flush interval
      this.flushInterval = setInterval(() => {
        this.flushBatch();
      }, this.config.flushIntervalMs);

      // Wait for ready signal
      await this.waitForReady();

      console.log(`[NeuralWorkerBridge:${this.bridgeId}] Worker started successfully`);
      return true;
    } catch (error) {
      console.warn(`[NeuralWorkerBridge:${this.bridgeId}] Worker failed to start:`, error);

      if (this.config.fallbackToMainThread) {
        console.log(`[NeuralWorkerBridge:${this.bridgeId}] Falling back to main thread`);
        this.fallbackMode = true;
        return true;
      }

      return false;
    }
  }

  /**
   * Stop the worker.
   */
  stop(): void {
    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = null;
    }

    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
    }

    this.isReady = false;
    this.batcher.clear();
    this.pendingCallbacks.clear();
  }

  /**
   * Wait for worker to be ready.
   */
  private async waitForReady(): Promise<void> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Worker ready timeout'));
      }, 5000);

      const handler = (event: MessageEvent<WorkerResult>) => {
        if (event.data.payload && typeof event.data.payload === 'object' && 'ready' in event.data.payload) {
          clearTimeout(timeout);
          this.isReady = true;
          this.worker?.removeEventListener('message', handler);
          resolve();
        }
      };

      this.worker?.addEventListener('message', handler);
    });
  }

  /**
   * Handle messages from worker.
   */
  private handleWorkerMessage(event: MessageEvent<WorkerResult>): void {
    const { type, payload, traceId } = event.data;

    if (type === 'result' && payload && typeof payload === 'object' && 'ready' in payload) {
      return; // Ignore ready signal
    }

    // Check if there's a pending callback
    const callback = this.pendingCallbacks.get(traceId);
    if (callback) {
      this.pendingCallbacks.delete(traceId);
      callback(event.data);
    }
  }

  /**
   * Handle worker errors.
   */
  private handleWorkerError(error: ErrorEvent): void {
    console.error(`[NeuralWorkerBridge:${this.bridgeId}] Worker error:`, error);

    if (this.config.fallbackToMainThread && !this.fallbackMode) {
      console.log(`[NeuralWorkerBridge:${this.bridgeId}] Switching to fallback mode`);
      this.fallbackMode = true;
      this.stop();
    }
  }

  /**
   * Send a message to the worker.
   */
  private sendToWorker(message: WorkerMessage): Promise<WorkerResult> {
    return new Promise((resolve, reject) => {
      if (!this.worker || this.fallbackMode) {
        reject(new Error('Worker not available'));
        return;
      }

      this.pendingCallbacks.set(message.traceId, resolve);

      const timeout = setTimeout(() => {
        this.pendingCallbacks.delete(message.traceId);
        reject(new Error('Worker message timeout'));
      }, 10000);

      // Remove timeout on response
      const originalResolve = resolve;
      resolve = (result: WorkerResult) => {
        clearTimeout(timeout);
        originalResolve(result);
      };
    });
  }

  /**
   * Emit a signal to be batched and processed.
   */
  emitSignal(signal: Signal, traceId: TraceId): void {
    if (this.fallbackMode) {
      // Process directly on main thread
      this.processOnMainThread(signal, traceId);
      return;
    }

    this.batcher.push(signal, traceId);
  }

  /**
   * Flush the current batch to the worker.
   */
  private async flushBatch(): Promise<void> {
    if (this.fallbackMode) return;

    const batch = this.batcher.flush();
    if (batch.length === 0) return;

    try {
      const traceId = `batch-${this.bridgeId}-${Date.now().toString(36)}`;
      
      // Convert to serializable format
      const payload = {
        signals: batch.map((b) => ({
          id: b.signal.id,
          node: b.signal.node,
          value: b.signal.value,
          timestamp: b.signal.timestamp,
        })),
      };

      const result = await this.sendToWorker({
        type: 'batch',
        payload,
        traceId,
        timestamp: Date.now(),
      });

      // Handle result if needed
      if (result.payload) {
        this.onStatsCallback?.(result.payload as WorkerStats);
      }
    } catch (error) {
      console.error(`[NeuralWorkerBridge:${this.bridgeId}] Batch flush failed:`, error);
    }
  }

  /**
   * Process signal on main thread (fallback mode).
   */
  private processOnMainThread(signal: Signal, traceId: TraceId): void {
    if (!this.predictiveLayer) return;

    // Forward to predictive layer
    this.predictiveLayer.processSignal(signal);
  }

  /**
   * Request sync from worker.
   */
  async sync(): Promise<WorkerStats | null> {
    if (this.fallbackMode || !this.worker) {
      return null;
    }

    try {
      const traceId = `sync-${this.bridgeId}-${Date.now().toString(36)}`;
      const result = await this.sendToWorker({
        type: 'sync',
        payload: {},
        traceId,
        timestamp: Date.now(),
      });

      return result.payload as WorkerStats;
    } catch (error) {
      console.error(`[NeuralWorkerBridge:${this.bridgeId}] Sync failed:`, error);
      return null;
    }
  }

  /**
   * Set callback for stats updates.
   */
  onStats(callback: (stats: WorkerStats) => void): void {
    this.onStatsCallback = callback;
  }

  /**
   * Check if worker is available.
   */
  isWorkerAvailable(): boolean {
    return !this.fallbackMode && this.worker !== null && this.isReady;
  }

  /**
   * Check if in fallback mode.
   */
  isFallbackMode(): boolean {
    return this.fallbackMode;
  }
}

// ============================================================================
// Worker Stats
// ============================================================================

export interface WorkerStats {
  totalComputations: number;
  averageComputeTimeMs: number;
  memoryUsageBytes: number;
  activeSynapses: number;
}

// ============================================================================
// Factory
// ============================================================================

/**
 * Create a worker bridge with configuration.
 */
export function createWorkerBridge(
  config?: Partial<WorkerBridgeConfig>,
  predictiveLayer?: PredictiveLayer,
): NeuralWorkerBridge {
  return new NeuralWorkerBridge(config, predictiveLayer);
}
