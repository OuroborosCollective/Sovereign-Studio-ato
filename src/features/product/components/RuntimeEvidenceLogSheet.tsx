import React from 'react';
import type { SovereignRuntimeEvidenceLogEntry } from '../runtime/sovereignCompactShortcutExecutionRuntime';
import { C } from './builderConstants';

export function RuntimeEvidenceLogSheet({ entries, onClose }: { readonly entries: readonly SovereignRuntimeEvidenceLogEntry[]; readonly onClose: () => void }) {
  return (
    <div role="presentation" onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 84, background: 'rgba(14,17,22,0.84)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <section role="dialog" aria-modal="true" aria-label="Runtime Evidence Logs" onClick={(event) => event.stopPropagation()} style={{ width: '100%', maxWidth: 680, maxHeight: '78vh', overflowY: 'auto', margin: '0 auto', borderRadius: '20px 20px 0 0', border: `1px solid ${C.border}`, background: C.surface, padding: '16px 16px calc(22px + env(safe-area-inset-bottom, 0px))' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><div><strong style={{ color: C.text }}>Runtime Evidence Logs</strong><p style={{ color: C.textMuted, fontSize: 11 }}>Nur Action-Stream- und Agent-Runtime-Ereignisse. Keine Tabwechsel- oder UI-Signallogs.</p></div><button type="button" onClick={onClose} aria-label="Runtime Logs schließen" title="Runtime Logs schließen">×</button></div>
        {entries.length === 0 ? <p style={{ color: C.textMuted }}>Noch keine Runtime-Ereignisse.</p> : <ol style={{ listStyle: 'none', padding: 0, margin: '12px 0 0', display: 'grid', gap: 8 }}>{entries.map((entry) => <li key={entry.id} data-runtime-source={entry.source} style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: 9, background: C.bg }}><div style={{ color: C.textMuted, fontSize: 9, fontFamily: 'monospace' }}>{new Date(entry.at).toLocaleTimeString('de-DE')} · {entry.source} · {entry.scope}</div><div style={{ color: entry.level === 'error' ? C.rose : entry.level === 'warning' ? C.amber : entry.level === 'success' ? C.green : C.text, fontSize: 11, marginTop: 4 }}>{entry.message}</div></li>)}</ol>}
      </section>
    </div>
  );
}
