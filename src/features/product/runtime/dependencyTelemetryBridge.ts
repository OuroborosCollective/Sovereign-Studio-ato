import { createTelemetryEvent, type SovereignTelemetryEvent, type SovereignTelemetryLevel, type SovereignTelemetryStage } from './sovereignTelemetry';

type PrimitiveTelemetryValue = string | number | boolean | null;

const LEVELS: SovereignTelemetryLevel[] = ['info', 'success', 'warning', 'error'];
const STAGES: SovereignTelemetryStage[] = ['repo', 'readiness', 'package', 'guards', 'github', 'workflow', 'memory', 'ui'];

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function cleanLevel(value: unknown): SovereignTelemetryLevel {
  return LEVELS.includes(value as SovereignTelemetryLevel) ? value as SovereignTelemetryLevel : 'info';
}

function stageFromSource(value: unknown): SovereignTelemetryStage | null {
  if (value === 'github') return 'github';
  if (value === 'workflow') return 'workflow';
  if (value === 'remote-memory' || value === 'pattern-memory') return 'memory';
  return null;
}

function cleanStage(value: unknown, details?: Record<string, PrimitiveTelemetryValue>): SovereignTelemetryStage {
  const sourceStage = stageFromSource(details?.dependencySource);
  if (sourceStage) return sourceStage;
  return STAGES.includes(value as SovereignTelemetryStage) ? value as SovereignTelemetryStage : 'ui';
}

function cleanDetails(value: unknown): Record<string, PrimitiveTelemetryValue> | undefined {
  const record = asRecord(value);
  if (!record) return undefined;

  const details: Record<string, PrimitiveTelemetryValue> = {};
  for (const [key, item] of Object.entries(record)) {
    const cleanKey = key.trim();
    if (!cleanKey) continue;
    if (typeof item === 'string' || typeof item === 'boolean' || item === null) details[cleanKey] = item;
    if (typeof item === 'number' && Number.isFinite(item)) details[cleanKey] = item;
  }
  return Object.keys(details).length ? details : undefined;
}

export function createDependencyTelemetryEvent(input: unknown, timestamp = Date.now()): SovereignTelemetryEvent | null {
  const record = asRecord(input);
  if (!record) return null;

  const label = cleanText(record.label);
  const message = cleanText(record.message);
  const details = cleanDetails(record.details);

  if (!label || !message) return null;

  try {
    return createTelemetryEvent(
      cleanStage(record.stage, details),
      cleanLevel(record.level),
      label,
      message,
      details,
      timestamp,
    );
  } catch {
    return null;
  }
}
