/**
 * _template/index.ts — Vorlage für neue Launcher-Tool-Einträge.
 *
 * SCHRITT 1: Diese Datei in dein Tool-Verzeichnis kopieren
 *   cp -r src/features/launcher/tools/_template src/features/launcher/tools/mein-tool
 *
 * SCHRITT 2: Alle TODO: Felder ausfüllen
 *
 * SCHRITT 3: In launcherRegistry.ts eintragen:
 *   import { meinToolEntry } from './tools/mein-tool';
 *   export const LAUNCHER_REGISTRY = [..., meinToolEntry];
 *
 * Das war's — kein weiterer Eingriff in BuilderContainer nötig.
 *
 * Issue #455
 */

// TODO: Passendes Lucide-Icon importieren
import { Puzzle } from 'lucide-react';
import type { LauncherEntry } from '../../launcherRegistry';
// TODO: Tool-Komponente importieren
import { TemplateTool } from './TemplateTool';

/**
 * TODO: Konstanten-Name anpassen (z.B. meinToolEntry)
 *
 * Erlaubte Farb-Palette (Tailwind bg-* Klassen):
 *   bg-indigo-600 | bg-violet-600 | bg-teal-600 | bg-rose-600
 *   bg-amber-600  | bg-sky-600    | bg-emerald-600
 */
export const templateToolEntry: LauncherEntry = {
  id: 'template-tool',                    // TODO: Einzigartiger ID — kebab-case, nach Deploy unveränderlich
  label: 'Template',                      // TODO: max. 15 Zeichen
  description: 'Vorlage für neue Tools', // TODO: max. 60 Zeichen
  icon: Puzzle,                           // TODO: Lucide-Icon
  color: 'bg-indigo-600',                 // TODO: Farbe aus der Palette
  component: TemplateTool,               // TODO: Tool-Komponente
  badge: 'BETA',                          // TODO: 'NEU' | 'BETA' | 'PRO' | undefined
  disabled: true,                         // TODO: false wenn das Tool fertig ist
};
