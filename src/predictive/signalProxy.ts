/**
 * Signal Proxy Layer
 *
 * ECMAScript Proxy wrapping runtime APIs to intercept and emit micro-signals.
 * Acts as a sensor layer that captures bottom-up signals from the runtime.
 *
 * @module predictive/signalProxy
 */

import type {
  Signal,
  SignalProxyConfig,
  SignalBuffer,
  TraceId,
} from './types';

import {
  DEFAULT_PREDICTIVE_CONFIG,
  type PredictiveLayerConfig,
} from './types';

// ============================================================================
// Signal Emitter Interface
// ============================================================================

/**
 * Callback interface for signal emission.
 * Implementations receive signals for further processing.
 */
export interface SignalEmitter {
  (signals: Signal[]): void;
}

// ============================================================================
// Signal Proxy Core
// ============================================================================

let signalSequence = 0;

function generateSignalId(): string {
  signalSequence = (signalSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `sig-${signalSequence.toString(36).padStart(8, '0')}`;
}

/**
 * Creates a micro-signal from runtime state.
 */
function createSignal(
  node: string,
  value: number,
  traceId: TraceId,
  metadata?: Record<string, unknown>,
): Signal {
  return {
    id: generateSignalId(),
    node,
    value,
    timestamp: Date.now(),
    traceId,
    metadata,
  };
}

// ============================================================================
// Signal Buffer (Circular Buffer)
// ============================================================================

/**
 * Signal buffer with circular storage for memory efficiency.
 */
export class SignalBufferManager {
  private buffers: Map<string, SignalBuffer> = new Map();
  private maxBufferSize: number;
  private onFlush: SignalEmitter | null = null;

  constructor(maxBufferSize: number = 1000) {
    this.maxBufferSize = maxBufferSize;
  }

  /**
   * Set the signal emitter callback.
   */
  setEmitter(emitter: SignalEmitter): void {
    this.onFlush = emitter;
  }

  /**
   * Get or create a buffer for a specific node.
   */
  getBuffer(bufferId: string): SignalBuffer {
    let buffer = this.buffers.get(bufferId);
    if (!buffer) {
      buffer = this.createBuffer(bufferId);
      this.buffers.set(bufferId, buffer);
    }
    return buffer;
  }

  private createBuffer(id: string): SignalBuffer {
    return {
      id,
      signals: [],
      maxSize: this.maxBufferSize,
      oldestTimestamp: 0,
      newestTimestamp: 0,
      isFull: false,
    };
  }

  /**
   * Add a signal to the buffer.
   * Uses circular buffer behavior when full.
   */
  push(bufferId: string, signal: Signal): void {
    const buffer = this.getBuffer(bufferId);

    if (buffer.signals.length >= buffer.maxSize) {
      // Circular: remove oldest signal
      buffer.signals.shift();
      buffer.isFull = true;
    }

    buffer.signals.push(signal);

    if (buffer.signals.length === 1) {
      buffer.oldestTimestamp = signal.timestamp;
    }
    buffer.newestTimestamp = signal.timestamp;
  }

  /**
   * Flush all buffers and return accumulated signals.
   */
  flush(): Signal[] {
    const allSignals: Signal[] = [];

    for (const buffer of this.buffers.values()) {
      allSignals.push(...buffer.signals);
      buffer.signals = [];
      buffer.oldestTimestamp = 0;
      buffer.newestTimestamp = 0;
      buffer.isFull = false;
    }

    if (allSignals.length > 0 && this.onFlush) {
      this.onFlush(allSignals);
    }

    return allSignals;
  }

  /**
   * Get signals from a specific buffer without flushing.
   */
  peek(bufferId: string): Signal[] {
    const buffer = this.buffers.get(bufferId);
    return buffer ? [...buffer.signals] : [];
  }

  /**
   * Get total signal count across all buffers.
   */
  getTotalCount(): number {
    let total = 0;
    for (const buffer of this.buffers.values()) {
      total += buffer.signals.length;
    }
    return total;
  }

  /**
   * Clear all buffers.
   */
  clear(): void {
    this.buffers.clear();
  }

  /**
   * Get all buffer IDs.
   */
  getBufferIds(): string[] {
    return Array.from(this.buffers.keys());
  }
}

// ============================================================================
// Runtime State Proxy
// ============================================================================

/**
 * Proxy handler for intercepting runtime state access.
 */
class RuntimeStateProxyHandler<T extends object> implements ProxyHandler<T> {
  private nodeName: string;
  private traceIdProvider: () => TraceId;
  private signalBuffer: SignalBufferManager;
  private config: SignalProxyConfig;
  private trackedValues: Map<string, unknown> = new Map();
  private flushInterval: ReturnType<typeof setInterval> | null = null;
  private interceptedPaths: Set<string> = new Set();

  constructor(
    nodeName: string,
    traceIdProvider: () => TraceId,
    signalBuffer: SignalBufferManager,
    config: SignalProxyConfig,
  ) {
    this.nodeName = nodeName;
    this.traceIdProvider = traceIdProvider;
    this.signalBuffer = signalBuffer;
    this.config = config;

    // Start flush interval if configured
    if (config.flushIntervalMs > 0) {
      this.flushInterval = setInterval(() => {
        this.signalBuffer.flush();
      }, config.flushIntervalMs);
    }
  }

  /**
   * Get the list of intercepted property paths.
   */
  getInterceptedPaths(): string[] {
    return Array.from(this.interceptedPaths);
  }

  /**
   * Cleanup resources.
   */
  destroy(): void {
    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = null;
    }
  }

  get(target: T, prop: string | symbol, receiver: unknown): unknown {
    if (typeof prop === 'symbol') {
      return Reflect.get(target, prop, receiver);
    }

    const value = Reflect.get(target, prop, receiver);
    const path = `${this.nodeName}.${prop}`;

    // Track this path as intercepted
    this.interceptedPaths.add(path);

    // Emit signal for numeric values
    if (typeof value === 'number' && Number.isFinite(value)) {
      const signal = createSignal(
        this.nodeName,
        value,
        this.traceIdProvider(),
        { property: prop, path },
      );

      this.signalBuffer.push(this.nodeName, signal);

      // Check if we should flush based on batch size
      const buffer = this.signalBuffer.peek(this.nodeName);
      if (buffer.length >= this.config.batchSize) {
        this.signalBuffer.flush();
      }

      // Track value for change detection
      this.trackedValues.set(prop, value);
    }

    // Return proxy for nested objects
    if (typeof value === 'object' && value !== null) {
      return new Proxy(value as object, new RuntimeStateProxyHandler(
        `${this.nodeName}.${prop}`,
        this.traceIdProvider,
        this.signalBuffer,
        { ...this.config, interceptAll: true },
      ));
    }

    return value;
  }

  set(target: T, prop: string | symbol, value: unknown, receiver: unknown): boolean {
    if (typeof prop === 'symbol') {
      return Reflect.set(target, prop, value, receiver);
    }

    const previousValue = this.trackedValues.get(prop);
    const path = `${this.nodeName}.${prop}`;

    // Emit signal on value change
    if (typeof value === 'number' && Number.isFinite(value)) {
      if (previousValue !== value) {
        const signal = createSignal(
          this.nodeName,
          value,
          this.traceIdProvider(),
          {
            property: prop,
            path,
            previousValue,
            changed: true,
          },
        );

        this.signalBuffer.push(this.nodeName, signal);
        this.trackedValues.set(prop, value);

        // Flush on significant change
        const buffer = this.signalBuffer.peek(this.nodeName);
        if (buffer.length >= this.config.batchSize) {
          this.signalBuffer.flush();
        }
      }
    }

    return Reflect.set(target, prop, value, receiver);
  }

  has(target: T, prop: string | symbol): boolean {
    return Reflect.has(target, prop);
  }

  ownKeys(target: T): ArrayLike<string | symbol> {
    return Reflect.ownKeys(target);
  }

  getOwnPropertyDescriptor(
    target: T,
    prop: string | symbol,
  ): PropertyDescriptor | undefined {
    return Reflect.getOwnPropertyDescriptor(target, prop);
  }
}

// ============================================================================
// Signal Proxy Factory
// ============================================================================

export interface SignalProxyInstance<T extends object> {
  proxy: T;
  flush(): Signal[];
  peek(nodeId: string): Signal[];
  getInterceptedPaths(): string[];
  destroy(): void;
}

/**
 * Creates a proxy for intercepting runtime state access.
 *
 * @example
 * ```typescript
 * const traceIdProvider = () => generateTraceId();
 * const buffer = new SignalBufferManager(1000);
 *
 * const { proxy, flush, destroy } = createSignalProxy<RuntimeState>(
 *   'runtime',
 *   { node: runtimeState },
 *   traceIdProvider,
 *   buffer,
 *   { enabled: true, batchSize: 10, flushIntervalMs: 50, monitoredNodes: ['runtime'], interceptAll: true }
 * );
 * ```
 */
export function createSignalProxy<T extends object>(
  nodeName: string,
  target: T,
  traceIdProvider: () => TraceId,
  buffer: SignalBufferManager,
  config: SignalProxyConfig,
): SignalProxyInstance<T> {
  const handler = new RuntimeStateProxyHandler(
    nodeName,
    traceIdProvider,
    buffer,
    config,
  );

  const proxy = new Proxy(target, handler);

  return {
    proxy,
    flush: () => buffer.flush(),
    peek: (id: string) => buffer.peek(id),
    getInterceptedPaths: () => handler.getInterceptedPaths(),
    destroy: () => handler.destroy(),
  };
}

// ============================================================================
// Simple Signal Emitter (for direct use)
// ============================================================================

/**
 * Direct signal emitter for runtime events.
 */
export class DirectSignalEmitter {
  private buffer: SignalBufferManager;
  private traceIdProvider: () => TraceId;
  private listeners: Set<(signals: Signal[]) => void> = new Set();

  constructor(
    maxBufferSize: number = 1000,
    traceIdProvider: () => TraceId,
  ) {
    this.buffer = new SignalBufferManager(maxBufferSize);
    this.traceIdProvider = traceIdProvider;

    this.buffer.setEmitter((signals) => {
      this.listeners.forEach((listener) => listener(signals));
    });
  }

  /**
   * Emit a signal directly.
   */
  emit(
    node: string,
    value: number,
    metadata?: Record<string, unknown>,
  ): Signal {
    const signal = createSignal(
      node,
      value,
      this.traceIdProvider(),
      metadata,
    );

    this.buffer.push(node, signal);
    return signal;
  }

  /**
   * Emit multiple signals at once.
   */
  emitBatch(signals: Omit<Signal, 'id' | 'timestamp' | 'traceId'>[]): Signal[] {
    return signals.map((s) =>
      this.emit(s.node, s.value, s.metadata),
    );
  }

  /**
   * Subscribe to signal batches.
   */
  subscribe(listener: (signals: Signal[]) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * Flush pending signals.
   */
  flush(): Signal[] {
    return this.buffer.flush();
  }

  /**
   * Get pending signals without flushing.
   */
  peek(node: string): Signal[] {
    return this.buffer.peek(node);
  }

  /**
   * Get total pending signal count.
   */
  getPendingCount(): number {
    return this.buffer.getTotalCount();
  }

  /**
   * Clear all pending signals.
   */
  clear(): void {
    this.buffer.clear();
  }
}

// ============================================================================
// Default Configuration
// ============================================================================

export function createDefaultSignalProxyConfig(
  overrides?: Partial<SignalProxyConfig>,
): SignalProxyConfig {
  return {
    enabled: true,
    batchSize: DEFAULT_PREDICTIVE_CONFIG.signal.batchSize,
    flushIntervalMs: DEFAULT_PREDICTIVE_CONFIG.signal.flushIntervalMs,
    monitoredNodes: [],
    interceptAll: true,
    ...overrides,
  };
}
