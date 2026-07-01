/**
 * VpsConnectorTool — Root-Komponente des VPS Connector Launcher-Tools.
 *
 * Zustandsmaschine: disconnected → connecting → connected | error
 * Credentials werden NUR im lokalen Component-State gehalten —
 * kein Store, kein localStorage, kein Logging.
 *
 * Issue #454
 */

import React from 'react';
import type { LauncherToolProps } from '../../launcherRegistry';
import { VpsConnectionForm } from './VpsConnectionForm';
import { VpsWorkspace } from './VpsWorkspace';
import { useVpsConnection } from './useVpsConnection';

export function VpsConnectorTool({ onClose, onMinimize }: LauncherToolProps) {
  const { state, connect, disconnect, execCommand, getTree } = useVpsConnection();

  // Nicht verbunden oder Verbindungsfehler
  if (state.phase !== 'connected') {
    return (
      <VpsConnectionForm
        connecting={state.phase === 'connecting'}
        error={state.error}
        onConnect={connect}
      />
    );
  }

  // Verbunden
  return (
    <VpsWorkspace
      host={state.host}
      username={state.username}
      getTree={getTree}
      execCommand={execCommand}
      onDisconnect={disconnect}
    />
  );
}
