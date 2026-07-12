import './runtime-adapter';
import React, { useEffect, useMemo, useState } from 'react';
import {
  BuilderContainer,
  type SovereignDraftPrPublishInput,
} from './features/product/containers/BuilderContainer';
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

  useEffect(() => {
    if (!agentConfig.ready || agentJob.status !== 'idle') return;
    let cancelled = false;
    let loading = false;
    const restoreLatestJob = async () => {
      if (loading) return;
      loading = true;
      try {
        const jobs = await agentClient.listJobs();
        if (cancelled || jobs.length === 0) return;
        setAgentJob((current) => current.status === 'idle' ? jobs[0] : current);
      } catch {
        // The first app render may precede login. Retry while idle so a later
        // authenticated session can recover its persisted runtime truth.
      } finally {
        loading = false;
      }
    };
    void restoreLatestJob();
    const timer = window.setInterval(() => { void restoreLatestJob(); }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [agentClient, agentConfig.ready, agentJob.status]);

  useEffect(() => {
    const jobId = agentJob.jobId;
    const active = ['queued', 'provisioning', 'running', 'validating'].includes(agentJob.status);
    if (!agentConfig.ready || !jobId || !active) return;
    let cancelled = false;
    let polling = false;
    const refresh = async () => {
      if (polling) return;
      polling = true;
      try {
        const snapshot = await agentClient.getJob(jobId);
        if (!cancelled) {
          setAgentJob((current) => current.jobId === jobId ? snapshot : current);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Agent-Status konnte nicht aktualisiert werden.';
        if (!cancelled) {
          setAgentJob((current) => {
            if (current.jobId !== jobId) return current;
            const alreadyReported = current.events.some((event) => event.stage === 'agent-poll-blocked' && event.message === message);
            return alreadyReported ? current : {
              ...current,
              lastError: message,
              events: [...current.events, { at: Date.now(), level: 'warning', stage: 'agent-poll-blocked', message }],
            };
          });
        }
      } finally {
        polling = false;
      }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [agentClient, agentConfig.ready, agentJob.jobId, agentJob.status]);

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
      const snapshot = await agentClient.startToolchainJob({
        repoUrl: input.repoUrl,
        branch: input.branch,
        mission: nextMission,
        evidenceText: nextMission,
        provisionWorkspace: true,
        cloneRepo: false,
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

  const publishDraftPr = async (input?: SovereignDraftPrPublishInput) => {
    let jobId = agentJob.jobId;
    let repoUrl = agentJob.repoUrl;

    if (input?.changes && input.changes.length > 0) {
      try {
        const snapshot = await agentClient.startToolchainJob({
          repoUrl: input.repoUrl,
          branch: input.branch,
          mission: input.mission,
          stagedFiles: input.changes,
          cloneRepo: true,
          provisionWorkspace: true,
          draftPrOnly: true,
          githubAccessToken: input.githubAccessToken,
        });
        jobId = snapshot.jobId;
        repoUrl = snapshot.repoUrl;
        setAgentJob(snapshot);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Staging der Änderungen fehlgeschlagen.';
        setAgentJob((current) => ({
          ...current,
          status: 'blocked',
          lastError: message,
          events: [...current.events, { at: Date.now(), level: 'error', stage: 'draft-pr-staging-failed', message }],
        }));
        return;
      }
    }

    if (!repoUrl || !jobId) {
      const message = 'Draft PR benötigt zuerst einen belegten Sovereign-Agent-Job mit Repository.';
      setAgentJob((current) => ({
        ...current,
        status: 'blocked',
        lastError: message,
        events: [...current.events, { at: Date.now(), level: 'warning', stage: 'draft-pr-requires-job', message }],
      }));
      return;
    }

    setAgentJob((current) => ({
      ...current,
      status: 'validating',
      lastError: undefined,
      events: [...current.events, {
        at: Date.now(),
        level: 'info',
        stage: 'draft-pr-prepare',
        message: 'Persistierte Changed-File-, Diff- und Test-Evidence wird geprüft.',
      }],
    }));

    try {
      const preparation = await agentClient.prepareDraftPr(jobId);
      if (!preparation.ok || !preparation.draftPrPreparation.allowed) {
        throw new Error(
          preparation.draftPrPreparation.blockers.join('; ')
          || preparation.draftPrPreparation.summary
          || 'Draft-PR-Vorbereitung wurde durch die Runtime blockiert.',
        );
      }

      const creation = await agentClient.createDraftPr(jobId);
      if (!creation.ok || !creation.draftPrCreate.allowed || !creation.draftPrCreate.prUrl) {
        throw new Error(
          creation.draftPrCreate.blocker
          || creation.draftPrCreate.summary
          || 'GitHub hat keinen belegten Draft PR bestätigt.',
        );
      }

      const snapshot = await agentClient.getJob(jobId);
      setAgentJob({
        ...snapshot,
        status: 'completed',
        draftPrUrl: snapshot.draftPrUrl || creation.draftPrCreate.prUrl,
        events: [...snapshot.events, {
          at: Date.now(),
          level: 'success',
          stage: 'draft-pr-created',
          message: `GitHub Draft PR erstellt: ${creation.draftPrCreate.prUrl}`,
        }],
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Draft-PR-Übergabe fehlgeschlagen.';
      setAgentJob((current) => ({
        ...current,
        status: 'blocked',
        lastError: message,
        events: [...current.events, { at: Date.now(), level: 'error', stage: 'draft-pr-blocked', message }],
      }));
    }
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
