import { configureStore, type Middleware } from '@reduxjs/toolkit';
import { Preferences } from '@capacitor/preferences';

import billingReducer from '../features/billing/billingSlice';
import canvasReducer, { addObject } from '../features/canvas/canvasSlice';
import ouroborosReducer from '../features/ouroboros/ouroborosSlice';

export const SOVEREIGN_STORE_ARCHITECTURE_VERSION = 2 as const;
export const SOVEREIGN_CANVAS_PERSISTENCE_KEY = 'sovereign_canvas_state_mirror';

export const AI_CANVAS_BRIDGE_ACTION_TYPES = [
  'ai/setGeneratedContent',
  'ai/responseReceived',
] as const;

const AI_CANVAS_BRIDGE_ACTION_TYPE_SET = new Set<string>(AI_CANVAS_BRIDGE_ACTION_TYPES);
const STORE_EVENT_LIMIT = 50;

interface ReduxActionLike {
  type: string;
  payload?: unknown;
}

interface CanvasMirrorRootState {
  canvas?: unknown;
}

export type SovereignStoreRuntimeEventKind =
  | 'ai-canvas-bridge'
  | 'canvas-persist-queued'
  | 'canvas-persist-written'
  | 'canvas-persist-skipped'
  | 'canvas-persist-failed'
  | 'canvas-persist-cleared'
  | 'canvas-persist-read-failed'
  | 'canvas-persist-serialize-failed';

export interface SovereignStoreRuntimeEvent {
  sequence: number;
  kind: SovereignStoreRuntimeEventKind;
  message: string;
  actionType?: string;
}

export interface CanvasPersistenceMirrorStatus {
  architectureVersion: typeof SOVEREIGN_STORE_ARCHITECTURE_VERSION;
  key: string;
  pending: boolean;
  writeInFlight: boolean;
  scheduled: boolean;
  writeCount: number;
  skippedWriteCount: number;
  failedWriteCount: number;
  queuedSequence: number | null;
  writtenSequence: number | null;
  lastValueBytes: number | null;
  lastWrittenBytes: number | null;
  lastError: string | null;
}

export interface SovereignStoreRuntimeStatus {
  architectureVersion: typeof SOVEREIGN_STORE_ARCHITECTURE_VERSION;
  canvasMirror: CanvasPersistenceMirrorStatus;
  events: SovereignStoreRuntimeEvent[];
  healthy: boolean;
  summary: string;
}

function isReduxActionLike(action: unknown): action is ReduxActionLike {
  return (
    typeof action === 'object' &&
    action !== null &&
    typeof (action as { type?: unknown }).type === 'string'
  );
}

function shouldBridgeAiActionToCanvas(action: ReduxActionLike): boolean {
  return (
    AI_CANVAS_BRIDGE_ACTION_TYPE_SET.has(action.type) &&
    action.payload !== null &&
    action.payload !== undefined
  );
}

function shouldMirrorCanvasAction(action: ReduxActionLike): boolean {
  return action.type.startsWith('canvas/');
}

function errorToMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function safeSerializeCanvasState(canvas: unknown): string | null {
  try {
    return JSON.stringify(canvas);
  } catch {
    return null;
  }
}

function byteLength(value: string): number {
  return new Blob([value]).size;
}

function defer(callback: () => void): void {
  if (typeof globalThis.setTimeout === 'function') {
    globalThis.setTimeout(callback, 0);
    return;
  }

  void Promise.resolve().then(callback);
}

function createStoreRuntimeEventLog() {
  let sequence = 0;
  const events: SovereignStoreRuntimeEvent[] = [];

  function record(
    kind: SovereignStoreRuntimeEventKind,
    message: string,
    actionType?: string,
  ): void {
    events.push({
      sequence: ++sequence,
      kind,
      message,
      actionType,
    });

    while (events.length > STORE_EVENT_LIMIT) {
      events.shift();
    }
  }

  function snapshot(): SovereignStoreRuntimeEvent[] {
    return events.map((event) => ({ ...event }));
  }

  function reset(): void {
    sequence = 0;
    events.length = 0;
  }

  return {
    record,
    snapshot,
    reset,
  };
}

const storeRuntimeEvents = createStoreRuntimeEventLog();

function createCanvasPersistenceMirror(key: string) {
  let pendingValue: string | null = null;
  let lastWrittenValue: string | null = null;
  let scheduled = false;
  let inFlight: Promise<boolean> | null = null;
  let sequence = 0;

  const status: CanvasPersistenceMirrorStatus = {
    architectureVersion: SOVEREIGN_STORE_ARCHITECTURE_VERSION,
    key,
    pending: false,
    writeInFlight: false,
    scheduled: false,
    writeCount: 0,
    skippedWriteCount: 0,
    failedWriteCount: 0,
    queuedSequence: null,
    writtenSequence: null,
    lastValueBytes: null,
    lastWrittenBytes: null,
    lastError: null,
  };

  function syncStatus(): void {
    status.pending = pendingValue !== null;
    status.writeInFlight = inFlight !== null;
    status.scheduled = scheduled;
    status.lastValueBytes = pendingValue === null ? null : byteLength(pendingValue);
    status.lastWrittenBytes =
      lastWrittenValue === null ? null : byteLength(lastWrittenValue);
  }

  function snapshot(): CanvasPersistenceMirrorStatus {
    syncStatus();

    return {
      ...status,
    };
  }

  async function flushOnce(value: string): Promise<boolean> {
    try {
      await Preferences.set({
        key,
        value,
      });

      lastWrittenValue = value;
      status.writeCount += 1;
      status.writtenSequence = ++sequence;
      status.lastError = null;

      storeRuntimeEvents.record(
        'canvas-persist-written',
        'Canvas state mirror written to native storage.',
      );

      return true;
    } catch (error) {
      pendingValue = value;
      status.failedWriteCount += 1;
      status.lastError = errorToMessage(error);

      storeRuntimeEvents.record(
        'canvas-persist-failed',
        `Canvas state mirror write failed: ${status.lastError}`,
      );

      return false;
    } finally {
      syncStatus();
    }
  }

  async function flush(): Promise<void> {
    if (inFlight) {
      await inFlight;
      return;
    }

    if (pendingValue === null) {
      syncStatus();
      return;
    }

    const value = pendingValue;
    pendingValue = null;

    syncStatus();

    inFlight = flushOnce(value);

    const succeeded = await inFlight;
    inFlight = null;

    syncStatus();

    if (succeeded && pendingValue !== null && pendingValue !== lastWrittenValue) {
      scheduleFlush();
    }
  }

  function scheduleFlush(): void {
    if (scheduled) return;

    scheduled = true;
    syncStatus();

    defer(() => {
      scheduled = false;
      syncStatus();
      void flush();
    });
  }

  function queue(value: string, actionType?: string): void {
    const sameAsPending = value === pendingValue;
    const sameAsWritten = value === lastWrittenValue;

    if (sameAsPending || sameAsWritten) {
      status.skippedWriteCount += 1;

      storeRuntimeEvents.record(
        'canvas-persist-skipped',
        sameAsPending
          ? 'Canvas state mirror skipped because the same value is already pending.'
          : 'Canvas state mirror skipped because the same value is already written.',
        actionType,
      );

      if (sameAsPending && status.lastError) {
        scheduleFlush();
      }

      syncStatus();
      return;
    }

    pendingValue = value;
    status.queuedSequence = ++sequence;
    status.lastError = null;

    storeRuntimeEvents.record(
      'canvas-persist-queued',
      'Canvas state mirror queued for native persistence.',
      actionType,
    );

    syncStatus();
    scheduleFlush();
  }

  function reset(): void {
    pendingValue = null;
    lastWrittenValue = null;
    scheduled = false;
    inFlight = null;
    sequence = 0;

    status.pending = false;
    status.writeInFlight = false;
    status.scheduled = false;
    status.writeCount = 0;
    status.skippedWriteCount = 0;
    status.failedWriteCount = 0;
    status.queuedSequence = null;
    status.writtenSequence = null;
    status.lastValueBytes = null;
    status.lastWrittenBytes = null;
    status.lastError = null;
  }

  return {
    queue,
    flush,
    reset,
    snapshot,
  };
}

const canvasPersistenceMirror = createCanvasPersistenceMirror(
  SOVEREIGN_CANVAS_PERSISTENCE_KEY,
);

const aiCanvasBridgeMiddleware: Middleware = (storeApi) => (next) => (action) => {
  const result = next(action);

  if (!isReduxActionLike(action) || !shouldBridgeAiActionToCanvas(action)) {
    return result;
  }

  storeRuntimeEvents.record(
    'ai-canvas-bridge',
    'AI action bridged into canvas object creation.',
    action.type,
  );

  storeApi.dispatch(addObject(action.payload as Parameters<typeof addObject>[0]));

  return result;
};

const canvasPersistenceMiddleware: Middleware = (storeApi) => (next) => (action) => {
  const result = next(action);

  if (!isReduxActionLike(action) || !shouldMirrorCanvasAction(action)) {
    return result;
  }

  const state = storeApi.getState() as CanvasMirrorRootState;
  const serializedCanvas = safeSerializeCanvasState(state.canvas);

  if (serializedCanvas === null) {
    storeRuntimeEvents.record(
      'canvas-persist-serialize-failed',
      'Canvas state mirror serialization failed.',
      action.type,
    );

    return result;
  }

  canvasPersistenceMirror.queue(serializedCanvas, action.type);

  return result;
};

export const store = configureStore({
  reducer: {
    billing: billingReducer,
    canvas: canvasReducer,
    ouroboros: ouroborosReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(aiCanvasBridgeMiddleware, canvasPersistenceMiddleware),
});

export async function flushCanvasStateMirror(): Promise<CanvasPersistenceMirrorStatus> {
  await canvasPersistenceMirror.flush();
  return canvasPersistenceMirror.snapshot();
}

export async function readCanvasStateMirror<TCanvasState = unknown>(): Promise<TCanvasState | null> {
  try {
    const result = await Preferences.get({
      key: SOVEREIGN_CANVAS_PERSISTENCE_KEY,
    });

    if (!result.value) return null;

    return JSON.parse(result.value) as TCanvasState;
  } catch (error) {
    storeRuntimeEvents.record(
      'canvas-persist-read-failed',
      `Canvas state mirror read failed: ${errorToMessage(error)}`,
    );

    return null;
  }
}

export async function clearCanvasStateMirror(): Promise<void> {
  try {
    await Preferences.remove({
      key: SOVEREIGN_CANVAS_PERSISTENCE_KEY,
    });

    storeRuntimeEvents.record(
      'canvas-persist-cleared',
      'Canvas state mirror cleared from native storage.',
    );
  } finally {
    canvasPersistenceMirror.reset();
  }
}

export function getCanvasStateMirrorStatus(): CanvasPersistenceMirrorStatus {
  return canvasPersistenceMirror.snapshot();
}

export function getSovereignStoreRuntimeStatus(): SovereignStoreRuntimeStatus {
  const canvasMirror = canvasPersistenceMirror.snapshot();
  const healthy = !canvasMirror.lastError && canvasMirror.failedWriteCount === 0;

  return {
    architectureVersion: SOVEREIGN_STORE_ARCHITECTURE_VERSION,
    canvasMirror,
    events: storeRuntimeEvents.snapshot(),
    healthy,
    summary: healthy
      ? 'Sovereign store runtime is healthy.'
      : `Sovereign store runtime degraded: ${canvasMirror.lastError ?? 'unknown persistence error'}`,
  };
}

export function resetSovereignStoreRuntimeDiagnostics(): void {
  storeRuntimeEvents.reset();
}

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export * from '../features/canvas/canvasSlice';
