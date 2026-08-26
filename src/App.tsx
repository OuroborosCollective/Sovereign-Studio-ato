import './runtime-adapter';
import React from 'react';
import { EvidenceObservatoryAtlas } from './features/evidence-observatory/EvidenceObservatoryAtlas';
import { PlayReleaseChat } from './features/release/PlayReleaseChat';

export default function App() {
  const observatoryMode = typeof window !== 'undefined'
    && (window.location.pathname === '/observatory'
      || window.location.pathname === '/evidence-observatory'
      || new URLSearchParams(window.location.search).get('observatory') === '1');

  return observatoryMode ? <EvidenceObservatoryAtlas /> : <PlayReleaseChat />;
}
