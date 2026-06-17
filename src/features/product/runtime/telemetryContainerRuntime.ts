import { summarizeTelemetry, validateTelemetryState, type SovereignTelemetryState } from './sovereignTelemetry';

export interface TelemetryContainerRuntimeInput {
  state: SovereignTelemetryState;
  expanded: boolean;
}

export interface TelemetryContainerRuntimeState {
  valid: boolean;
  canExpand: boolean;
  eventCount: number;
  summary: string;
  validationSummary: string;
}

export function deriveTelemetryContainerState(input: TelemetryContainerRuntimeInput): TelemetryContainerRuntimeState {
  const validation = validateTelemetryState(input.state);
  const eventCount = Array.isArray(input.state.events) ? input.state.events.length : 0;

  return {
    valid: validation.valid,
    canExpand: validation.valid && eventCount > 0,
    eventCount,
    summary: validation.valid ? summarizeTelemetry(input.state) : validation.errors.join(' | '),
    validationSummary: validation.summary,
  };
}

export function nextTelemetryExpandedState(current: boolean, eventCount: number): boolean {
  if (eventCount <= 0) return false;
  return !current;
}
