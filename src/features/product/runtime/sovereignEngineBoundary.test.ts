import { describe, expect, it, vi } from 'vitest';
import type {
  SovereignAgentJobSnapshot,
  SovereignLiveProjection,
  SovereignWorkspaceEvidenceAnchor,
} from './sovereignAgentRuntime';
import {
  createInitialSovereignEngineState,
  createSovereignClientBoundaryBlockedEvent,
  createSovereignEngineCommand,
  createSovereignEngineCommandAcceptedEvent,
  createSovereignEngineCommandFailedEvent,
  executeSovereignEngineCommand,
  selectSovereignEngineJobProjection,
  sovereignEngineJobFromEvent,
  sovereignEngineReducer,
  type SovereignEngineEventV1,
  type SovereignEngineTransport,
} from './sovereignEngineBoundary';

const SESSION = 'engine-session-test';
const JOB_ID = 'job-1';

function job(overrides: Partial<SovereignAgentJobSnapshot> = {}): SovereignAgentJobSnapshot {
  return {
    jobId: JOB_ID,
    workspaceId: 'workspace-1',
    status: 'running',
    repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
    branch: 'main',
    changedFiles: [],
    events: [],
    ...overrides,
  };
}

function projection(overrides: Partial<SovereignLiveProjection> = {}): SovereignLiveProjection {
  return {
    projectionId: 'visual-1',
    eventId: 'visual-1',
    sessionId: 'livews-1234567890abcdef12345678',
    sessionBindingHash: 'a'.repeat(64),
    attemptId: 'attempt-1',
    jobId: JOB_ID,
    workspaceId: 'workspace-1',
    actionId: 'action-1',
    sourceKind: 'PROCESS',
    projectionKind: 'TERMINAL',
    projectionState: 'REQUESTED',
    sourceReceiptRef: 'b'.repeat(64),
    sourceIdentityHash: 'c'.repeat(64),
    payload: { chunk: '1 test failed', exitCode: 1 },
    projectionHash: 'd'.repeat(64),
    authoritative: false,
    claim: 'OBSERVED',
    ...overrides,
  };
}

function evidenceAnchor(
  overrides: Partial<SovereignWorkspaceEvidenceAnchor> = {},
): SovereignWorkspaceEvidenceAnchor {
  return {
    anchorId: `evidence-${'e'.repeat(24)}`,
    jobId: JOB_ID,
    workspaceId: 'workspace-1',
    claimKind: 'TEST_EXECUTION_RECEIPT_MATCH',
    verdict: 'VERIFIED',
    sourceVerdict: 'VERIFIED',
    sessionBindingHash: 'f'.repeat(64),
    runId: 'run-1',
    taskId: 'task-1',
    attemptId: 'attempt-1',
    actionId: 'action-1',
    scope: 'tool=test;effect=read',
    sourceKind: 'AGENT_RUN_RECEIPT',
    sourceRefs: ['a'.repeat(64)],
    repositoryRevision: 'b'.repeat(40),
    observedAt: '2026-08-23T03:30:00Z',
    freshnessReasons: [],
    evidenceHash: 'c'.repeat(64),
    authoritative: false,
    ...overrides,
  };
}

function transport(overrides: Partial<SovereignEngineTransport> = {}): SovereignEngineTransport {
  return {
    listJobs: vi.fn(async () => []),
    getJob: vi.fn(async () => job()),
    startRepositoryExecution: vi.fn(async () => job()),
    startToolchainJob: vi.fn(async () => job()),
    cancelJob: vi.fn(async () => job({ status: 'blocked', lastError: 'Cancelled by user.' })),
    getProjections: vi.fn(async () => [projection()]),
    getEvidenceAnchors: vi.fn(async () => [evidenceAnchor()]),
    runJanitor: vi.fn(async () => ({
      ok: true,
      jobId: JOB_ID,
      tool: { status: 'done', changedFiles: [], metadata: {} },
    })),
    prepareDraftPr: vi.fn(async () => ({
      ok: true,
      jobId: JOB_ID,
      draftPrPreparation: { allowed: true, decision: 'ready', blockers: [] },
    })),
    createDraftPr: vi.fn(async () => {
      const sha = 'e'.repeat(40);
      return {
        ok: true,
        jobId: JOB_ID,
        draftPrCreate: {
          allowed: true,
          status: 'created',
          prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1',
          headSha: sha,
          publishedHeadSha: sha,
          readbackHeadSha: sha,
          prNumber: 1,
          draftVerified: true,
          prStateVerified: 'open',
          headBranch: 'sovereign/test',
          baseBranch: 'main',
          readbackVerified: true,
          checksReadbackVerified: true,
          ciState: 'pending',
          checkRunCount: 1,
          checksPendingCount: 1,
          checksSuccessCount: 0,
          checksFailureCount: 0,
          statusContextCount: 0,
        },
      };
    }),
    ...overrides,
  };
}

describe('Sovereign Typed Engine Boundary', () => {
  it('changes canonical product state only after the matching typed command was accepted', async () => {
    const command = createSovereignEngineCommand(
      SESSION,
      'START_REPOSITORY_EXECUTION',
      {
        input: {
          repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
          branch: 'main',
          mission: 'Integrate the typed boundary.',
        },
      },
      { commandId: 'command-start-1', correlationId: 'correlation-1', issuedAt: 10 },
    );
    const resultEvent = await executeSovereignEngineCommand(command, transport(), () => 20);
    const initial = createInitialSovereignEngineState({ sessionId: SESSION });

    const rejectedWithoutCommand = sovereignEngineReducer(initial, resultEvent);
    expect(rejectedWithoutCommand).toBe(initial);
    expect(rejectedWithoutCommand.canonicalJob.status).toBe('idle');

    const withCommand = sovereignEngineReducer(initial, createSovereignEngineCommandAcceptedEvent(command, () => 15));
    const accepted = sovereignEngineReducer(withCommand, resultEvent);
    expect(accepted.canonicalJob).toMatchObject({ jobId: JOB_ID, status: 'running' });
    expect(accepted.pendingCommands).toEqual({});
  });

  it('rejects arbitrary assistant/provider/tool text as an engine state transition', () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION });
    const forged = {
      schemaVersion: 'sovereign.engine-event.v1',
      eventId: 'event-forged-1',
      eventType: 'ASSISTANT_TEXT',
      source: 'SOVEREIGN_BACKEND',
      sessionId: SESSION,
      causationId: 'provider-response-1',
      correlationId: 'correlation-1',
      occurredAt: 10,
      payload: { text: 'Alles fertig und deployed.', status: 'completed' },
    } as unknown as SovereignEngineEventV1;

    const next = sovereignEngineReducer(initial, forged);
    expect(next).toBe(initial);
    expect(next.canonicalJob.status).toBe('idle');
  });

  it('rejects unknown schemas and foreign engine sessions', () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION });
    const local = createSovereignClientBoundaryBlockedEvent(SESSION, 'start', 'Repository URL fehlt.', {
      occurredAt: 10,
      correlationId: 'correlation-1',
    });
    const wrongSchema = { ...local, schemaVersion: 'sovereign.engine-event.v2' } as unknown as SovereignEngineEventV1;
    const wrongSession = { ...local, eventId: 'event-foreign-1', sessionId: 'engine-session-other' };

    expect(sovereignEngineReducer(initial, wrongSchema)).toBe(initial);
    expect(sovereignEngineReducer(initial, wrongSession)).toBe(initial);
  });

  it('fails closed without throwing for a known event type with a malformed payload', () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION });
    const malformed = {
      schemaVersion: 'sovereign.engine-event.v1',
      eventId: 'event-malformed-1',
      eventType: 'CANONICAL_JOB_SNAPSHOT_ACCEPTED',
      source: 'SOVEREIGN_BACKEND',
      sessionId: SESSION,
      causationId: 'command-read-malformed',
      correlationId: 'correlation-malformed',
      occurredAt: 10,
      payload: null,
    } as unknown as SovereignEngineEventV1;

    let next = initial;
    expect(() => {
      next = sovereignEngineReducer(initial, malformed);
    }).not.toThrow();
    expect(next).toBe(initial);
  });

  it('rejects event replay without applying the transition twice', () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION });
    const event = createSovereignClientBoundaryBlockedEvent(SESSION, 'start', 'Repository URL fehlt.', {
      occurredAt: 10,
      correlationId: 'correlation-1',
    });
    const once = sovereignEngineReducer(initial, event);
    const replay = sovereignEngineReducer(once, event);

    expect(replay).toBe(once);
    expect(replay.acceptedEventIds).toHaveLength(1);
  });

  it('does not let an older canonical readback overwrite a newer job transition', async () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION, job: job() });
    const olderRead = createSovereignEngineCommand(
      SESSION,
      'READ_JOB',
      { jobId: JOB_ID },
      { commandId: 'command-read-older', correlationId: 'correlation-read-older', issuedAt: 10 },
    );
    const newerCancel = createSovereignEngineCommand(
      SESSION,
      'CANCEL_JOB',
      { jobId: JOB_ID },
      { commandId: 'command-cancel-newer', correlationId: 'correlation-cancel-newer', issuedAt: 11 },
    );

    const withOlder = sovereignEngineReducer(
      initial,
      createSovereignEngineCommandAcceptedEvent(olderRead, () => 12),
    );
    const withBoth = sovereignEngineReducer(
      withOlder,
      createSovereignEngineCommandAcceptedEvent(newerCancel, () => 13),
    );
    const newerEvent = await executeSovereignEngineCommand(newerCancel, transport(), () => 14);
    const afterCancel = sovereignEngineReducer(withBoth, newerEvent);
    expect(afterCancel.canonicalJob.status).toBe('blocked');

    const olderEvent = await executeSovereignEngineCommand(
      olderRead,
      transport({ getJob: vi.fn(async () => job({ status: 'running' })) }),
      () => 15,
    );
    const afterLateRead = sovereignEngineReducer(afterCancel, olderEvent);

    expect(afterLateRead.canonicalJob.status).toBe('blocked');
    expect(afterLateRead.pendingCommands).toEqual({});
    expect(afterLateRead.canonicalJobSequence).toBe(afterCancel.canonicalJobSequence);
  });

  it('keeps visual projections observation-only and cannot change job status', async () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION, job: job({ status: 'failed' }) });
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-1', correlationId: 'correlation-1', issuedAt: 10 },
    );
    const started = sovereignEngineReducer(initial, createSovereignEngineCommandAcceptedEvent(command, () => 11));
    const event = await executeSovereignEngineCommand(command, transport(), () => 12);
    const next = sovereignEngineReducer(started, event);

    expect(next.projections).toHaveLength(1);
    expect(next.canonicalJob.status).toBe('failed');
    expect(next.projections[0]).toMatchObject({ authoritative: false, claim: 'OBSERVED' });
  });

  it('rejects a projection from another job before creating a canonical backend event', async () => {
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-foreign-job', correlationId: 'correlation-foreign-job', issuedAt: 10 },
    );

    await expect(executeSovereignEngineCommand(
      command,
      transport({ getProjections: vi.fn(async () => [projection({ jobId: 'job-other' })]) }),
      () => 12,
    )).rejects.toThrow('projection outside the requested job/workspace/session binding');
  });

  it('rejects mixed projection sessions or attempts before creating a canonical backend event', async () => {
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-foreign-attempt', correlationId: 'correlation-foreign-attempt', issuedAt: 10 },
    );

    await expect(executeSovereignEngineCommand(
      command,
      transport({
        getProjections: vi.fn(async () => [
          projection(),
          projection({
            projectionId: 'visual-2',
            eventId: 'visual-2',
            sessionBindingHash: '9'.repeat(64),
            attemptId: 'attempt-2',
          }),
        ]),
      }),
      () => 12,
    )).rejects.toThrow('projection outside the requested job/workspace/session binding');
  });

  it('rejects a projection event whose workspace differs from the canonical job', async () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION, job: job() });
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-foreign-workspace', correlationId: 'correlation-foreign-workspace', issuedAt: 10 },
    );
    const started = sovereignEngineReducer(initial, createSovereignEngineCommandAcceptedEvent(command, () => 11));
    const event = await executeSovereignEngineCommand(
      command,
      transport({ getProjections: vi.fn(async () => [projection({ workspaceId: 'workspace-other' })]) }),
      () => 12,
    );

    const next = sovereignEngineReducer(started, event);

    expect(next.projections).toEqual([]);
    expect(next.pendingCommands[command.commandId]).toBeDefined();
  });

  it('rejects a projection event whose attempt differs from its accepted payload', async () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION, job: job() });
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-event-attempt', correlationId: 'correlation-event-attempt', issuedAt: 10 },
    );
    const started = sovereignEngineReducer(initial, createSovereignEngineCommandAcceptedEvent(command, () => 11));
    const event = await executeSovereignEngineCommand(command, transport(), () => 12);
    const forged = {
      ...event,
      eventId: 'event-projections-foreign-attempt',
      attemptId: 'attempt-other',
    };

    const next = sovereignEngineReducer(started, forged);

    expect(next.projections).toEqual([]);
    expect(next.pendingCommands[command.commandId]).toBeDefined();
  });

  it('admits evidence anchors only through a matching accepted typed command and canonical backend event', async () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION, job: job() });
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-1', correlationId: 'correlation-evidence-1', issuedAt: 10 },
    );
    const event = await executeSovereignEngineCommand(command, transport(), () => 12);

    expect(sovereignEngineReducer(initial, event)).toBe(initial);

    const started = sovereignEngineReducer(
      initial,
      createSovereignEngineCommandAcceptedEvent(command, () => 11),
    );
    const foreign = { ...event, eventId: 'event-evidence-foreign', jobId: 'job-other' };
    expect(sovereignEngineReducer(started, foreign)).toBe(started);

    const accepted = sovereignEngineReducer(started, event);
    expect(accepted.evidenceAnchors).toEqual([evidenceAnchor()]);
    expect(accepted.canonicalJob).toMatchObject({ jobId: JOB_ID, status: 'running' });
    expect(accepted.pendingCommands).toEqual({});
  });

  it('rejects evidence from another job before creating a canonical backend event', async () => {
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-foreign-job', correlationId: 'correlation-evidence-foreign-job', issuedAt: 10 },
    );

    await expect(executeSovereignEngineCommand(
      command,
      transport({ getEvidenceAnchors: vi.fn(async () => [evidenceAnchor({ jobId: 'job-other' })]) }),
      () => 12,
    )).rejects.toThrow('evidence outside the requested job/workspace/session binding');
  });

  it('rejects an evidence event whose workspace differs from the canonical job', async () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION, job: job() });
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-foreign-workspace', correlationId: 'correlation-evidence-foreign-workspace', issuedAt: 10 },
    );
    const started = sovereignEngineReducer(initial, createSovereignEngineCommandAcceptedEvent(command, () => 11));
    const event = await executeSovereignEngineCommand(
      command,
      transport({ getEvidenceAnchors: vi.fn(async () => [evidenceAnchor({ workspaceId: 'workspace-other' })]) }),
      () => 12,
    );

    const next = sovereignEngineReducer(started, event);

    expect(next.evidenceAnchors).toEqual([]);
    expect(next.pendingCommands[command.commandId]).toBeDefined();
  });

  it('clears prior monitor evidence when a projection or evidence read fails', () => {
    const initial = {
      ...createInitialSovereignEngineState({ sessionId: SESSION, job: job() }),
      projections: [projection()],
      evidenceAnchors: [evidenceAnchor()],
    };
    const projectionCommand = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-failed', correlationId: 'correlation-projections-failed', issuedAt: 10 },
    );
    const projectionStarted = sovereignEngineReducer(
      initial,
      createSovereignEngineCommandAcceptedEvent(projectionCommand, () => 11),
    );
    const afterProjectionFailure = sovereignEngineReducer(
      projectionStarted,
      createSovereignEngineCommandFailedEvent(projectionCommand, new Error('projection read failed'), () => 12),
    );

    expect(afterProjectionFailure.projections).toEqual([]);
    expect(afterProjectionFailure.evidenceAnchors).toEqual([evidenceAnchor()]);

    const evidenceCommand = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-failed', correlationId: 'correlation-evidence-failed', issuedAt: 13 },
    );
    const evidenceStarted = sovereignEngineReducer(
      afterProjectionFailure,
      createSovereignEngineCommandAcceptedEvent(evidenceCommand, () => 14),
    );
    const afterEvidenceFailure = sovereignEngineReducer(
      evidenceStarted,
      createSovereignEngineCommandFailedEvent(evidenceCommand, new Error('evidence read failed'), () => 15),
    );

    expect(afterEvidenceFailure.projections).toEqual([]);
    expect(afterEvidenceFailure.evidenceAnchors).toEqual([]);
    expect(afterEvidenceFailure.pendingCommands).toEqual({});
  });

  it('does not let a late read failure erase newer monitor evidence', async () => {
    const projectionInitial = createInitialSovereignEngineState({ sessionId: SESSION, job: job() });
    const olderProjectionRead = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-older-failure', correlationId: 'correlation-projections-older-failure', issuedAt: 10 },
    );
    const newerProjectionRead = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-newer-success', correlationId: 'correlation-projections-newer-success', issuedAt: 11 },
    );
    const withOlderProjection = sovereignEngineReducer(
      projectionInitial,
      createSovereignEngineCommandAcceptedEvent(olderProjectionRead, () => 12),
    );
    const withBothProjections = sovereignEngineReducer(
      withOlderProjection,
      createSovereignEngineCommandAcceptedEvent(newerProjectionRead, () => 13),
    );
    const newerProjectionEvent = await executeSovereignEngineCommand(
      newerProjectionRead,
      transport({
        getProjections: vi.fn(async () => [projection({ attemptId: 'attempt-newer' })]),
      }),
      () => 14,
    );
    const afterNewerProjection = sovereignEngineReducer(withBothProjections, newerProjectionEvent);
    const afterLateProjectionFailure = sovereignEngineReducer(
      afterNewerProjection,
      createSovereignEngineCommandFailedEvent(olderProjectionRead, new Error('late projection failure'), () => 15),
    );

    expect(afterLateProjectionFailure.projections).toMatchObject([{ attemptId: 'attempt-newer' }]);
    expect(afterLateProjectionFailure.pendingCommands).toEqual({});

    const evidenceInitial = createInitialSovereignEngineState({ sessionId: SESSION, job: job() });
    const olderEvidenceRead = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-older-failure', correlationId: 'correlation-evidence-older-failure', issuedAt: 20 },
    );
    const newerEvidenceRead = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-newer-success', correlationId: 'correlation-evidence-newer-success', issuedAt: 21 },
    );
    const withOlderEvidence = sovereignEngineReducer(
      evidenceInitial,
      createSovereignEngineCommandAcceptedEvent(olderEvidenceRead, () => 22),
    );
    const withBothEvidence = sovereignEngineReducer(
      withOlderEvidence,
      createSovereignEngineCommandAcceptedEvent(newerEvidenceRead, () => 23),
    );
    const newerEvidenceEvent = await executeSovereignEngineCommand(
      newerEvidenceRead,
      transport({
        getEvidenceAnchors: vi.fn(async () => [evidenceAnchor({ attemptId: 'attempt-newer' })]),
      }),
      () => 24,
    );
    const afterNewerEvidence = sovereignEngineReducer(withBothEvidence, newerEvidenceEvent);
    const afterLateEvidenceFailure = sovereignEngineReducer(
      afterNewerEvidence,
      createSovereignEngineCommandFailedEvent(olderEvidenceRead, new Error('late evidence failure'), () => 25),
    );

    expect(afterLateEvidenceFailure.evidenceAnchors).toMatchObject([{ attemptId: 'attempt-newer' }]);
    expect(afterLateEvidenceFailure.pendingCommands).toEqual({});
  });

  it('does not let an older read success repopulate evidence after a newer read failed', async () => {
    const projectionInitial = {
      ...createInitialSovereignEngineState({ sessionId: SESSION, job: job() }),
      projections: [projection({ attemptId: 'attempt-before-failure' })],
    };
    const olderProjectionRead = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-older-success', correlationId: 'correlation-projections-older-success', issuedAt: 30 },
    );
    const newerProjectionRead = createSovereignEngineCommand(
      SESSION,
      'READ_PROJECTIONS',
      { jobId: JOB_ID },
      { commandId: 'command-projections-newer-failure', correlationId: 'correlation-projections-newer-failure', issuedAt: 31 },
    );
    const withOlderProjection = sovereignEngineReducer(
      projectionInitial,
      createSovereignEngineCommandAcceptedEvent(olderProjectionRead, () => 32),
    );
    const withBothProjections = sovereignEngineReducer(
      withOlderProjection,
      createSovereignEngineCommandAcceptedEvent(newerProjectionRead, () => 33),
    );
    const afterNewerProjectionFailure = sovereignEngineReducer(
      withBothProjections,
      createSovereignEngineCommandFailedEvent(newerProjectionRead, new Error('newer projection failure'), () => 34),
    );
    const olderProjectionEvent = await executeSovereignEngineCommand(
      olderProjectionRead,
      transport({
        getProjections: vi.fn(async () => [projection({ attemptId: 'attempt-older' })]),
      }),
      () => 35,
    );
    const afterLateProjectionSuccess = sovereignEngineReducer(
      afterNewerProjectionFailure,
      olderProjectionEvent,
    );

    expect(afterNewerProjectionFailure.projections).toEqual([]);
    expect(afterLateProjectionSuccess.projections).toEqual([]);
    expect(afterLateProjectionSuccess.pendingCommands).toEqual({});

    const evidenceInitial = {
      ...createInitialSovereignEngineState({ sessionId: SESSION, job: job() }),
      evidenceAnchors: [evidenceAnchor({ attemptId: 'attempt-before-failure' })],
    };
    const olderEvidenceRead = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-older-success', correlationId: 'correlation-evidence-older-success', issuedAt: 40 },
    );
    const newerEvidenceRead = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-newer-failure', correlationId: 'correlation-evidence-newer-failure', issuedAt: 41 },
    );
    const withOlderEvidence = sovereignEngineReducer(
      evidenceInitial,
      createSovereignEngineCommandAcceptedEvent(olderEvidenceRead, () => 42),
    );
    const withBothEvidence = sovereignEngineReducer(
      withOlderEvidence,
      createSovereignEngineCommandAcceptedEvent(newerEvidenceRead, () => 43),
    );
    const afterNewerEvidenceFailure = sovereignEngineReducer(
      withBothEvidence,
      createSovereignEngineCommandFailedEvent(newerEvidenceRead, new Error('newer evidence failure'), () => 44),
    );
    const olderEvidenceEvent = await executeSovereignEngineCommand(
      olderEvidenceRead,
      transport({
        getEvidenceAnchors: vi.fn(async () => [evidenceAnchor({ attemptId: 'attempt-older' })]),
      }),
      () => 45,
    );
    const afterLateEvidenceSuccess = sovereignEngineReducer(
      afterNewerEvidenceFailure,
      olderEvidenceEvent,
    );

    expect(afterNewerEvidenceFailure.evidenceAnchors).toEqual([]);
    expect(afterLateEvidenceSuccess.evidenceAnchors).toEqual([]);
    expect(afterLateEvidenceSuccess.pendingCommands).toEqual({});
  });

  it('rejects invalid evidence anchors before they can enter an accepted engine event', async () => {
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_EVIDENCE_ANCHORS',
      { jobId: JOB_ID },
      { commandId: 'command-evidence-invalid', correlationId: 'correlation-evidence-invalid', issuedAt: 10 },
    );

    await expect(executeSovereignEngineCommand(
      command,
      transport({
        getEvidenceAnchors: vi.fn(async () => [evidenceAnchor({ sourceKind: 'FRAME_OBSERVATION', verdict: 'VERIFIED' })]),
      }),
      () => 12,
    )).rejects.toThrow('invalid evidence anchor contract');
  });

  it('keeps local blockers outside canonical runtime truth', () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION });
    const next = sovereignEngineReducer(
      initial,
      createSovereignClientBoundaryBlockedEvent(SESSION, 'start', 'Repository URL fehlt.', {
        occurredAt: 10,
        correlationId: 'correlation-1',
      }),
    );

    expect(next.canonicalJob.status).toBe('idle');
    expect(selectSovereignEngineJobProjection(next)).toMatchObject({
      status: 'blocked',
      lastError: 'Repository URL fehlt.',
    });
  });

  it('rejects a stale or foreign job snapshot before it can become an engine event', async () => {
    const initial = createInitialSovereignEngineState({ sessionId: SESSION, job: job() });
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_JOB',
      { jobId: JOB_ID },
      { commandId: 'command-read-1', correlationId: 'correlation-1', issuedAt: 10 },
    );
    const started = sovereignEngineReducer(initial, createSovereignEngineCommandAcceptedEvent(command, () => 11));
    const execution = executeSovereignEngineCommand(
      command,
      transport({ getJob: vi.fn(async () => job({ jobId: 'job-other' })) }),
      () => 12,
    );

    await expect(execution).rejects.toThrow('another identity');
    const failed = sovereignEngineReducer(
      started,
      createSovereignEngineCommandFailedEvent(command, new Error('foreign identity'), () => 13),
    );
    expect(failed.canonicalJob.jobId).toBe(JOB_ID);
    expect(failed.pendingCommands).toEqual({});
  });

  it('does not persist command secrets in accepted control events', () => {
    const sensitiveValue = 'sensitive-test-value-that-must-not-persist';
    const command = createSovereignEngineCommand(
      SESSION,
      'CREATE_DRAFT_PR',
      { jobId: JOB_ID, githubAccessToken: sensitiveValue },
      { commandId: 'command-pr-1', correlationId: 'correlation-1', issuedAt: 10 },
    );

    const accepted = createSovereignEngineCommandAcceptedEvent(command, () => 11);
    expect(JSON.stringify(accepted)).not.toContain(sensitiveValue);
    expect(accepted.payload).toMatchObject({ commandType: 'CREATE_DRAFT_PR', expectedJobId: JOB_ID });
  });

  it('strips repository URL userinfo before a pending command can enter product state', () => {
    const embeddedValue = 'embedded-sensitive-value';
    const command = createSovereignEngineCommand(
      SESSION,
      'START_REPOSITORY_EXECUTION',
      {
        input: {
          repoUrl: `https://${embeddedValue}@example.com/OuroborosCollective/Sovereign-Studio-ato`,
          branch: 'main',
          mission: 'Integrate the typed boundary.',
        },
      },
      { commandId: 'command-start-secret-1', correlationId: 'correlation-secret-1', issuedAt: 10 },
    );

    const accepted = createSovereignEngineCommandAcceptedEvent(command, () => 11);
    expect(JSON.stringify(accepted)).not.toContain(embeddedValue);
    expect(accepted.payload).toMatchObject({
      commandType: 'START_REPOSITORY_EXECUTION',
      repoUrl: 'https://example.com/OuroborosCollective/Sovereign-Studio-ato',
    });
  });

  it('preserves command causation and correlation through the backend event', async () => {
    const command = createSovereignEngineCommand(
      SESSION,
      'READ_JOB',
      { jobId: JOB_ID, adopt: true },
      { commandId: 'command-read-2', correlationId: 'correlation-2', issuedAt: 10 },
    );
    const event = await executeSovereignEngineCommand(command, transport(), () => 20);

    expect(event).toMatchObject({
      sessionId: SESSION,
      causationId: 'command-read-2',
      correlationId: 'correlation-2',
      eventType: 'CANONICAL_JOB_SNAPSHOT_ACCEPTED',
    });
    expect(sovereignEngineJobFromEvent(event)).toMatchObject({ jobId: JOB_ID });
  });
});
