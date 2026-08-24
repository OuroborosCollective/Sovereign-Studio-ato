import React from 'react';
import { C } from './builderConstants';

export type DraftPrEvidenceSource = 'staged' | 'agent' | 'mixed';

export function DraftPrActionPreview({
  repoUrl,
  branch,
  expectedHeadSha,
  mission,
  changedFileCount,
  evidenceSource,
  onConfirm,
  onCancel,
}: {
  readonly repoUrl: string;
  readonly branch: string;
  readonly expectedHeadSha?: string;
  readonly mission: string;
  readonly changedFileCount: number;
  readonly evidenceSource: DraftPrEvidenceSource;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}) {
  const evidenceLabel = evidenceSource === 'mixed'
    ? 'bestätigte lokale Änderungen und serverseitige Agent-Evidence'
    : evidenceSource === 'agent'
      ? 'serverseitige Agent-Changed-File-Evidence'
      : 'bestätigte lokale Diff-Evidence';

  return (
    <div
      role="presentation"
      onClick={onCancel}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 96,
        background: 'rgba(14,17,22,0.86)',
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
      }}
    >
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="draft-pr-action-preview-title"
        aria-describedby="draft-pr-action-preview-description"
        onClick={(event) => event.stopPropagation()}
        data-testid="draft-pr-action-preview"
        style={{
          width: '100%',
          maxWidth: 680,
          borderRadius: '20px 20px 0 0',
          border: `1px solid ${C.orange}66`,
          background: C.surface,
          padding: '18px 16px calc(22px + env(safe-area-inset-bottom, 0px))',
        }}
      >
        <h2 id="draft-pr-action-preview-title" style={{ margin: 0, color: C.text, fontSize: 16 }}>
          Draft PR wirklich an die Runtime übergeben?
        </h2>
        <p id="draft-pr-action-preview-description" style={{ color: C.textMuted, fontSize: 12, lineHeight: 1.5 }}>
          Diese bestätigte Aktion kann einen Draft PR erzeugen. Der Server prüft danach
          Repository-Head, Diff, Review und seine persistierte Evidence erneut. Bei einer
          Abweichung wird kein PR erstellt.
        </p>

        <dl style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 8, margin: '14px 0' }}>
          <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: 10, background: C.bg }}>
            <dt style={{ color: C.textMuted, fontSize: 10 }}>Repository / Branch</dt>
            <dd title={`${repoUrl}#${branch}`} style={{ color: C.text, margin: '3px 0 0', overflowWrap: 'anywhere', fontSize: 12 }}>
              {repoUrl}#{branch}
            </dd>
          </div>
          <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: 10, background: C.bg }}>
            <dt style={{ color: C.textMuted, fontSize: 10 }}>Erwarteter Head</dt>
            <dd title={expectedHeadSha || 'Kein Head-SHA verfügbar'} data-testid="draft-pr-preview-head" style={{ color: C.sky, margin: '3px 0 0', overflowWrap: 'anywhere', fontFamily: 'monospace', fontSize: 11 }}>
              {expectedHeadSha || 'nicht verfügbar – der Server blockiert bei fehlender Head-Evidence'}
            </dd>
          </div>
          <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: 10, background: C.bg }}>
            <dt style={{ color: C.textMuted, fontSize: 10 }}>Gebundene Evidence</dt>
            <dd title={`${changedFileCount} Datei(en) · ${evidenceLabel}`} style={{ color: C.text, margin: '3px 0 0', fontSize: 12 }}>
              {changedFileCount} Datei(en) · {evidenceLabel}
            </dd>
          </div>
          <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: 10, background: C.bg }}>
            <dt style={{ color: C.textMuted, fontSize: 10 }}>Mission</dt>
            <dd title={mission || 'Create a reviewed Draft PR.'} style={{ color: C.text, margin: '3px 0 0', overflowWrap: 'anywhere', fontSize: 12 }}>
              {mission || 'Create a reviewed Draft PR.'}
            </dd>
          </div>
        </dl>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button
            type="button"
            autoFocus
            onClick={onCancel}
            data-testid="cancel-draft-pr-action-preview"
            className="focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:outline-none"
            aria-label="Abbrechen"
            title="Übergabe an Runtime abbrechen"
            style={{
              flex: '1 1 180px',
              minHeight: 46,
              borderRadius: 11,
              border: `1px solid ${C.border}`,
              background: C.bg,
              color: C.text,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={onConfirm}
            data-testid="confirm-draft-pr-action-preview"
            className="focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:outline-none"
            aria-label="Draft PR nach Serverprüfung posten"
            title="Draft PR nach Serverprüfung posten"
            style={{
              flex: '1 1 220px',
              minHeight: 46,
              borderRadius: 11,
              border: 'none',
              background: C.orange,
              color: '#fff',
              fontWeight: 800,
              cursor: 'pointer',
            }}
          >
            Draft PR nach Serverprüfung posten
          </button>
        </div>
      </section>
    </div>
  );
}
