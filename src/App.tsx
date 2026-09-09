import React from 'react';
import { EvidenceObservatoryAtlas } from './features/evidence-observatory/EvidenceObservatoryAtlas';
import SovereignControlSurfaceVNext from './features/control-surface-vnext/App';

const CHAT_FIRST_STYLE: React.CSSProperties = {
  height: '100dvh',
  overflow: 'hidden',
  background: '#0e1116',
};

/**
 * Canonical browser entry for Sovereign.
 *
 * The default client is the vNext control surface. It does not auto-adopt an
 * unrelated persisted run as current truth: a mission handle becomes current
 * only after this surface receives the real runId from the backend. Runtime,
 * workspace and publication panels remain projections of server readback.
 *
 * Draft PR publication is a separate owner-visible action and remains bound to
 * the existing backend prepare/create gates and strict GitHub readback.
 */
export default function App() {
  const observatoryMode = typeof window !== 'undefined'
    && (window.location.pathname === '/observatory'
      || window.location.pathname === '/evidence-observatory'
      || new URLSearchParams(window.location.search).get('observatory') === '1');

  if (observatoryMode) return <EvidenceObservatoryAtlas />;

  return (
    <div
      data-testid="sovereign-chat-app"
      data-layout="sovereign-control-surface-vnext"
      data-primary-surface="sovereign-control-surface-vnext"
      data-truth-scope="runtime-readback-only"
      aria-label="Sovereign Control Surface"
      style={CHAT_FIRST_STYLE}
    >
      <SovereignControlSurfaceVNext />
    </div>
  );
}
