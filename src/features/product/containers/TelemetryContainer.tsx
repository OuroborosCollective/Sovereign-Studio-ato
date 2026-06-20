import React, { useEffect, useState } from 'react';
import { SovereignTelemetryPanel } from '../components/SovereignTelemetryPanel';
import { appendTelemetryEvent, type SovereignTelemetryState } from '../runtime/sovereignTelemetry';
import { createDependencyTelemetryEvent } from '../runtime/dependencyTelemetryBridge';
import { deriveTelemetryContainerState, nextTelemetryExpandedState } from '../runtime/telemetryContainerRuntime';

export interface TelemetryContainerProps {
  state: SovereignTelemetryState;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}

export function TelemetryContainer({ state, expanded, onExpandedChange }: TelemetryContainerProps) {
  const [liveState, setLiveState] = useState(state);

  useEffect(() => {
    setLiveState(state);
  }, [state]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const handleDependencyTelemetry = (event: Event) => {
      const telemetryEvent = createDependencyTelemetryEvent((event as CustomEvent).detail);
      if (!telemetryEvent) return;
      setLiveState((current) => appendTelemetryEvent(current, telemetryEvent));
    };

    window.addEventListener('sovereign:dependency-telemetry-event', handleDependencyTelemetry);
    return () => window.removeEventListener('sovereign:dependency-telemetry-event', handleDependencyTelemetry);
  }, []);

  const containerState = deriveTelemetryContainerState({ state: liveState, expanded });

  const handleToggle = () => {
    onExpandedChange(nextTelemetryExpandedState(expanded, containerState.eventCount));
  };

  return (
    <section data-testid="telemetry-container" aria-label="Telemetry Container">
      <p className="sr-only">{containerState.validationSummary}</p>
      {!containerState.valid ? <p className="mt-3 text-xs text-red-300">{containerState.summary}</p> : null}
      <SovereignTelemetryPanel state={liveState} expanded={expanded && containerState.canExpand} onToggle={handleToggle} />
    </section>
  );
}
