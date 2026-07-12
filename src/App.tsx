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
        provisionWorkspace: input.provisionWorkspace ?? true,
        cloneRepo: input.cloneRepo ?? true,
        stagedFiles: input.stagedFiles,
        testCommand: input.testCommand,
        githubAccessToken: input.githubAccessToken,
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

  const publishDraftPr = async (input: SovereignDraftPrPublishInput): Promise<void> => {
    if (!agentConfig.ready) throw new Error(agentConfig.reason);
    if (!input.repoUrl.trim()) throw new Error('Draft PR benötigt ein belegtes Repository.');
    if (input.changes.length > 0 && !input.confirmed) {
      throw new Error('Die staged Änderungen wurden noch nicht bestätigt.');
    }

    let workingJob = agentJob;
    const sameRepositoryJob = Boolean(
      workingJob.jobId
      && workingJob.repoUrl === input.repoUrl
      && (workingJob.branch || 'main') === (input.branch || 'main'),
    );

    try {
      if (input.changes.length > 0) {
        setAgentJob({
          status: 'queued',
          repoUrl: input.repoUrl,
          branch: input.branch || 'main',
          changedFiles: [],
          events: [{
            at: Date.now(),
            level: 'info',
            stage: 'staged-change-handoff',
            message: `${input.changes.length} bestätigte Dateiänderung(en) werden in einen isolierten Workspace übertragen.`,
          }],
        });
        workingJob = await agentClient.startToolchainJob({
          repoUrl: input.repoUrl,
          branch: input.branch,
          mission: input.mission,
          evidenceText: input.mission,
          provisionWorkspace: true,
          cloneRepo: true,
          stagedFiles: input.changes.map((change) => ({
            path: change.path,
            content: change.content,
            baseContent: change.baseContent,
          })),
          githubAccessToken: input.githubAccessToken,
        });
        setAgentJob(workingJob);
      } else if (!sameRepositoryJob || !workingJob.jobId) {
        throw new Error('Kein passender belegter Agent-Job für dieses Repository vorhanden.');
      }

      const jobId = workingJob.jobId;
      if (!jobId) throw new Error('Backend hat keine Job-ID für die Draft-PR-Übergabe geliefert.');
      if ((workingJob.changedFiles?.length ?? 0) === 0) {
        throw new Error(workingJob.lastError || 'Backend hat keine Changed-File-Evidence geliefert.');
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

      const preparation = await agentClient.prepareDraftPr(jobId);
      if (!preparation.ok || !preparation.draftPrPreparation.allowed) {
        throw new Error(
          preparation.draftPrPreparation.blockers.join('; ')
          || preparation.draftPrPreparation.summary
          || 'Draft-PR-Vorbereitung wurde blockiert.',
        );
      }

      const creation = await agentClient.createDraftPr(jobId, input.githubAccessToken);
      const prUrl = creation.draftPrCreate.prUrl || '';
      if (
        !creation.ok
        || !creation.draftPrCreate.allowed
        || !/^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/[0-9]+$/.test(prUrl)
      ) {
        throw new Error(
          creation.draftPrCreate.blocker
          || creation.draftPrCreate.summary
          || 'GitHub hat keinen gültigen Draft-PR-Link bestätigt.',
        );
      }

      const persisted = await agentClient.getJob(jobId);
      const persistedUrl = persisted.draftPrUrl || prUrl;
      if (!/^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/[0-9]+$/.test(persistedUrl)) {
        throw new Error('Der finale Backend-Job enthält keinen gültigen Draft-PR-Link.');
      }
      setAgentJob({
        ...persisted,
        status: 'completed',
        draftPrUrl: persistedUrl,
        lastError: undefined,
        events: [...persisted.events, {
          at: Date.now(),
          level: 'success',
          stage: 'draft-pr-created',
          message: `GitHub Draft PR bestätigt: ${persistedUrl}`,
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
      throw error;
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
