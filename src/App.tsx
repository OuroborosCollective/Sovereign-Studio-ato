import './runtime-adapter';
import React, { useMemo, useState } from 'react';
import { BuilderContainer } from './features/product/containers/BuilderContainer';
import { LlmAdapterProvider } from './features/product/contexts/LlmAdapterContext';
import {
  createSovereignAgentClient,
  type SovereignAgentStartJobInput,
} from './features/product/runtime/sovereignAgentClient';
import {
  createSovereignAgentIdleSnapshot,
  resolveSovereignAgentConfig,
  summarizeSovereignAgentJob,
  type SovereignAgentJobSnapshot,
} from './features/product/runtime/sovereignAgentRuntime';

const CHAT_ONLY_STYLE: React.CSSProperties = {
  height: '100dvh',
  overflow: 'hidden',
  background: '#0e1116',
};

export default function App() {
  const [mission, setMission] = useState('GitHub-URL einfügen oder Auftrag schreiben.');
  const agentConfig = useMemo(() => resolveSovereignAgentConfig(), []);
  const agentClient = useMemo(
    () => createSovereignAgentClient({ config: agentConfig }),
    [agentConfig],
  );
  const [agentJob, setAgentJob] = useState<SovereignAgentJobSnapshot>(
    () => createSovereignAgentIdleSnapshot(),
  );
  const [janitorPreview, setJanitorPreview] = useState('');

  const startChatOnlyTask = async (nextMission: string, input?: Partial<SovereignAgentStartJobInput>) => {
    setMission(nextMission);
    setJanitorPreview('');
    if (!agentConfig.ready) {
      setAgentJob({
        status: 'blocked',
        changedFiles: [],
        events: [{ at: Date.now(), level: 'error', stage: 'agent-config', message: agentConfig.reason }],
        lastError: agentConfig.reason,
      });
      return;
    }
    if (!input?.repoUrl) {
      setAgentJob({
        status: 'blocked',
        changedFiles: [],
        events: [{ at: Date.now(), level: 'error', stage: 'agent-request', message: 'Repository URL fehlt.' }],
        lastError: 'Repository URL fehlt.',
      });
      return;
    }
    setAgentJob({
      status: 'queued',
      repoUrl: input.repoUrl,
      branch: input.branch || 'main',
      changedFiles: [],
      events: [{ at: Date.now(), level: 'info', stage: 'agent-request', message: 'Auftrag an die Sovereign Agent Runtime übergeben.' }],
    });
    try {
      const snapshot = await agentClient.startJob({
        repoUrl: input.repoUrl,
        branch: input.branch,
        mission: nextMission,
      });
      setAgentJob(snapshot);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Agent Runtime Start fehlgeschlagen.';
      setAgentJob({
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
    const jobId = agentJob.jobId;
    if (!agentConfig.ready || !jobId) return;
    try {
      const snapshot = await agentClient.cancelJob(jobId);
      setAgentJob(snapshot);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Agent Runtime Stop fehlgeschlagen.';
      setAgentJob((current) => ({
        ...current,
        status: 'failed',
        lastError: message,
        events: [...current.events, { at: Date.now(), level: 'error', stage: 'agent-cancel', message }],
      }));
    }
  };

  const runJanitorScan = async () => {
    setMission('Fehleranalyse');
    const jobId = agentJob.jobId;
    if (!agentConfig.ready || !jobId) {
      const message = 'Für den Janitor zuerst ein Repository als Sovereign-Agent-Job laden.';
      setAgentJob((current) => ({
        ...current,
        lastError: message,
        events: [...current.events, { at: Date.now(), level: 'warning', stage: 'janitor-requires-repo', message }],
      }));
      return;
    }
    setAgentJob((current) => ({
      ...current,
      events: [...current.events, { at: Date.now(), level: 'info', stage: 'janitor-scan', message: 'Deterministischer Janitor-Scan gestartet.' }],
    }));
    try {
      const response = await agentClient.runJanitor(jobId, {
        mode: 'scan',
        family: 'Runtime-Wahrheit, Zustandswidersprüche, sichere Repo-Automation',
        maxFindings: 10,
        maxFiles: 200,
      });
      const findings = Array.isArray(response.tool.metadata.findings) ? response.tool.metadata.findings : [];
      const recommendedTestCommand = typeof response.tool.metadata.recommendedTestCommand === 'string'
        ? response.tool.metadata.recommendedTestCommand
        : undefined;
      setJanitorPreview(JSON.stringify({
        summary: response.tool.output,
        findingCount: findings.length,
        findings,
        recommendedTestCommand,
        writeAction: false,
      }, null, 2));
      setAgentJob((current) => ({
        ...current,
        lastError: undefined,
        events: [...current.events, {
          at: Date.now(),
          level: 'success',
          stage: 'janitor-scan-completed',
          message: `${findings.length} Janitor-Befund(e) gefunden. Es wurde keine Datei verändert.`,
        }],
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Janitor-Scan fehlgeschlagen.';
      setAgentJob((current) => ({
        ...current,
        lastError: message,
        events: [...current.events, { at: Date.now(), level: 'error', stage: 'janitor-scan-failed', message }],
      }));
    }
  };

  const agentIsRunning = agentJob.status === 'queued' || agentJob.status === 'provisioning' || agentJob.status === 'running' || agentJob.status === 'validating';
  const repoReady = Boolean(agentJob.repoUrl && agentJob.status !== 'idle');
  const repoBusy = agentJob.status === 'queued' || agentJob.status === 'provisioning';
  const runtimeSummary = summarizeSovereignAgentJob(agentJob);

  const publishDraftPr = () => {
    if (!agentJob.repoUrl) {
      const message = 'Draft PR benötigt zuerst ein durch die Runtime belegtes Repository.';
      setAgentJob((current) => ({
        ...current,
        lastError: message,
        events: [...current.events, { at: Date.now(), level: 'warning', stage: 'draft-pr-requires-repo', message }],
      }));
      return;
    }
    void startChatOnlyTask('Draft PR aus den belegten Änderungen erstellen', {
      repoUrl: agentJob.repoUrl,
      branch: agentJob.branch,
    });
  };

  return (
    <LlmAdapterProvider>
      <main data-testid="chat-only-app" data-layout="chat-only-live-entry" aria-label="Sovereign Chat" style={CHAT_ONLY_STYLE}>
        <BuilderContainer
          mission={mission}
          repoReady={repoReady}
          repoReason={repoReady ? `Runtime-Repository: ${agentJob.repoUrl}` : 'GitHub-URL direkt im Chat einfügen.'}
          repoBusy={repoBusy}
          runtimeBusy={agentIsRunning}
          isPublishing={agentJob.status === 'validating'}
          sovereignSummary={runtimeSummary}
          sovereignPreview={janitorPreview}
          onMissionChange={setMission}
          onGenerateIdeas={() => setMission('Ideen/Build')}
          onGenerateErrorWorkflow={() => { void runJanitorScan(); }}
          onPublishDraftPr={publishDraftPr}
          agentReady={agentConfig.ready}
          agentConfig={agentConfig}
          agentJob={agentJob}
          agentJobStatus={agentIsRunning ? 'Sovereign Agent Auftrag läuft' : agentJob.lastError}
          agentIsRunning={agentIsRunning}
          onStartAgent={startChatOnlyTask}
          onCancelAgent={cancelChatOnlyTask}
        />
      </main>
    </LlmAdapterProvider>
  );
}
