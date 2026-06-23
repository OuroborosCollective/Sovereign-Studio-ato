/**
 * Signal Proxy Layer
 *
 * ECMAScript Proxy wrapping runtime APIs to intercept and emit micro-signals.
 *
 * @module predictive/signalProxy
 */

import type { Signal, SignalProxyConfig, SignalBuffer, TraceId } from './types';

export interface SignalEmitter {
  (signals: Signal[]): void;
}

let signalSequence = 0;
let fallbackTraceSequence = 0;

function generateSignalId(): string {
  signalSequence = (signalSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `sig-${signalSequence.toString(36).padStart(8, '0')}`;
}

function defaultTraceIdProvider(): TraceId {
  fallbackTraceSequence = (fallbackTraceSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `pred-signal-${fallbackTraceSequence.toString(36).padStart(8, '0')}`;
}

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

export class SignalBufferManager {
  private buffers: Map<string, SignalBuffer> = new Map();
  private maxBufferSize: number;
  private onFlush: SignalEmitter | null = null;

  constructor(maxBufferSize = 1000) {
    this.maxBufferSize = maxBufferSize;
  }

  setEmitter(emitter: SignalEmitter): void {
    this.onFlush = emitter;
  }

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

  push(bufferId: string, signal: Signal): void {
    const buffer = this.getBuffer(bufferId);

    if (buffer.signals.length >= buffer.maxSize) {
      buffer.signals.shift();
      buffer.isFull = true;
    }

    buffer.signals.push(signal);
    if (buffer.signals.length === 1) buffer.oldestTimestamp = signal.timestamp;
    buffer.newestTimestamp = signal.timestamp;
  }

  flush(): Signal[] {
    const allSignals: Signal[] = [];

    for (const buffer of this.buffers.values()) {
      allSignals.push(...buffer.signals);
      buffer.signals = [];
      buffer.oldestTimestamp = 0;
      buffer.newestTimestamp = 0;
      buffer.isFull = false;
    }

    if (allSignals.length > 0 && this.onFlush) this.onFlush(allSignals);
    return allSignals;
  }

  peek(bufferId: string): Signal[] {
    const buffer = this.buffers.get(bufferId);
    return buffer ? [...buffer.signals] : [];
  }

  getTotalCount(): number {
    let total = 0;
    for (const buffer of this.buffers.values()) total += buffer.signals.length;
    return total;
  }

  clear(): void {
    this.buffers.clear();
  }

  getBufferIds(): string[] {
    return Array.from(this.buffers.keys());
  }
}

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

    if (config.flushIntervalMs > 0) {
      this.flushInterval = setInterval(() => {
        this.signalBuffer.flush();
      }, config.flushIntervalMs);
    }
  }

  getInterceptedPaths(): string[] {
    return Array.from(this.interceptedPaths);
  }

  destroy(): void {
    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = null;
    }
  }

  get(target: T, prop: string | symbol, receiver: unknown): unknown {
    if (typeof prop === 'symbol') return Reflect.get(target, prop, receiver);

    const value = Reflect.get(target, prop, receiver);
    const path = `${this.nodeName}.${prop}`;
    this.interceptedPaths.add(path);

    if (typeof value === 'number' && Number.isFinite(value)) {
      const signal = createSignal(this.nodeName, value, this.traceIdProvider(), { property: prop, path });
      this.signalBuffer.push(this.nodeName, signal);
      const buffer = this.signalBuffer.peek(this.nodeName);
      if (buffer.length >= this.config.batchSize) this.signalBuffer.flush();
      this.trackedValues.set(prop, value);
    }

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
    if (typeof prop === 'symbol') return Reflect.set(target, prop, value, receiver);

    const previousValue = this.trackedValues.get(prop);
    const path = `${this.nodeName}.${prop}`;

    if (typeof value === 'number' && Number.isFinite(value) && previousValue !== value) {
      const signal = createSignal(this.nodeName, value, this.traceIdProvider(), {
        property: prop,
        path,
        previousValue,
        changed: true,
      });
      this.signalBuffer.push(this.nodeName, signal);
      this.trackedValues.set(prop, value);
      const buffer = this.signalBuffer.peek(this.nodeName);
      if (buffer.length >= this.config.batchSize) this.signalBuffer.flush();
    }

    return Reflect.set(target, prop, value, receiver);
  }

  has(target: T, prop: string | symbol): boolean {
    return Reflect.has(target, prop);
  }

  ownKeys(target: T): ArrayLike<string | symbol> {
    return Reflect.ownKeys(target);
  }

  getOwnPropertyDescriptor(target: T, prop: string | symbol): PropertyDescriptor | undefined {
    return Reflect.getOwnPropertyDescriptor(target, prop);
  }
}

export interface SignalProxyInstance<T extends object> {
  proxy: T;
  flush(): Signal[];
  peek(nodeId: string): Signal[];
  getInterceptedPaths(): string[];
  destroy(): void;
}

export function createSignalProxy<T extends object>(
  nodeName: string,
  target: T,
  traceIdProvider: () => TraceId,
  buffer: SignalBufferManager,
  config: SignalProxyConfig,
): SignalProxyInstance<T> {
  const handler = new RuntimeStateProxyHandler(nodeName, traceIdProvider, buffer, config);
  const proxy = new Proxy(target, handler);

  return {
    proxy,
    flush: () => buffer.flush(),
    peek: (id: string) => buffer.peek(id),
    getInterceptedPaths: () => handler.getInterceptedPaths(),
    destroy: () => handler.destroy(),
  };
}

export class DirectSignalEmitter {
  private buffer: SignalBufferManager;
  private traceIdProvider: () => TraceId;
  private listeners: Set<(signals: Signal[]) => void> = new Set();

  constructor(maxBufferSize = 1000, traceIdProvider: () => TraceId = defaultTraceIdProvider) {
    this.buffer = new SignalBufferManager(maxBufferSize);
    this.traceIdProvider = traceIdProvider;
    this.buffer.setEmitter((signals) => {
      this.listeners.forEach((listener) => listener(signals));
    });
  }

  emit(node: string, value: number, metadata?: Record<string, unknown>): Signal {
    const signal = createSignal(node, value, this.traceIdProvider(), metadata);
    this.buffer.push(node, signal);
    return signal;
  }

  emitBatch(signals: Omit<Signal, 'id' | 'timestamp' | 'traceId'>[]): Signal[] {
    return signals.map((signal) => this.emit(signal.node, signal.value, signal.metadata));
  }

  subscribe(listener: (signals: Signal[]) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  flush(): Signal[] {
    return this.buffer.flush();
  }

  peek(node: string): Signal[] {
    return this.buffer.peek(node);
  }

  getPendingCount(): number {
    return this.buffer.getTotalCount();
  }

  clear(): void {
    this.buffer.clear();
  }
}

export function createDefaultSignalProxyConfig(): SignalProxyConfig {
  return {
    enabled: true,
    batchSize: 10,
    flushIntervalMs: 50,
    monitoredNodes: [],
    interceptAll: true,
  };
}
