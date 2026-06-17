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

export interface SovereignTelemetryValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

const MAX_EVENTS = 120;
const MAX_TEXT = 1200;
const TELEMETRY_LEVELS: SovereignTelemetryLevel[] = ['info', 'success', 'warning', 'error'];
const TELEMETRY_STAGES: SovereignTelemetryStage[] = ['repo', 'readiness', 'package', 'guards', 'github', 'workflow', 'memory', 'ui'];

const SECRET_PATTERNS = [
  /ghp_[A-Za-z0-9_]{8,}/g,
  /github_pat_[A-Za-z0-9_]+/g,
  /sk-[A-Za-z0-9_-]{12,}/g,
  /Bearer\s+[A-Za-z0-9._~+/=-]{10,}/gi,
  /password\s*[:=]\s*[^\s]+/gi,
  /token\s*[:=]\s*[^\s]+/gi,
];

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function hasSecret(value: string): boolean {
  return SECRET_PATTERNS.some((pattern) => {
    pattern.lastIndex = 0;
    return pattern.test(value);
  });
}

function validateDetails(details?: SovereignTelemetryEvent['details']): string[] {
  if (!details) return [];
  const errors: string[] = [];
  for (const [key, value] of Object.entries(details)) {
    if (!key.trim()) errors.push('Telemetry detail key is empty.');
    if (typeof value === 'string' && hasSecret(value)) errors.push(`Telemetry detail ${key} contains secret-like content.`);
    if (typeof value === 'number' && !Number.isFinite(value)) errors.push(`Telemetry detail ${key} is not a finite number.`);
  }
  return errors;
}

export function validateTelemetryEvent(event: SovereignTelemetryEvent): SovereignTelemetryValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!event.id.trim()) errors.push('Telemetry event id is required.');
  if (!TELEMETRY_STAGES.includes(event.stage)) errors.push(`Unknown telemetry stage: ${event.stage}`);
  if (!TELEMETRY_LEVELS.includes(event.level)) errors.push(`Unknown telemetry level: ${event.level}`);
  if (!event.label.trim()) errors.push('Telemetry label is required.');
  if (!event.message.trim()) errors.push('Telemetry message is required.');
  if (event.label.length > MAX_TEXT || event.message.length > MAX_TEXT) errors.push('Telemetry text is too long.');
  if (!Number.isFinite(event.timestamp) || event.timestamp <= 0) errors.push('Telemetry timestamp must be positive.');
  if ([event.id, event.label, event.message].some(hasSecret)) errors.push('Telemetry event contains secret-like content.');
  errors.push(...validateDetails(event.details));

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in telemetry event.`,
  };
}

export function assertTelemetryEventValid(event: SovereignTelemetryEvent): void {
  const report = validateTelemetryEvent(event);
  if (!report.valid) throw new Error(`Telemetry event is invalid: ${report.errors.join(' | ')}`);
}

export function validateTelemetryState(state: SovereignTelemetryState): SovereignTelemetryValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!Array.isArray(state.events)) errors.push('Telemetry events must be an array.');
  if (state.events.length > MAX_EVENTS) errors.push(`Telemetry has more than ${MAX_EVENTS} events.`);

  const ids = new Set<string>();
  for (const event of state.events) {
    if (ids.has(event.id)) warnings.push(`Duplicate telemetry event id: ${event.id}`);
    ids.add(event.id);
    const report = validateTelemetryEvent(event);
    errors.push(...report.errors.map((error) => `${event.label || event.id}: ${error}`));
    warnings.push(...report.warnings.map((warning) => `${event.label || event.id}: ${warning}`));
  }

  for (const [stage, event] of Object.entries(state.latestByStage)) {
    if (!TELEMETRY_STAGES.includes(stage as SovereignTelemetryStage)) errors.push(`Unknown latest telemetry stage: ${stage}`);
    const latest = state.events.filter((item) => item.stage === stage).slice(-1)[0];
    if (latest && latest.id !== event?.id) warnings.push(`latestByStage mismatch for ${stage}.`);
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${state.events.length} telemetry event(s), ${errors.length} error(s), ${warnings.length} warning(s).`,
  };
}

export function assertTelemetryStateValid(state: SovereignTelemetryState): void {
  const report = validateTelemetryState(state);
  if (!report.valid) throw new Error(`Telemetry state is invalid: ${report.errors.join(' | ')}`);
}

export function createTelemetryEvent(
  stage: SovereignTelemetryStage,
  level: SovereignTelemetryLevel,
  label: string,
  message: string,
  details?: SovereignTelemetryEvent['details'],
  timestamp = Date.now(),
): SovereignTelemetryEvent {
  const safeLabel = label.trim().slice(0, MAX_TEXT);
  const safeMessage = message.trim().slice(0, MAX_TEXT);
  const seed = `${stage}:${level}:${safeLabel}:${safeMessage}:${timestamp}:${JSON.stringify(details ?? {})}`;
  const event = {
    id: stableHash(seed),
    stage,
    level,
    label: safeLabel,
    message: safeMessage,
    timestamp,
    details,
  } satisfies SovereignTelemetryEvent;
  assertTelemetryEventValid(event);
  return event;
}

export function createInitialTelemetryState(): SovereignTelemetryState {
  return { events: [], latestByStage: {} };
}

export function appendTelemetryEvent(
  state: SovereignTelemetryState,
  event: SovereignTelemetryEvent,
  maxEvents = MAX_EVENTS,
): SovereignTelemetryState {
  assertTelemetryStateValid(state);
  assertTelemetryEventValid(event);
  const events = [...state.events, event].slice(-Math.max(1, maxEvents));
  const next = {
    events,
    latestByStage: {
      ...state.latestByStage,
      [event.stage]: event,
    },
  } satisfies SovereignTelemetryState;
  assertTelemetryStateValid(next);
  return next;
}

export function summarizeTelemetry(state: SovereignTelemetryState): string {
  assertTelemetryStateValid(state);
  if (!state.events.length) return 'No telemetry events yet.';
  const latest = state.events[state.events.length - 1];
  const errorCount = state.events.filter((event) => event.level === 'error').length;
  const warningCount = state.events.filter((event) => event.level === 'warning').length;
  return `${state.events.length} events, ${warningCount} warning(s), ${errorCount} error(s). Latest: ${latest?.label ?? 'unknown'}`;
}

export function formatTelemetryLine(event: SovereignTelemetryEvent): string {
  assertTelemetryEventValid(event);
  const date = new Date(event.timestamp).toISOString();
  const detailText = event.details
    ? ` ${Object.entries(event.details).map(([key, value]) => `${key}=${String(value)}`).join(' ')}`
    : '';
  return `[${date}] [${event.level.toUpperCase()}] [${event.stage}] ${event.label}: ${event.message}${detailText}`;
}
