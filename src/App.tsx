import './runtime-adapter';
import React, { useState } from 'react';
import { BuilderContainer } from './features/product/containers/BuilderContainer';
import { LlmAdapterProvider } from './features/product/contexts/LlmAdapterContext';

const CHAT_ONLY_STYLE: React.CSSProperties = {
  height: '100dvh',
  overflow: 'hidden',
  background: '#0e1116',
};

export default function App() {
  const [mission, setMission] = useState('GitHub-URL einfügen oder Auftrag schreiben.');
  const startChatOnlyTask = (nextMission: string) => setMission(nextMission);
  return (
    <LlmAdapterProvider>
      <main data-testid="chat-only-app" data-layout="chat-only-live-entry" aria-label="Sovereign Chat" style={CHAT_ONLY_STYLE}>
        <BuilderContainer
          mission={mission}
          repoReady={false}
          repoReason="GitHub-URL direkt im Chat einfügen."
          repoBusy={false}
          runtimeBusy={false}
          isPublishing={false}
          sovereignSummary="Sovereign ist bereit. Lade ein Repo per GitHub-URL im Chat oder beschreibe den nächsten Auftrag."
          sovereignPreview=""
          onMissionChange={setMission}
          onGenerateIdeas={() => setMission('Ideen/Build')}
          onGenerateErrorWorkflow={() => setMission('Fehleranalyse')}
          onPublishDraftPr={() => setMission('Draft PR')}
          openhandsReady={true}
          onStartOpenHands={startChatOnlyTask}
        />
      </main>
    </LlmAdapterProvider>
  );
}
