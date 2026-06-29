import './runtime-adapter';
import React, { useCallback, useState } from 'react';
import { BuilderContainer } from './features/product/containers/BuilderContainer';
import { LlmAdapterProvider } from './features/product/contexts/LlmAdapterContext';

const INITIAL_CHAT_MISSION = 'GitHub-URL einfügen oder Auftrag schreiben.';

const CHAT_ONLY_STYLE = `
  html,
  body,
  #root {
    height: 100%;
    margin: 0;
    overflow: hidden;
    background: #0e1116;
  }

  [data-testid="chat-only-app"] {
    width: 100%;
    height: 100dvh;
    min-height: 100dvh;
    overflow: hidden;
    background: #0e1116;
  }

  [data-testid="chat-only-app"] [data-testid="builder-container"] {
    height: 100dvh !important;
    max-height: 100dvh !important;
    width: 100% !important;
    max-width: min(100vw, 640px) !important;
    margin: 0 auto !important;
  }

  @media (max-width: 520px) {
    [data-testid="chat-only-app"] [data-testid="builder-container"] {
      max-width: 100vw !important;
    }
  }

  @media (min-width: 768px) {
    [data-testid="chat-only-app"] {
      display: flex;
      justify-content: center;
    }

    [data-testid="chat-only-app"] [data-testid="builder-container"] {
      border-left: 1px solid rgba(148, 163, 184, 0.14);
      border-right: 1px solid rgba(148, 163, 184, 0.14);
      box-shadow: 0 0 40px rgba(0, 0, 0, 0.28);
    }
  }
`;

export default function App() {
  const [mission, setMission] = useState(INITIAL_CHAT_MISSION);
  const [summary, setSummary] = useState(
    'Sovereign ist bereit. Lade ein Repo per GitHub-URL im Chat oder beschreibe den nächsten Auftrag.',
  );

  const updateMission = useCallback((nextMission: string) => {
    setMission(nextMission);

    const clean = nextMission.trim();
    if (!clean) return;

    if (clean.startsWith('Repo laden via Chat:')) {
      setSummary('Repo-Kontext wurde im Chat übernommen. Was soll Sovereign daran ändern oder prüfen?');
      return;
    }

    setSummary('Auftrag im Chat übernommen. Sovereign hält die Kontrollflächen im Hintergrund und zeigt nur den nächsten sinnvollen Schritt.');
  }, []);

  const startChatOnlyTask = useCallback((nextMission: string) => {
    setMission(nextMission);
    setSummary(
      'Auftrag übernommen. Die Arbeitsumgebung bleibt hinter dem Chat; sichtbare nächste Schritte erscheinen nur hier im Verlauf.',
    );
  }, []);

  const explainHiddenFeature = useCallback((label: string) => {
    setSummary(`${label} bleibt im Chat-only Live-Pfad eine optionale Chat-Aktion, keine separate sichtbare Arbeitsfläche.`);
  }, []);

  return (
    <LlmAdapterProvider>
      <main
        data-testid="chat-only-app"
        data-layout="chat-only-live-entry"
        aria-label="Sovereign Chat"
      >
        <style>{CHAT_ONLY_STYLE}</style>
        <BuilderContainer
          mission={mission}
          repoReady={false}
          repoReason="GitHub-URL direkt im Chat einfügen."
          repoBusy={false}
          runtimeBusy={false}
          isPublishing={false}
          sovereignSummary={summary}
          sovereignPreview=""
          onMissionChange={updateMission}
          onGenerateIdeas={() => explainHiddenFeature('Ideen/Build')}
          onGenerateErrorWorkflow={() => explainHiddenFeature('Fehleranalyse')}
          onPublishDraftPr={() => explainHiddenFeature('Draft PR')}
          openhandsReady={true}
          onStartOpenHands={startChatOnlyTask}
        />
      </main>
    </LlmAdapterProvider>
  );
}
