import React from 'react';
import type { GeneratedFileDiffReport } from '../runtime/generatedFileDiffPreview';
import { C } from './builderConstants';

export function PatchDiffEvidenceSheet({ report, confirmed, onConfirm, onClose }: { readonly report: GeneratedFileDiffReport; readonly confirmed: boolean; readonly onConfirm: () => void; readonly onClose: () => void }) {
  return (
    <div role="presentation" onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 84, background: 'rgba(14,17,22,0.84)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <section role="dialog" aria-modal="true" aria-label="Patch Diff" onClick={(event) => event.stopPropagation()} style={{ width: '100%', maxWidth: 680, maxHeight: '82vh', overflowY: 'auto', margin: '0 auto', borderRadius: '20px 20px 0 0', border: `1px solid ${C.border}`, background: C.surface, padding: '16px 16px calc(22px + env(safe-area-inset-bottom, 0px))' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><div><strong style={{ color: C.text }}>Patch Diff</strong><p style={{ color: C.textMuted, fontSize: 11 }}>{report.summary}</p></div><button type="button" onClick={onClose} aria-label="Patch Diff schließen" title="Patch Diff schließen">×</button></div>
        {report.files.map((file) => <article key={file.path} style={{ marginTop: 12, border: `1px solid ${C.border}`, borderRadius: 10, padding: 10, background: C.bg }}><strong style={{ color: C.sky, fontSize: 12 }}>{file.path}</strong><p style={{ color: C.textSub, fontSize: 10 }}>{file.summary}</p><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', color: C.text, fontSize: 10, lineHeight: 1.45 }}>{file.preview}</pre></article>)}
        <button type="button" onClick={onConfirm} disabled={confirmed} data-testid="confirm-patch-diff" style={{ width: '100%', minHeight: 48, marginTop: 16, borderRadius: 12, border: `1px solid ${confirmed ? C.green : C.sky}`, background: confirmed ? `${C.green}18` : `${C.sky}18`, color: confirmed ? C.green : C.sky, fontWeight: 700, cursor: confirmed ? 'default' : 'pointer' }}>{confirmed ? '✓ Patch bestätigt' : 'Patch prüfen und bestätigen'}</button>
      </section>
    </div>
  );
}
