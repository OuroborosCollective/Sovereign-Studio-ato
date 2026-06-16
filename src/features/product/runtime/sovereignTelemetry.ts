export type SovereignTelemetryLevel = 'info' | 'success' | 'warning' | 'error';

export type SovereignTelemetryStage =
  | 'repo'
  | 'readiness'
  | 'package'
  | 'guards'
  | 'github'
  | 'workflow'
  | 'memory'
  | 'ui';

export interface SovereignTelemetryEvent {
  id: string;
  stage: SovereignTelemetryStage;
  level: SovereignTelemetryLevel;
  label: string;
  message: string;
  timestamp: number;
  details?: Record<string, string | number | boolean | null>;
}

export interface SovereignTelemetryState {
  events: SovereignTelemetryEvent[];
  latestByStage: Partial<Record<SovereignTelemetryStage, SovereignTelemetryEvent>>;
}

const MAX_EVENTS = 120;

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

export function createTelemetryEvent(
  stage: SovereignTelemetryStage,
  level: SovereignTelemetryLevel,
  label: string,
  message: string,
  details?: SovereignTelemetryEvent['details'],
  timestamp = Date.now(),
): SovereignTelemetryEvent {
  const seed = `${stage}:${level}:${label}:${message}:${timestamp}:${JSON.stringify(details ?? {})}`;
  return {
    id: stableHash(seed),
    stage,
    level,
    label,
    message,
    timestamp,
    details,
  };
}

export function createInitialTelemetryState(): SovereignTelemetryState {
  return { events: [], latestByStage: {} };
}

export function appendTelemetryEvent(
  state: SovereignTelemetryState,
  event: SovereignTelemetryEvent,
  maxEvents = MAX_EVENTS,
): SovereignTelemetryState {
  const events = [...state.events, event].slice(-Math.max(1, maxEvents));
  return {
    events,
    latestByStage: {
      ...state.latestByStage,
      [event.stage]: event,
    },
  };
}

export function summarizeTelemetry(state: SovereignTelemetryState): string {
  if (!state.events.length) return 'No telemetry events yet.';
  const latest = state.events.at(-1);
  const errorCount = state.events.filter((event) => event.level === 'error').length;
  const warningCount = state.events.filter((event) => event.level === 'warning').length;
  return `${state.events.length} events, ${warningCount} warning(s), ${errorCount} error(s). Latest: ${latest?.label ?? 'unknown'}`;
}

export function formatTelemetryLine(event: SovereignTelemetryEvent): string {
  const date = new Date(event.timestamp).toISOString();
  const detailText = event.details
    ? ` ${Object.entries(event.details).map(([key, value]) => `${key}=${String(value)}`).join(' ')}`
    : '';
  return `[${date}] [${event.level.toUpperCase()}] [${event.stage}] ${event.label}: ${event.message}${detailText}`;
}
