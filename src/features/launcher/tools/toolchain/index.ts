/**
 * Toolchain Tool — Launcher-Eintrag für den Sovereign Universal Toolchain Server.
 *
 * Exposiert das FastMCP/REST/OpenAPI Toolchain-Backend als Launcher-Panel.
 * Endpunkte:
 *   MCP:     https://sovereign-backend.arelorian.de/toolchain/mcp
 *   REST:    https://sovereign-backend.arelorian.de/toolchain/api/v1/tools/{name}
 *   OpenAPI: https://sovereign-backend.arelorian.de/toolchain/api/openapi.json
 */

import { Wrench } from 'lucide-react';
import type { LauncherEntry } from '../../launcherRegistry';
import { ToolchainPanel } from '../../../toolchain/ToolchainPanel';

export const toolchainToolEntry: LauncherEntry = {
  id:          'sovereign-toolchain',
  label:       'Toolchain',
  description: 'Universal MCP/REST/OpenAPI Toolchain — LLM & Workspace Tools',
  icon:        Wrench,
  color:       'bg-teal-600',
  component:   ToolchainPanel,
  badge:       'NEU',
  disabled:    false,
};
