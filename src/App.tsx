import './runtime-adapter';
import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import {
  BuilderContainer,
  type SovereignDraftPrPublishInput,
} from './features/product/containers/BuilderContainer';
import { LlmAdapterProvider } from './features/product/contexts/LlmAdapterContext';
import {
  createSovereignAgentClient,
  type SovereignAgentStartJobInput,
  type SovereignPatternLearningEvidence,
} from './features/product/runtime/sovereignAgentClient';
import {
  isSovereignAgentTerminalStatus,
  resolveSovereignAgentConfig,
  summarizeSovereignAgentJob,
} from './features/product/runtime/sovereignAgentRuntime';
import {
  createInitialSovereignEngineState,
  createSovereignClientBoundaryBlockedEvent,
  createSovereignEngineCommand,
  createSovereignEngineCommandAcceptedEvent,
  createSovereignEngineCommandFailedEvent,
  executeSovereignEngineCommand,
  hasSovereignEnginePendingCommand,
  selectSovereignEngineJobProjection,
  sovereignEngineJobFromEvent,
  sovereignEngineOperationResultFromEvent,
  sovereignEngineReducer,
  type SovereignEngineCommandV1,
} from './features/product/runtime/sovereignEngineBoundary';
import {
  reusableMemoryContext,
  searchReusableMemory,
} from './features/knowledge/knowledgeApi';
import { RescuePanel } from './features/rescue/RescuePanel';
import { EvidenceObservatoryAtlas } from './features/evidence-observatory/EvidenceObservatoryAtlas';

const MONITOR_FIRST_STYLE: React.CSSProperties = {
  height: '100dvh',
  overflow: 'hidden',
  background: '#0e1116',
};

function SovereignMonitorApp() {
  const [mission, setMission] = useState('GitHub-URL einfügen oder Auftrag an das LLM geben.');
  const agentConfig = useMemo(() => resolveSovereignAgentConfig(), []);
  const agentClient = useMemo(
    () => createSovereignAgentClient({ config: agentConfig }),
    [agentConfig],
  );
  const [engineState, dispatchEngineEvent] = useReducer(
    sovereignEngineReducer,
    undefined,
    () => createInitialSovereignEngineState(),
  );
  const canonicalAgentJob = engineState.canonicalJob;
  const agentJob = selectSovereignEngineJobProjection(engineState);
  const liveProjections = engineState.projections;
  const liveEvidenceAnchors = engineState.evidenceAnchors;
  const [janitorPreview, setJanitorPreview] = useState('');
  const [patternLearningEvidence, setPatternLearningEvidence] = useState<
    SovereignPatternLearningEvidence | undefined
  >();
  const [desktopFrame, setDesktopFrame] = useState<{
    readonly url: string;
    readonly frameHash: string;
    readonly observedAt: number;
  } | null>(null);
  const desktopFrameUrlRef = useRef<string | null>(null);
  const [rescueOpen, setRescueOpen] = useState(
    () => typeof window !== 'undefined'
      && new URLSearchParams(window.location.search).get('rescue') === '1',
  );

  const runEngineCommand = useCallback(async (command: SovereignEngineCommandV1) => {
    dispatchEngineEvent(createSovereignEngineCommandAcceptedEvent(command));
    try {
      const event = await executeSovereignEngineCommand(command, agentClient);
      dispatchEngineEvent(event);
      return event;
    } catch (error) {
      dispatchEngineEvent(createSovereignEngineCommandFailedEvent(command, error));
      throw error;
    }
  }, [agentClient]);

  const blockClientBoundary = useCallback((
    operation: string,
    message: string,
    context: { repoUrl?: string; branch?: string } = {},
  ) => {
    dispatchEngineEvent(createSovereignClientBoundaryBlockedEvent(
      engineState.sessionId,
      operation,
      message,
      context,
    ));
  }, [engineState.sessionId]);

  useEffect(() => {
    if (!agentConfig.ready || canonicalAgentJob.status !== 'idle') return;
    let cancelled = false;
    let loading = false;
    const restoreLatestJob = async () => {
      if (loading) return;
      loading = true;
      const command = createSovereignEngineCommand(
        engineState.sessionId,
        'RESTORE_LATEST_JOB',
        {},
      );
      try {
        await runEngineCommand(command);
      } catch {
        // The first app render may precede login. The typed failure event is
        // intentionally non-user-visible and the restore is retried while idle.
      } finally {
        loading = false;
      }
    };
    void restoreLatestJob();
    const timer = window.setInterval(() => {
      if (!cancelled) void restoreLatestJob();
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [agentConfig.ready, canonicalAgentJob.status, engineState.sessionId, runEngineCommand]);

  useEffect(() => {
    const jobId = canonicalAgentJob.jobId;
    const active = ['queued', 'provisioning', 'running', 'validating'].includes(canonicalAgentJob.status);
    if (!agentConfig.ready || !jobId || !active) return;
    let cancelled = false;
    let polling = false;
    const refresh = async () => {
      if (polling || cancelled) return;
      polling = true;
      const command = createSovereignEngineCommand(
        engineState.sessionId,
        'READ_JOB',
        { jobId },
      );
      try {
        await runEngineCommand(command);
      } catch {
        // Poll failures remain bounded control observations. They never patch
        // the last canonical job snapshot or invent a replacement status.
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
  }, [agentConfig.ready, canonicalAgentJob.jobId, canonicalAgentJob.status, engineState.sessionId, runEngineCommand]);

  useEffect(() => {
    const jobId = canonicalAgentJob.jobId;
    if (!agentConfig.ready || !jobId || canonicalAgentJob.status === 'idle' || canonicalAgentJob.status === 'cleaned') {
      return;
    }
    let cancelled = false;
    let polling = false;
    const refresh = async () => {
      if (polling || cancelled) return;
      polling = true;
      const projectionCommand = createSovereignEngineCommand(
        engineState.sessionId,
        'READ_PROJECTIONS',
        { jobId },
      );
      const evidenceCommand = createSovereignEngineCommand(
        engineState.sessionId,
        'READ_EVIDENCE_ANCHORS',
        { jobId },
      );
      try {
        await Promise.allSettled([
          runEngineCommand(projectionCommand),
          runEngineCommand(evidenceCommand),
        ]);
      } finally {
        polling = false;
      }
    };
    void refresh();
    if (isSovereignAgentTerminalStatus(canonicalAgentJob.status)) {
      return () => { cancelled = true; };
    }
    const timer = window.setInterval(() => { void refresh(); }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [agentConfig.ready, canonicalAgentJob.jobId, canonicalAgentJob.status, engineState.sessionId, runEngineCommand]);

  useEffect(() => {
    const jobId = canonicalAgentJob.jobId;
    const canReadFrame = Boolean(
      agentConfig.ready
      && jobId
      && canonicalAgentJob.status !== 'idle'
      && canonicalAgentJob.status !== 'cleaned'
      && typeof URL.createObjectURL === 'function',
    );
    const clearFrame = () => {
      const previous = desktopFrameUrlRef.current;
      desktopFrameUrlRef.current = null;
      if (previous && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(previous);
      setDesktopFrame(null);
    };
    if (!canReadFrame || !jobId) {
      clearFrame();
      return;
    }

    let cancelled = false;
    let polling = false;
    const refresh = async () => {
      if (cancelled || polling) return;
      polling = true;
      try {
        const observed = await agentClient.getDesktopFrame(jobId);
        if (cancelled) return;
        const nextUrl = URL.createObjectURL(observed.blob);
        const previous = desktopFrameUrlRef.current;
        desktopFrameUrlRef.current = nextUrl;
        setDesktopFrame({
          url: nextUrl,
          frameHash: observed.frameHash,
          observedAt: observed.observedAt,
        });
        if (previous && previous !== nextUrl && typeof URL.revokeObjectURL === 'function') {
          URL.revokeObjectURL(previous);
        }
      } catch {
        if (!cancelled) clearFrame();
      } finally {
        polling = false;
      }
    };
    void refresh();
    if (isSovereignAgentTerminalStatus(canonicalAgentJob.status)) {
      return () => { cancelled = true; };
    }
    const timer = window.setInterval(() => { void refresh(); }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [agentClient, agentConfig.ready, canonicalAgentJob.jobId, canonicalAgentJob.status]);

  useEffect(() => () => {
    const previous = desktopFrameUrlRef.current;
    if (previous && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(previous);
    desktopFrameUrlRef.current = null;
  }, []);

  const evidenceWithReusableMemory = async (query: string): Promise<string> => {
    try {
      const memory = await searchReusableMemory(query, 6);
      const context = reusableMemoryContext(memory);
      return context ? `${query}\n\n${context}` : query;
    } catch {
      // Login, embeddings or memory may be unavailable. Recall must never
      // prevent a real agent job from starting.
      return query;
    }
  };

  const startMonitorTask = async (nextMission: string, input?: Partial<SovereignAgentStartJobInput>) => {
    setMission(nextMission);
    setJanitorPreview('');
    setPatternLearningEvidence(undefined);
    if (!agentConfig.ready) {
      blockClientBoundary('agent-config', agentConfig.reason);
      return;
    }
    if (!input?.repoUrl) {
      blockClientBoundary('agent-request', 'Repository URL fehlt.');
      return;
    }
    try {
      const evidenceText = await evidenceWithReusableMemory(nextMission);
      const command = createSovereignEngineCommand(
        engineState.sessionId,
        'START_REPOSITORY_EXECUTION',
        {
          input: {
            repoUrl: input.repoUrl,
            branch: input.branch,
            expectedHeadSha: input.expectedHeadSha,
            mission: nextMission,
            evidenceText,
            githubAccessToken: input.githubAccessToken,
          },
        },
      );
      await runEngineCommand(command);
    } catch {
      // The typed command-failure event carries the bounded UI notice. It does
      // not fabricate a failed canonical runtime snapshot.
    }
  };

  const cancelMonitorTask = async () => {
    const jobId = canonicalAgentJob.jobId;
    if (!agentConfig.ready || !jobId) return;
    const command = createSovereignEngineCommand(
      engineState.sessionId,
      'CANCEL_JOB',
      { jobId },
    );
    try {
      await runEngineCommand(command);
    } catch {
      // Failure is represented by a typed local notice; canonical job truth is
      // left at the last backend-confirmed snapshot.
    }
  };

  const runJanitorScan = async () => {
    setMission('Fehleranalyse');
    const jobId = canonicalAgentJob.jobId;
    if (!agentConfig.ready || !jobId) {
      blockClientBoundary(
        'janitor-requires-repo',
        'Für den Janitor zuerst ein Repository als Sovereign-Agent-Job laden.',
      );
      return;
    }
    const command = createSovereignEngineCommand(
      engineState.sessionId,
      'RUN_JANITOR',
      {
        jobId,
        input: {
          mode: 'scan',
          family: 'Runtime-Wahrheit, Zustandswidersprüche, sichere Repo-Automation',
          maxFindings: 10,
          maxFiles: 200,
        },
      },
    );
    try {
      const event = await runEngineCommand(command);
      const response = sovereignEngineOperationResultFromEvent(event, 'JANITOR');
      if (!response) throw new Error('Janitor-Readback hat den typisierten Boundary-Vertrag nicht erfüllt.');
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
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Janitor-Scan fehlgeschlagen.';
      blockClientBoundary('janitor-scan', message);
    }
  };

  const canonicalRuntimeRunning = ['queued', 'provisioning', 'running', 'validating'].includes(
    canonicalAgentJob.status,
  );
  const engineStartBusy = hasSovereignEnginePendingCommand(engineState, [
    'START_REPOSITORY_EXECUTION',
    'START_TOOLCHAIN_JOB',
  ]);
  const agentIsRunning = canonicalRuntimeRunning || engineStartBusy;
  const repoReady = Boolean(
    canonicalAgentJob.repoUrl
    && canonicalAgentJob.workspaceId
    && ['running', 'waiting-for-user', 'validating', 'completed'].includes(canonicalAgentJob.status),
  );
  const repoBusy = engineStartBusy
    || canonicalAgentJob.status === 'queued'
    || canonicalAgentJob.status === 'provisioning';
  const isPublishing = canonicalAgentJob.status === 'validating'
    || hasSovereignEnginePendingCommand(engineState, ['PREPARE_DRAFT_PR', 'CREATE_DRAFT_PR']);
  const runtimeSummary = summarizeSovereignAgentJob(agentJob);

  const publishDraftPr = async (
    input?: SovereignDraftPrPublishInput,
  ) => {
    let jobId = canonicalAgentJob.jobId;
    let repoUrl = canonicalAgentJob.repoUrl;

    if (!jobId && input?.changes && input.changes.length > 0) {
      try {
        const evidenceText = await evidenceWithReusableMemory(input.mission);
        const startCommand = createSovereignEngineCommand(
          engineState.sessionId,
          'START_TOOLCHAIN_JOB',
          {
            input: {
              repoUrl: input.repoUrl,
              branch: input.branch,
              expectedHeadSha: input.expectedHeadSha,
              mission: input.mission,
              evidenceText,
              provisionWorkspace: true,
              cloneRepo: true,
              stagedFiles: input.changes,
              githubAccessToken: input.githubAccessToken,
            },
          },
        );
        const startEvent = await runEngineCommand(startCommand);
        const snapshot = sovereignEngineJobFromEvent(startEvent);
        if (!snapshot?.jobId || !snapshot.repoUrl) {
          throw new Error('Staged Agent Start lieferte keinen kanonischen Job-Readback.');
        }
        jobId = snapshot.jobId;
        repoUrl = snapshot.repoUrl;
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Agent Runtime Start (Staged) fehlgeschlagen.';
        blockClientBoundary('agent-start-staged', message);
        return;
      }
    }

    if (!repoUrl || !jobId) {
      const message = 'Draft PR benötigt zuerst einen belegten Sovereign-Agent-Job mit Repository.';
      blockClientBoundary('draft-pr-requires-job', message);
      throw new Error(message);
    }

    try {
      setPatternLearningEvidence(undefined);
      const prepareCommand = createSovereignEngineCommand(
        engineState.sessionId,
        'PREPARE_DRAFT_PR',
        { jobId },
      );
      const prepareEvent = await runEngineCommand(prepareCommand);
      const preparation = sovereignEngineOperationResultFromEvent(
        prepareEvent,
        'DRAFT_PR_PREPARATION',
      );
      if (!preparation) {
        throw new Error('Draft-PR-Vorbereitung lieferte keinen typisierten Runtime-Readback.');
      }
      setPatternLearningEvidence(preparation.learningEvidence);
      if (!preparation.ok || !preparation.draftPrPreparation.allowed) {
        throw new Error(
          preparation.draftPrPreparation.blockers.join('; ')
          || preparation.draftPrPreparation.summary
          || 'Draft-PR-Vorbereitung wurde durch die Runtime blockiert.',
        );
      }

      const createCommand = createSovereignEngineCommand(
        engineState.sessionId,
        'CREATE_DRAFT_PR',
        { jobId, githubAccessToken: input?.githubAccessToken },
      );
      const createEvent = await runEngineCommand(createCommand);
      const creation = sovereignEngineOperationResultFromEvent(createEvent, 'DRAFT_PR_CREATE');
      if (!creation?.ok || !creation.draftPrCreate.allowed || !creation.draftPrCreate.prUrl) {
        throw new Error(
          creation?.draftPrCreate.blocker
          || creation?.draftPrCreate.summary
          || 'GitHub hat keinen belegten Draft PR bestätigt.',
        );
      }

      const readbackCommand = createSovereignEngineCommand(
        engineState.sessionId,
        'READ_JOB',
        { jobId },
      );
      const readbackEvent = await runEngineCommand(readbackCommand);
      const snapshot = sovereignEngineJobFromEvent(readbackEvent);
      if (!snapshot || snapshot.draftPrUrl !== creation.draftPrCreate.prUrl) {
        throw new Error('Persistierter Job-Readback bestätigt die erstellte Draft-PR-URL noch nicht.');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Draft-PR-Übergabe fehlgeschlagen.';
      blockClientBoundary('draft-pr-blocked', message);
    }
  };

  const adoptRescueJob = async (jobId: string) => {
    const command = createSovereignEngineCommand(
      engineState.sessionId,
      'READ_JOB',
      { jobId, adopt: true },
    );
    try {
      const event = await runEngineCommand(command);
      if (!sovereignEngineJobFromEvent(event)) {
        throw new Error('Rescue-Job lieferte keinen kanonischen Job-Readback.');
      }
      setMission('Sovereign Rescue');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Rescue-Job konnte nicht übernommen werden.';
      blockClientBoundary('rescue-adopt', message);
    }
  };

  return (
    <LlmAdapterProvider>
      <main
        data-testid="sovereign-monitor-app"
        data-layout="monitor-first-live-workspace"
        aria-label="Sovereign Workspace Monitor"
        data-legacy-backend-image-marker="DevChat"
        style={MONITOR_FIRST_STYLE}
      >
        <BuilderContainer
          mission={mission}
          repoReady={repoReady}
          repoReason={repoReady ? `Runtime-Repository: ${canonicalAgentJob.repoUrl}` : 'Noch kein Repository an den Workspace-Monitor gebunden.'}
          repoBusy={repoBusy}
          runtimeBusy={agentIsRunning}
          isPublishing={isPublishing}
          sovereignSummary={runtimeSummary}
          sovereignPreview={janitorPreview}
          onMissionChange={setMission}
          onGenerateIdeas={() => setMission('Ideen/Build')}
          onGenerateErrorWorkflow={() => { void runJanitorScan(); }}
          onPublishDraftPr={publishDraftPr}
          agentReady={agentConfig.ready}
          agentConfig={agentConfig}
          agentJob={agentJob}
          agentProjections={liveProjections}
          agentEvidenceAnchors={liveEvidenceAnchors}
          desktopFrame={desktopFrame}
          patternLearningEvidence={patternLearningEvidence}
          agentJobStatus={agentIsRunning
            ? 'Sovereign Agent Auftrag läuft'
            : engineState.clientNotice?.message || agentJob.lastError}
          agentIsRunning={agentIsRunning}
          onStartAgent={startMonitorTask}
          onCancelAgent={cancelMonitorTask}
        />
        {!rescueOpen && (
          ['blocked', 'failed'].includes(canonicalAgentJob.status)
          || Boolean(engineState.clientNotice)
        ) && (
          <button
            type="button"
            onClick={() => setRescueOpen(true)}
            aria-label="Sovereign Rescue öffnen"
            style={{
              position: 'fixed',
              right: 14,
              bottom: 14,
              zIndex: 70,
              minHeight: 48,
              borderRadius: 24,
              border: '1px solid #38bdf8',
              background: '#0c4a6e',
              color: '#f0f9ff',
              padding: '10px 16px',
              fontWeight: 800,
              boxShadow: '0 12px 30px rgba(0,0,0,.35)',
            }}
          >
            Rescue
          </button>
        )}
        <RescuePanel
          open={rescueOpen}
          apiBaseUrl={agentConfig.agentApiUrl}
          currentJobId={canonicalAgentJob.jobId}
          draftPrUrl={canonicalAgentJob.draftPrUrl}
          onClose={() => setRescueOpen(false)}
          onJobReady={adoptRescueJob}
          onPublishDraftPr={() => publishDraftPr()}
        />
      </main>
    </LlmAdapterProvider>
  );
}

export default function App() {
  const observatoryMode = typeof window !== 'undefined'
    && (window.location.pathname === '/observatory'
      || window.location.pathname === '/evidence-observatory'
      || new URLSearchParams(window.location.search).get('observatory') === '1');
  return observatoryMode ? <EvidenceObservatoryAtlas /> : <SovereignMonitorApp />;
}
