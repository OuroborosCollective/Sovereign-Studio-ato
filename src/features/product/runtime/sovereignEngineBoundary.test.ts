import { describe, expect, it, vi } from 'vitest';
import type {
  SovereignAgentJobSnapshot,
  SovereignLiveProjection,
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

function projection(): SovereignLiveProjection {
  return {
    projectionId: 'visual-1',
    eventId: 'visual-1',
    sessionId: 'livews-1234567890abcdef12345678',
    sessionBindingHash: 'a'.repeat(64),
    attemptId: 'attempt-1',
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
