import './runtime-adapter';
import React, { useMemo, useState } from 'react';
import { BuilderContainer } from './features/product/containers/BuilderContainer';
import { LlmAdapterProvider } from './features/product/contexts/LlmAdapterContext';
import {
  createOpenHandsEnterpriseClient,
  type OpenHandsStartJobInput,
} from './features/product/runtime/openhandsEnterpriseClient';
import {
  createOpenHandsIdleSnapshot,
  resolveOpenHandsEnterpriseConfig,
  type OpenHandsJobSnapshot,
} from './features/product/runtime/openhandsEnterpriseRuntime';

const CHAT_ONLY_STYLE: React.CSSProperties = {
  height: '100dvh',
  overflow: 'hidden',
  background: '#0e1116',
};

export default function App() {
  const [mission, setMission] = useState('GitHub-URL einfügen oder Auftrag schreiben.');
  const openhandsConfig = useMemo(() => resolveOpenHandsEnterpriseConfig(), []);
  const openhandsClient = useMemo(
    () => createOpenHandsEnterpriseClient({ config: openhandsConfig }),
    [openhandsConfig],
  );
  const [openhandsJob, setOpenHandsJob] = useState<OpenHandsJobSnapshot>(
    () => createOpenHandsIdleSnapshot(),
  );

  const startChatOnlyTask = async (nextMission: string, input?: Partial<OpenHandsStartJobInput>) => {
    setMission(nextMission);
    if (!openhandsConfig.ready) {
      setOpenHandsJob({
        status: 'blocked',
        changedFiles: [],
        events: [{ at: Date.now(), level: 'error', stage: 'agent-config', message: openhandsConfig.reason }],
        lastError: openhandsConfig.reason,
      });
      return;
    }
    if (!input?.repoUrl) {
      setOpenHandsJob({
        status: 'blocked',
        changedFiles: [],
        events: [{ at: Date.now(), level: 'error', stage: 'agent-request', message: 'Repository URL fehlt.' }],
        lastError: 'Repository URL fehlt.',
      });
      return;
    }
    setOpenHandsJob({
      status: 'queued',
      repoUrl: input.repoUrl,
      branch: input.branch || 'main',
      changedFiles: [],
      events: [{ at: Date.now(), level: 'info', stage: 'agent-request', message: 'Auftrag an die Sovereign Agent Runtime übergeben.' }],
    });
    try {
      const snapshot = await openhandsClient.startJob({
        repoUrl: input.repoUrl,
        branch: input.branch,
        mission: nextMission,
      });
      setOpenHandsJob(snapshot);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Agent Runtime Start fehlgeschlagen.';
      setOpenHandsJob({
        status: 'failed',
        repoUrl: input.repoUrl,
        branch: input.branch || 'main',
        changedFiles: [],
        events: [{ at: Date.now(), level: 'error', stage: 'agent-start', message }],
        lastError: message,
      });
    }
  };

  const cancelChatOnlyTask = async () => {
    const jobId = openhandsJob.jobId;
    if (!openhandsConfig.ready || !jobId) return;
    try {
      const snapshot = await openhandsClient.cancelJob(jobId);
      setOpenHandsJob(snapshot);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Agent Runtime Stop fehlgeschlagen.';
      setOpenHandsJob((current) => ({
        ...current,
        status: 'failed',
        lastError: message,
        events: [...current.events, { at: Date.now(), level: 'error', stage: 'agent-cancel', message }],
      }));
    }
  };

  const openhandsIsRunning = openhandsJob.status === 'queued' || openhandsJob.status === 'provisioning' || openhandsJob.status === 'running' || openhandsJob.status === 'validating';

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
          openhandsReady={openhandsConfig.ready}
          openhandsConfig={openhandsConfig}
          openhandsJob={openhandsJob}
          openhandsJobStatus={openhandsIsRunning ? 'Sovereign Agent Auftrag läuft' : openhandsJob.lastError}
          openhandsIsRunning={openhandsIsRunning}
          onStartOpenHands={startChatOnlyTask}
          onCancelOpenHands={cancelChatOnlyTask}
        />
      </main>
    </LlmAdapterProvider>
  );
}
