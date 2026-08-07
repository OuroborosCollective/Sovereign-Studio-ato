/**
 * Signal Processor - Bounded iterables with backpressure and replay
 * 
 * @module predictive/signalPipeline/signalProcessor
 */

import {
  SignalTickContract,
  SignalWindowContract,
  SIGNAL_TICK_SCHEMA_ID,
  SIGNAL_WINDOW_SCHEMA_ID,
} from './signalTick';

// ============================================================================
// Content Hash
// ============================================================================

function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16).padStart(8, '0');
}

function generateContentHash(obj: unknown): string {
  const canonical = JSON.stringify(sortObjectKeys(obj));
  return simpleHash(canonical);
}

function sortObjectKeys(obj: unknown): unknown {
  if (obj === null || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(sortObjectKeys);
  
  const sorted: Record<string, unknown> = {};
  const keys = Object.keys(obj as Record<string, unknown>).sort();
  
  for (const key of keys) {
    sorted[key] = sortObjectKeys((obj as Record<string, unknown>)[key]);
  }
  
  return sorted;
}

// ============================================================================
// Backpressure Controller
// ============================================================================

export interface BackpressureConfig {
  maxQueueSize: number;
  highWaterMark: number;
  lowWaterMark: number;
  refillRate: number;
  drainRate: number;
}

export interface BackpressureState {
  queueSize: number;
  paused: boolean;
  lastRefill: number;
  lastDrain: number;
}

export const DEFAULT_BACKPRESSURE_CONFIG: BackpressureConfig = {
  maxQueueSize: 1000,
  highWaterMark: 800,
  lowWaterMark: 200,
  refillRate: 100,
  drainRate: 50,
};

export class BackpressureController {
  private config: BackpressureConfig;
  private state: BackpressureState;

  constructor(config: Partial<BackpressureConfig> = {}) {
    this.config = { ...DEFAULT_BACKPRESSURE_CONFIG, ...config };
    this.state = {
      queueSize: 0,
      paused: false,
      lastRefill: Date.now(),
      lastDrain: Date.now(),
    };
  }

  getState(): BackpressureState {
    return { ...this.state };
  }

  /**
   * Check if signal can be accepted.
   */
  canAccept(): boolean {
    if (this.state.queueSize >= this.config.maxQueueSize) {
      return false;
    }
    
    if (this.state.paused && this.state.queueSize < this.config.lowWaterMark) {
      this.state.paused = false;
    }
    
    // Auto-pause when hitting high water mark
    if (!this.state.paused && this.state.queueSize >= this.config.highWaterMark) {
      this.state.paused = true;
      this.state.lastDrain = Date.now();
    }
    
    return !this.state.paused;
  }

  /**
   * Record signal acceptance.
   */
  accept(): void {
    this.state.queueSize++;
    
    // Check if we should auto-pause
    if (this.state.queueSize >= this.config.highWaterMark && !this.state.paused) {
      this.state.paused = true;
      this.state.lastDrain = Date.now();
    }
  }

  /**
   * Record signal processing completion.
   */
  complete(): void {
    if (this.state.queueSize > 0) {
      this.state.queueSize--;
    }
    
    if (this.state.queueSize < this.config.lowWaterMark && this.state.paused) {
      this.state.paused = false;
    }
  }

  /**
   * Request backpressure pause.
   */
  pause(): void {
    this.state.paused = true;
    this.state.lastDrain = Date.now();
  }

  /**
   * Get load factor (0-1).
   */
  getLoadFactor(): number {
    return this.state.queueSize / this.config.maxQueueSize;
  }

  /**
   * Check if high water mark is reached.
   */
  isHighWaterMark(): boolean {
    return this.state.queueSize >= this.config.highWaterMark;
  }
}

// ============================================================================
// Bounded Signal Iterator
// ============================================================================

export interface SignalIteratorOptions {
  windowDurationMs: number;
  maxTicksPerWindow: number;
  backpressure?: BackpressureController;
  replayFromSequence?: number;
}

export interface SignalBatch {
  window: SignalWindowContract;
  ticks: SignalTickContract[];
}

export class BoundedSignalIterator implements AsyncIterable<SignalBatch> {
  private source: AsyncIterable<SignalTickContract>;
  private options: SignalIteratorOptions;
  private backpressure: BackpressureController;
  private currentWindow: SignalWindowContract | null = null;
  private currentTicks: SignalTickContract[] = [];
  private sequence: number = 0;
  private tick: number = 0;
  private windowStartTime: number = 0;
  private sourceIterator: AsyncIterator<SignalTickContract> | null = null;
  private exhausted: boolean = false;

  constructor(source: AsyncIterable<SignalTickContract>, options: SignalIteratorOptions) {
    this.source = source;
    this.options = options;
    this.backpressure = options.backpressure || new BackpressureController();
    
    if (options.replayFromSequence !== undefined) {
      this.sequence = options.replayFromSequence;
    }
  }

  [Symbol.asyncIterator](): AsyncIterator<SignalBatch> {
    this.sourceIterator = this.source[Symbol.asyncIterator]();
    this.exhausted = false;

    return {
      next: async (): Promise<IteratorResult<SignalBatch>> => {
        // Wait for backpressure clearance
        while (!this.backpressure.canAccept() && !this.exhausted) {
          this.backpressure.pause();
          await new Promise(resolve => setTimeout(resolve, 100));
        }

        // Check if current window is complete
        if (this.shouldCloseWindow()) {
          if (this.currentWindow && this.currentTicks.length > 0) {
            const batch = this.createBatch(true);
            this.resetWindow();
            return { done: false, value: batch };
          }
        }

        // Check if we should emit a window (before getting more ticks)
        if (this.shouldEmitWindow()) {
          const batch = this.createBatch(false);
          this.currentTicks = []; // Reset ticks but keep window
          this.initWindow(); // Start new window
          return { done: false, value: batch };
        }

        // Get next tick
        if (!this.sourceIterator) {
          return { done: true, value: undefined };
        }
        
        const result = await this.sourceIterator.next();
        
        if (result.done) {
          this.exhausted = true;
          // Emit final window if any ticks remain
          if (this.currentTicks.length > 0) {
            const batch = this.createBatch(true);
            this.resetWindow();
            return { done: false, value: batch };
          }
          return { done: true, value: undefined };
        }

        const tick = result.value;
        
        // Initialize window if needed
        if (!this.currentWindow) {
          this.initWindow();
        }

        // Validate tick sequence
        if (tick.sequence <= this.sequence && this.options.replayFromSequence === undefined) {
          // Skip out of order tick in non-replay mode
          return { done: false, value: await this.getNextBatch() };
        }

        this.currentTicks.push(tick);
        this.sequence = tick.sequence;
        this.tick = Math.max(this.tick, tick.tick);
        this.backpressure.accept();

        // Continue fetching more ticks
        return { done: false, value: await this.getNextBatch() };
      },
    };
  }

  private async getNextBatch(): Promise<SignalBatch> {
    // Wait for backpressure clearance
    while (!this.backpressure.canAccept() && !this.exhausted) {
      this.backpressure.pause();
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    // Check if current window is complete
    if (this.shouldCloseWindow()) {
      if (this.currentWindow && this.currentTicks.length > 0) {
        const batch = this.createBatch(true);
        this.resetWindow();
        return batch;
      }
    }

    // Check if we should emit a window
    if (this.shouldEmitWindow()) {
      const batch = this.createBatch(false);
      this.currentTicks = [];
      this.initWindow();
      return batch;
    }

    // Get next tick
    if (!this.sourceIterator) {
      throw new Error('Source iterator not initialized');
    }
    
    const result = await this.sourceIterator.next();
    
    if (result.done) {
      this.exhausted = true;
      if (this.currentTicks.length > 0) {
        const batch = this.createBatch(true);
        this.resetWindow();
        return batch;
      }
      throw new Error('No more batches');
    }

    const tick = result.value;
    
    if (!this.currentWindow) {
      this.initWindow();
    }

    if (tick.sequence <= this.sequence && this.options.replayFromSequence === undefined) {
      return this.getNextBatch();
    }

    this.currentTicks.push(tick);
    this.sequence = tick.sequence;
    this.tick = Math.max(this.tick, tick.tick);
    this.backpressure.accept();

    return this.getNextBatch();
  }

  private shouldCloseWindow(): boolean {
    if (!this.currentWindow) return false;
    
    const now = Date.now();
    const windowAge = now - this.windowStartTime;
    
    return (
      windowAge >= this.options.windowDurationMs ||
      this.currentTicks.length >= this.options.maxTicksPerWindow
    );
  }

  private shouldEmitWindow(): boolean {
    return this.currentTicks.length >= this.options.maxTicksPerWindow;
  }

  private initWindow(): void {
    this.windowStartTime = Date.now();
    
    this.currentWindow = {
      schemaId: SIGNAL_WINDOW_SCHEMA_ID,
      schemaVersion: 'v1',
      id: `window-${this.windowStartTime}`,
      startTick: this.tick,
      endTick: 0,
      startTime: this.windowStartTime,
      windowDurationMs: this.options.windowDurationMs,
      tickCount: 0,
      tickHashes: [],
      contentHash: '',
      schemaHash: '',
      closed: false,
    };
  }

  private createBatch(closed: boolean): SignalBatch {
    if (!this.currentWindow) {
      throw new Error('No active window');
    }

    const window = { ...this.currentWindow };
    window.endTick = this.tick;
    window.tickCount = this.currentTicks.length;
    window.tickHashes = this.currentTicks.map(t => t.contentHash);
    window.contentHash = generateContentHash(window.tickHashes);
    window.schemaHash = generateContentHash({
      schemaId: SIGNAL_WINDOW_SCHEMA_ID,
      fields: Object.keys(window),
    });
    window.closed = closed;

    return { window, ticks: [...this.currentTicks] };
  }

  private resetWindow(): void {
    this.currentWindow = null;
    this.currentTicks = [];
  }
}

// ============================================================================
// Replay Parity Validator
// ============================================================================

export interface ReplayParityResult {
  parity: boolean;
  drift: number;
  replayedTicks: number;
  mismatches: ReplayMismatch[];
}

export interface ReplayMismatch {
  tickId: string;
  originalHash: string;
  replayHash: string;
  field: string;
}

export class ReplayParityValidator {
  private originalTicks: Map<string, SignalTickContract> = new Map();
  private replayTicks: Map<string, SignalTickContract> = new Map();

  /**
   * Register an original tick for comparison.
   */
  registerOriginal(tick: SignalTickContract): void {
    this.originalTicks.set(tick.id, tick);
  }

  /**
   * Register a replayed tick for comparison.
   */
  registerReplay(tick: SignalTickContract): void {
    this.replayTicks.set(tick.id, tick);
  }

  /**
   * Validate replay parity.
   */
  validate(): ReplayParityResult {
    const mismatches: ReplayMismatch[] = [];
    let drift = 0;
    let hasMismatch = false;
    
    // Check for missing replays
    const originalEntries = Array.from(this.originalTicks.entries());
    for (const [id, original] of originalEntries) {
      const replay = this.replayTicks.get(id);
      
      if (!replay) {
        drift++;
        hasMismatch = true;
        continue;
      }

      // Compare content hashes
      if (original.contentHash !== replay.contentHash) {
        mismatches.push({
          tickId: id,
          originalHash: original.contentHash,
          replayHash: replay.contentHash,
          field: 'contentHash',
        });
        hasMismatch = true;
      }

      // Compare sequence numbers
      if (original.sequence !== replay.sequence) {
        mismatches.push({
          tickId: id,
          originalHash: String(original.sequence),
          replayHash: String(replay.sequence),
          field: 'sequence',
        });
        hasMismatch = true;
      }

      // Compare tick values
      if (original.tick !== replay.tick) {
        mismatches.push({
          tickId: id,
          originalHash: String(original.tick),
          replayHash: String(replay.tick),
          field: 'tick',
        });
        hasMismatch = true;
      }
    }

    return {
      parity: !hasMismatch,
      drift,
      replayedTicks: this.replayTicks.size,
      mismatches,
    };
  }

  /**
   * Clear all registered ticks.
   */
  clear(): void {
    this.originalTicks.clear();
    this.replayTicks.clear();
  }
}

// ============================================================================
// Tick Factory
// ============================================================================

export function createSignalTick(
  payload: Record<string, unknown>,
  options: {
    id?: string;
    windowId: string;
    parentIds?: string[];
    isCheckpoint?: boolean;
  }
): SignalTickContract {
  const sequence = Date.now();
  const tick = sequence; // Logical clock = sequence for single-threaded case
  
  return {
    schemaId: SIGNAL_TICK_SCHEMA_ID,
    schemaVersion: 'v1',
    id: options.id || `tick-${sequence}-${simpleHash(JSON.stringify(payload))}`,
    sequence,
    tick,
    timestamp: Date.now(),
    contentHash: generateContentHash(payload),
    schemaHash: generateContentHash({ schemaId: SIGNAL_TICK_SCHEMA_ID, fields: Object.keys(payload) }),
    parents: options.parentIds || [],
    windowId: options.windowId,
    isCheckpoint: options.isCheckpoint || false,
    retryCount: 0,
  };
}
