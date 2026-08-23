import React, { useMemo, useState } from 'react';
import { maskSecrets } from '../../../shared/utils/crypto';
import type { SovereignEvidenceVerdict, SovereignWorkspaceEvidenceAnchor } from '../runtime/sovereignAgentRuntime';
import { C } from './builderConstants';

export interface WorkspaceEvidenceRailProps {
  readonly anchors: readonly SovereignWorkspaceEvidenceAnchor[];
}

const VERDICT_VIEW: Readonly<Record<SovereignEvidenceVerdict, { icon: string; label: string; color: string }>> = {
  OBSERVED: { icon: '◉', label: 'Observed', color: C.sky },
  UNVERIFIED: { icon: '…', label: 'Unverified', color: C.amber },
  VERIFIED: { icon: '✓', label: 'Verified', color: C.green },
  BLOCKED: { icon: '⊘', label: 'Blocked', color: C.rose },
  CONTRADICTED: { icon: '!', label: 'Contradicted', color: C.rose },
  STALE: { icon: '↺', label: 'Stale', color: C.amber },
};

function short(value: string | undefined, width = 12): string {
  if (!value) return '—';
  return value.length > width ? `${value.slice(0, width)}…` : value;
}

function labelForClaim(claim: string): string {
  return claim.toLowerCase().split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function EvidenceInspector({ anchor, onClose }: { anchor: SovereignWorkspaceEvidenceAnchor; onClose: () => void }) {
  const view = VERDICT_VIEW[anchor.verdict];
  const rows: Array<[string, string]> = [
    ['Claim', labelForClaim(anchor.claimKind)],
    ['Verdict', view.label],
    ['Scope', anchor.scope],
    ['Attempt', anchor.attemptId],
    ['Action', anchor.actionId],
    ['Repository revision', anchor.repositoryRevision],
    ['Target revision', anchor.targetRevision ?? '—'],
    ['Image digest', anchor.imageDigest ?? '—'],
    ['Runtime identity', anchor.runtimeIdentityHash ?? '—'],
    ['Source', anchor.sourceKind],
    ['Observed', anchor.observedAt],
    ['Freshness', anchor.freshnessReasons.length ? anchor.freshnessReasons.join(', ') : 'current for the bound identity'],
  ];
  return (
    <div role="dialog" aria-modal="false" aria-label="Evidence Inspector" data-testid="workspace-evidence-inspector" style={{ border: `1px solid ${view.color}`, borderRadius: 8, padding: 10, background: '#0b0f14' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <strong style={{ color: view.color }}>{view.icon} {view.label}</strong>
        <span style={{ color: C.textMuted, fontFamily: 'monospace', fontSize: 10 }}>{short(anchor.evidenceHash, 16)}</span>
        <button type="button" onClick={onClose} aria-label="Evidence Inspector schließen" style={{ marginLeft: 'auto', color: C.textSub, background: 'transparent', border: 0, cursor: 'pointer' }}>×</button>
      </div>
      <dl style={{ display: 'grid', gridTemplateColumns: 'minmax(90px, auto) 1fr', gap: '4px 8px', margin: 0, fontSize: 10.5 }}>
        {rows.map(([name, value]) => (
          <React.Fragment key={name}>
            <dt style={{ color: C.textMuted }}>{name}</dt>
            <dd style={{ color: C.textSub, margin: 0, fontFamily: 'monospace', overflowWrap: 'anywhere' }}>{maskSecrets(value)}</dd>
          </React.Fragment>
        ))}
        <dt style={{ color: C.textMuted }}>Source refs</dt>
        <dd style={{ color: C.textSub, margin: 0, fontFamily: 'monospace', overflowWrap: 'anywhere' }}>{anchor.sourceRefs.map((ref) => short(ref, 18)).join(', ')}</dd>
      </dl>
      <p style={{ margin: '8px 0 0', color: C.textMuted, fontSize: 10 }}>Der Anchor verweist auf kanonische Quellen; Monitor/Frame sind selbst keine Success Authority.</p>
    </div>
  );
}

export function WorkspaceEvidenceRail({ anchors }: WorkspaceEvidenceRailProps) {
  const current = useMemo(() => {
    const ordered = [...anchors].sort((left, right) => Date.parse(left.observedAt) - Date.parse(right.observedAt));
    const latest = ordered[ordered.length - 1];
    if (!latest) return [];
    return ordered.filter((anchor) => (
      anchor.sessionBindingHash === latest.sessionBindingHash
      && anchor.attemptId === latest.attemptId
    )).slice(-6);
  }, [anchors]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = current.find((anchor) => anchor.anchorId === selectedId) ?? null;
  if (current.length === 0) return null;
  return (
    <section aria-label="Live Workspace Evidence" data-testid="workspace-evidence-rail" style={{ borderTop: `1px solid ${C.border}`, padding: '8px 12px', display: 'grid', gap: 7 }}>
      <div style={{ fontSize: 10.5, color: C.textMuted, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase' }}>Evidence · claim-granular</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {current.map((anchor) => {
          const view = VERDICT_VIEW[anchor.verdict];
          return (
            <button
              key={anchor.anchorId}
              type="button"
              onClick={() => setSelectedId((currentId) => currentId === anchor.anchorId ? null : anchor.anchorId)}
              aria-label={`${view.label}: ${labelForClaim(anchor.claimKind)}`}
              aria-expanded={selectedId === anchor.anchorId}
              style={{ border: `1px solid ${view.color}`, borderRadius: 999, padding: '4px 8px', color: view.color, background: '#0b0f14', cursor: 'pointer', fontSize: 10.5 }}
            >
              <span aria-hidden="true">{view.icon}</span> {view.label} · {labelForClaim(anchor.claimKind)}
            </button>
          );
        })}
      </div>
      {selected ? <EvidenceInspector anchor={selected} onClose={() => setSelectedId(null)} /> : null}
    </section>
  );
}
