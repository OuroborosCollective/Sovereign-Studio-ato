import React, { useEffect } from 'react';
import type { SovereignRuntimeEvidenceLogEntry } from '../runtime/sovereignCompactShortcutExecutionRuntime';
import { buildEvidenceLineage } from '../runtime/evidenceLineageRuntime';
import { C } from './builderConstants';

export function RuntimeEvidenceLogSheet({ entries, onClose }: { readonly entries: readonly SovereignRuntimeEvidenceLogEntry[]; readonly onClose: () => void }) {
  const lineages = buildEvidenceLineage(entries);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div role="presentation" onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 84, background: 'rgba(14,17,22,0.84)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <section role="dialog" aria-modal="true" aria-labelledby="runtime-evidence-logs-title" onClick={(event) => event.stopPropagation()} style={{ width: '100%', maxWidth: 680, maxHeight: '78vh', overflowY: 'auto', margin: '0 auto', borderRadius: '20px 20px 0 0', border: `1px solid ${C.border}`, background: C.surface, padding: '16px 16px calc(22px + env(safe-area-inset-bottom, 0px))' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <h3 id="runtime-evidence-logs-title" style={{ color: C.text, margin: 0, fontSize: 14, fontWeight: 700 }}>Runtime Evidence Logs</h3>
            <p style={{ color: C.textMuted, fontSize: 11, margin: '2px 0 0' }}>Nur Action-Stream- und Agent-Runtime-Ereignisse. Keine Tabwechsel- oder UI-Signallogs.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-xs focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none transition-opacity hover:opacity-80"
            aria-label="Runtime Logs schließen"
            title="Runtime Logs schließen"
            style={{ color: C.textMuted, background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}
          >
            ×
          </button>
        </div>
        {lineages.length > 0 && (
          <ul role="list" aria-label="Evidence Lineage Chains" data-testid="evidence-lineage-lens" style={{ listStyle: 'none', padding: 0, margin: '10px 0 0', display: 'grid', gap: 6 }}>
            {lineages.map((lineage) => (
              <li key={lineage.scope} title={`Lineage Scope ${lineage.scope}: ${lineage.nodes.map((node) => node.source).join(' → ')}`} style={{ border: `1px solid ${C.sky}33`, borderRadius: 9, padding: 8, background: `${C.sky}08` }}>
                <div style={{ color: C.sky, fontSize: 9, fontFamily: 'monospace' }}>{lineage.scope}</div>
                <div style={{ color: C.textSub, fontSize: 10, marginTop: 3 }}>{lineage.nodes.map((node) => node.source).join(' → ')}</div>
              </li>
            ))}
          </ul>
        )}
        {entries.length === 0 ? (
          <p style={{ color: C.textMuted, marginTop: 12, fontSize: 12 }}>Noch keine Runtime-Ereignisse.</p>
        ) : (
          <ol style={{ listStyle: 'none', padding: 0, margin: '12px 0 0', display: 'grid', gap: 8 }}>
            {entries.map((entry) => (
              <li key={entry.id} data-runtime-source={entry.source} title={`Runtime Event (${entry.source} / ${entry.scope}): ${entry.message}`} style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: 9, background: C.bg }}>
                <div style={{ color: C.textMuted, fontSize: 9, fontFamily: 'monospace' }}>{new Date(entry.at).toLocaleTimeString('de-DE')} · {entry.source} · {entry.scope}</div>
                <div style={{ color: entry.level === 'error' ? C.rose : entry.level === 'warning' ? C.amber : entry.level === 'success' ? C.green : C.text, fontSize: 11, marginTop: 4 }}>{entry.message}</div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
