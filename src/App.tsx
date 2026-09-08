import React from 'react';
import { EvidenceObservatoryAtlas } from './features/evidence-observatory/EvidenceObservatoryAtlas';
import { PlayReleaseChat } from './features/release/PlayReleaseChat';
import { SovereignRescueOverlay } from './features/rescue/SovereignRescueOverlay';

const CHAT_FIRST_STYLE: React.CSSProperties = {
  height: '100dvh',
  overflow: 'hidden',
  background: '#0e1116',
};

/**
 * Canonical browser entry for Sovereign.
 *
 * The default client projects only the current Play Release chat session. It
 * does not auto-adopt a previously persisted Agent job as current truth. Older
 * jobs remain backend history and must be explicitly read/adopted by a bounded
 * workflow before they can affect current product state.
 *
 * Rescue remains available through its own current-session job bridge. It may
 * only publish a job returned through that overlay's exact job-id readback and
 * never adopts a historical "latest job" implicitly.
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
      data-layout="chat-first-agent-zero-background"
      data-primary-surface="play-release-chat"
      data-truth-scope="current-chat-session-only"
      aria-label="Sovereign Chat"
      style={CHAT_FIRST_STYLE}
    >
      <PlayReleaseChat />
      <SovereignRescueOverlay />
    </div>
  );
}
