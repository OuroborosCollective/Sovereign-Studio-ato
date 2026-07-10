/**
 * LauncherRegistry — zentrale Registrierung aller Sovereign Launcher Tools.
 *
 * Neue Tools werden hier eingetragen — KEINE Änderung an BuilderContainer.tsx nötig.
 * Jedes Tool ist vollständig isoliert in src/features/launcher/tools/<tool-name>/.
 *
 * Issue #451
 */

import type React from 'react';

// ── Typen ────────────────────────────────────────────────────────────────────

export interface LauncherEntry {
  /** kebab-case, einzigartig, nach Deployment NICHT mehr ändern */
  id: string;
  /** Anzeigename in der Grid-Kachel — max. 15 Zeichen */
  label: string;
  /** Kurzbeschreibung — max. 60 Zeichen */
  description: string;
  /** Lucide-Icon — keine eigenen SVGs */
  icon: React.ComponentType<{ size?: number; className?: string }>;
  /** Tailwind bg-*-Klasse aus der erlaubten Palette */
  color: string;
  /** Die Tool-Komponente — rendert im Floating Window */
  component: React.ComponentType<LauncherToolProps>;
  /** Optionaler Status-Badge */
  badge?: 'NEU' | 'BETA' | 'PRO';
  /** true = sichtbar im Grid, aber nicht startbar */
  disabled?: boolean;
}

/** Props die jedes Launcher-Tool bekommt */
export interface LauncherToolProps {
  onClose: () => void;
  onMinimize: () => void;
}

// ── Erlaubte Farb-Palette ─────────────────────────────────────────────────────
// bg-indigo-600 | bg-violet-600 | bg-teal-600 | bg-rose-600
// bg-amber-600  | bg-sky-600    | bg-emerald-600

// ── Registry ─────────────────────────────────────────────────────────────────

// Tool-Imports — neue Tools hier ergänzen
import { vpsConnectorEntry }      from './tools/vps/index';
import { adminToolEntry }         from './tools/admin/index';
import { toolchainToolEntry }     from './tools/toolchain/index';
import {
  coverageToolEntry,
  healthToolEntry,
  memoryToolEntry,
  settingsToolEntry,
} from './tools/sovereign-core/index';

/**
 * Alle registrierten Launcher-Tools.
 * Neue Einträge einfach anhängen — das LauncherMenu rendert sie automatisch.
 */
export const LAUNCHER_REGISTRY: LauncherEntry[] = [
  vpsConnectorEntry,    // Issue #454 — VPS Connector
  adminToolEntry,       // Issue #460 — Admin Backend
  toolchainToolEntry,   // Universal Toolchain — MCP/REST/OpenAPI
  settingsToolEntry,    // Core utility — Settings with real session checks
  memoryToolEntry,      // Core utility — Memory/key inspection without secrets
  healthToolEntry,      // Core utility — Client health checks
  coverageToolEntry,    // Core utility — Coverage map gate
];
