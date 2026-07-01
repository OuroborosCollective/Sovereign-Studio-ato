/**
 * TemplateTool — Basis-Vorlage für neue Sovereign Launcher Tools.
 *
 * VERWENDUNG:
 *   cp -r src/features/launcher/tools/_template src/features/launcher/tools/mein-tool
 *   Dann alle TODO: Markierungen ausfüllen.
 *
 * Issue #455
 */

import React from 'react';
import type { LauncherToolProps } from '../../launcherRegistry';

// TODO: Icon aus lucide-react importieren
// import { Puzzle } from 'lucide-react';

const C = {
  bg:      '#0e1116',
  surface: '#161c24',
  border:  '#232d3a',
  accent:  '#00d9b1',
  text:    '#cdd9e5',
  textSub: '#768390',
} as const;

/**
 * TODO: Komponente umbenennen (z.B. MeinTool)
 *
 * LauncherToolProps = { onClose: () => void; onMinimize: () => void; }
 * Das Floating Window liefert Titel + Minimize + Close — kein eigener Header nötig.
 *
 * Layout-Constraints:
 *   - Rendert in ≈390 × (vh − 180px)
 *   - h-full flex flex-col als Root
 *   - overflow-y-auto für scrollbaren Inhalt
 *   - Farbschema: C.bg als Hintergrund, C.text für Text
 */
export function TemplateTool({ onClose, onMinimize }: LauncherToolProps) {
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
        padding: 20,
        gap: 16,
        background: C.bg,
      }}
    >
      {/* TODO: Tool-Inhalt hier einfügen */}

      {/* Beispiel: Leer-Zustand */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 12,
      }}>
        <span style={{ fontSize: 32, opacity: 0.15 }}>⬡</span>
        <p style={{ fontSize: 12, color: C.textSub, textAlign: 'center' }}>
          TODO: Tool-Inhalt implementieren
        </p>
        <p style={{ fontSize: 10, color: C.textSub, textAlign: 'center', opacity: 0.6 }}>
          Ersetze diesen Platzhalter in TemplateTool.tsx
        </p>
      </div>

      {/* Beispiel: Action-Button */}
      <button
        type="button"
        onClick={() => {
          // TODO: Aktion implementieren
          // WICHTIG: Kein Auto-Execute — User bestätigt schreibende Aktionen
        }}
        style={{
          padding: '10px 0', borderRadius: 10, fontSize: 12, fontWeight: 700,
          border: 'none', cursor: 'pointer',
          background: C.accent, color: '#000',
        }}
      >
        TODO: Button-Label
      </button>
    </div>
  );
}
