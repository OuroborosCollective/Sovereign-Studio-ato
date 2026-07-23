import React from 'react';
import type { GeneratedFileDiffReport } from '../runtime/generatedFileDiffPreview';
import { formatDiffStats } from '../runtime/diffStatsFormatter';
import { buildImpactReport } from '../runtime/dependencyImpactRuntime';
import { buildMergeBlastRadiusGate } from '../runtime/mergeBlastRadiusGateRuntime';
import { C } from './builderConstants';

export function PatchDiffEvidenceSheet({ report, confirmed, narratives = {}, onConfirm, onClose }: { readonly report: GeneratedFileDiffReport; readonly confirmed: boolean; readonly narratives?: Readonly<Record<string, string>>; readonly onConfirm: () => void; readonly onClose: () => void }) {
  const stats = formatDiffStats(report);
  const impact = buildImpactReport(
    report.files.map((file) => file.path),
    report.files.map((file) => ({ path: file.path, content: file.preview })),
    { complete: false },
  );
  const blastRadius = buildMergeBlastRadiusGate({
    changedPaths: report.files.filter((file) => file.changed).map((file) => file.path),
    totalAddedLines: report.totalAddedLines,
    totalRemovedLines: report.totalRemovedLines,
    dependencyImpact: Object.values(impact.byTarget),
  });
  return (
    <div role="presentation" onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 84, background: 'rgba(14,17,22,0.84)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <section role="dialog" aria-modal="true" aria-label="Patch Diff" onClick={(event) => event.stopPropagation()} style={{ width: '100%', maxWidth: 680, maxHeight: '82vh', overflowY: 'auto', margin: '0 auto', borderRadius: '20px 20px 0 0', border: `1px solid ${C.border}`, background: C.surface, padding: '16px 16px calc(22px + env(safe-area-inset-bottom, 0px))' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <strong style={{ color: C.text }}>Patch Diff</strong>
            <p style={{ color: C.textMuted, fontSize: 11 }}>{report.summary}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Patch Diff schließen" title="Patch Diff schließen">×</button>
        </div>
        <div data-testid="patch-diff-stats" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8, marginTop: 10 }}>
          <div style={{ border: `1px solid ${C.border}`, borderRadius: 9, padding: 9, background: C.bg }}><div style={{ color: C.sky, fontWeight: 700, fontSize: 12 }}>{stats.fileCountLabel}</div><div style={{ color: C.textMuted, fontSize: 9, marginTop: 3 }}>{stats.fileKindBreakdown || 'Keine Dateien'}</div></div>
          <div style={{ border: `1px solid ${C.border}`, borderRadius: 9, padding: 9, background: C.bg }}><div style={{ color: stats.hasChanges ? C.green : C.textMuted, fontWeight: 700, fontSize: 12 }}>{stats.lineChangeSummary}</div><div style={{ color: C.textMuted, fontSize: 9, marginTop: 3 }}>deterministisch aus der Diff-Vorschau</div></div>
        </div>
        <div data-testid="merge-blast-radius" style={{ marginTop: 10, border: `1px solid ${blastRadius.level === 'critical' || blastRadius.level === 'high' ? C.rose : blastRadius.level === 'medium' ? C.amber : C.green}44`, borderRadius: 9, padding: 9, background: C.bg }}>
          <div style={{ color: C.text, fontWeight: 700, fontSize: 11 }}>Merge Blast Radius: {blastRadius.level.toUpperCase()} · {blastRadius.score}/100</div>
          <div style={{ color: C.textMuted, fontSize: 9, marginTop: 3 }}>{blastRadius.reasons.join(' ') || 'Bounded diff evidence indicates a low blast radius.'}</div>
        </div>
        {report.files.map((file) => {
          const fileImpact = impact.byTarget[file.path];
          return <article key={file.path} style={{ marginTop: 12, border: `1px solid ${C.border}`, borderRadius: 10, padding: 10, background: C.bg }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <strong style={{ color: C.sky, fontSize: 12 }}>{file.path}</strong>
              <span title="Deterministisch aus den aktuell geladenen Diff-Quellen; kein vollständiger Repo-Scan" style={{ border: `1px solid ${fileImpact?.risk === 'high' ? C.rose : C.border}`, borderRadius: 999, padding: '2px 7px', color: fileImpact?.risk === 'high' ? C.rose : C.textMuted, fontSize: 9 }}>
                Impact {fileImpact?.importerCount ?? 0} · Teilmenge {fileImpact?.scannedFileCount ?? 0}
              </span>
            </div>
            {narratives[file.path] && <p data-testid={`semantic-narration-${file.path}`} style={{ color: C.text, fontSize: 11, fontWeight: 600, marginTop: 7 }}>{narratives[file.path]}</p>}
            <p style={{ color: C.textSub, fontSize: 10 }}>{file.summary}</p>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', color: C.text, fontSize: 10, lineHeight: 1.45 }}>{file.preview}</pre>
          </article>;
        })}
        <button type="button" onClick={onConfirm} disabled={confirmed} data-testid="confirm-patch-diff" style={{ width: '100%', minHeight: 48, marginTop: 16, borderRadius: 12, border: `1px solid ${confirmed ? C.green : C.sky}`, background: confirmed ? `${C.green}18` : `${C.sky}18`, color: confirmed ? C.green : C.sky, fontWeight: 700, cursor: confirmed ? 'default' : 'pointer' }}>{confirmed ? '✓ Patch bestätigt' : 'Patch prüfen und bestätigen'}</button>
      </section>
    </div>
  );
}
