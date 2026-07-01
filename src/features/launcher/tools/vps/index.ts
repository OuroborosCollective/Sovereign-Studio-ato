/**
 * VPS Connector — Launcher-Tool-Eintrag.
 *
 * Registriert den VPS Connector im LAUNCHER_REGISTRY.
 * Issue #454
 */

import { Terminal } from 'lucide-react';
import type { LauncherEntry } from '../../launcherRegistry';
import { VpsConnectorTool } from './VpsConnectorTool';

export const vpsConnectorEntry: LauncherEntry = {
  id: 'vps-connector',
  label: 'VPS Connector',
  description: 'SSH-Verbindung mit File Tree & Chat',
  icon: Terminal,
  color: 'bg-violet-600',
  component: VpsConnectorTool,
  badge: 'NEU',
  // Security: Deaktiviert bis server-seitige userId-Bindung, Command-Allowlist
  // und Destructive-Block implementiert sind. Issue #454.
  disabled: true,
};
