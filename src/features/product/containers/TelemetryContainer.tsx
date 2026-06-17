import React from 'react';
import { SovereignTelemetryPanel } from '../components/SovereignTelemetryPanel';
import type { SovereignTelemetryState } from '../runtime/sovereignTelemetry';
import { deriveTelemetryContainerState, nextTelemetryExpandedState } from '../runtime/telemetryContainerRuntime';

export interface TelemetryContainerProps {
  state: SovereignTelemetryState;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}

export function TelemetryContainer({ state, expanded, onExpandedChange }: TelemetryContainerProps) {
  const containerState = deriveTelemetryContainerState({ state, expanded });

  const handleToggle = () => {
    onExpandedChange(nextTelemetryExpandedState(expanded, containerState.eventCount));
  };

  return (
    <section data-testid="telemetry-container" aria-label="Telemetry Container">
      <p className="sr-only">{containerState.validationSummary}</p>
      {!containerState.valid ? <p className="mt-3 text-xs text-red-300">{containerState.summary}</p> : null}
      <SovereignTelemetryPanel state={state} expanded={expanded && containerState.canExpand} onToggle={handleToggle} />
    </section>
  );
}
