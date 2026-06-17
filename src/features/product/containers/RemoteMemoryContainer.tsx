import React from 'react';
import { RemoteMemoryPanel, type RemoteMemoryPanelProps } from '../components/RemoteMemoryPanel';

export interface RemoteMemoryContainerProps extends RemoteMemoryPanelProps {
  statusLabel?: string;
}

export function RemoteMemoryContainer({ statusLabel = 'Remote Memory boundary active.', ...panelProps }: RemoteMemoryContainerProps) {
  return (
    <section data-testid="remote-memory-container" aria-label="Remote Memory Container">
      <p className="sr-only">{statusLabel}</p>
      <RemoteMemoryPanel {...panelProps} />
    </section>
  );
}
