import './runtime-adapter';
import React, { useState } from 'react';
import { AuditLiveWorkbench } from './features/product/components/AuditLiveWorkbench';
import { LlmAdapterProvider } from './features/product/contexts/LlmAdapterContext';

export default function App() {
  const [mission, setMission] = useState('GitHub-URL einfügen oder Auftrag schreiben.');
  return (
    <LlmAdapterProvider>
      <main data-testid="chat-only-app" aria-label="Sovereign Chat" style={{ height: '100dvh', overflow: 'hidden', background: '#0e1116' }}>
        <AuditLiveWorkbench
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
          onStartOpenHands={setMission}
        />
      </main>
    </LlmAdapterProvider>
  );
}
