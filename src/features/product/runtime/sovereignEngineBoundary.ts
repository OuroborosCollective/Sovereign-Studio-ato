import type {
  SovereignDraftPrCreateResponse,
  SovereignDraftPrPreparationResponse,
  SovereignJanitorInput,
  SovereignJanitorToolResponse,
  SovereignRepositoryExecutionInput,
  SovereignToolchainStartJobInput,
} from './sovereignAgentClient';
import {
  createSovereignAgentIdleSnapshot,
  maskSovereignAgentSensitiveText,
  type SovereignAgentJobSnapshot,
  type SovereignLiveProjection,
  type SovereignWorkspaceEvidenceAnchor,
} from './sovereignAgentRuntime';

/**
 * Typed product boundary in front of the canonical Sovereign backend runtime.
 *
 * The backend job/readback contracts remain the truth owner. This module is a
 * strict adapter and reducer: React may request typed commands and may project
 * accepted typed events, but raw provider text, assistant text, tool output or
 * arbitrary JSON can never mutate canonical product state.
 *
 * Deliberately out of scope for this V1 foundation: a universal effect gateway,
 * permission redesign, deployment orchestration and Live Monitor rendering.
 */
export const SOVEREIGN_ENGINE_COMMAND_SCHEMA_VERSION = 'sovereign.engine-command.v1' as const;
export const SOVEREIGN_ENGINE_EVENT_SCHEMA_VERSION = 'sovereign.engine-event.v1' as const;

export interface SovereignEngineCommandPayloads {
  RESTORE_LATEST_JOB: Record<string, never>;
  READ_JOB: { jobId: string; adopt?: boolean };
  START_REPOSITORY_EXECUTION: { input: SovereignRepositoryExecutionInput };
  START_TOOLCHAIN_JOB: { input: SovereignToolchainStartJobInput };
  CANCEL_JOB: { jobId: string };
  READ_PROJECTIONS: { jobId: string };
  READ_EVIDENCE_ANCHORS: { jobId: string };
  RUN_JANITOR: { jobId: string; input: SovereignJanitorInput };
  PREPARE_DRAFT_PR: { jobId: string; headBranch?: string };
  CREATE_DRAFT_PR: { jobId: string; githubAccessToken?: string };
}

export type SovereignEngineCommandType = keyof SovereignEngineCommandPayloads;

type SovereignEngineCommandFor<T extends SovereignEngineCommandType> = {
  [K in T]: {
    schemaVersion: typeof SOVEREIGN_ENGINE_COMMAND_SCHEMA_VERSION;
    commandId: string;
    commandType: K;
    sessionId: string;
    correlationId: string;
    issuedAt: number;
    payload: SovereignEngineCommandPayloads[K];
  }
}[T];

export type SovereignEngineCommandV1 = SovereignEngineCommandFor<SovereignEngineCommandType>;

export type SovereignEngineOperationResultKind =
  | 'JANITOR'
  | 'DRAFT_PR_PREPARATION'
  | 'DRAFT_PR_CREATE';

interface SovereignEngineOperationResultByKind {
  JANITOR: SovereignJanitorToolResponse;
  DRAFT_PR_PREPARATION: SovereignDraftPrPreparationResponse;
  DRAFT_PR_CREATE: SovereignDraftPrCreateResponse;
}

type EngineEventBase<
  TType extends string,
  TSource extends 'CLIENT_CONTROL' | 'SOVEREIGN_BACKEND',
  TPayload,
> = {
  schemaVersion: typeof SOVEREIGN_ENGINE_EVENT_SCHEMA_VERSION;
  eventId: string;
  eventType: TType;
  source: TSource;
  sessionId: string;
  causationId: string;
  correlationId: string;
  occurredAt: number;
  jobId?: string;
  workspaceId?: string;
  attemptId?: string;
  payload: TPayload;
};

export type SovereignEngineEventV1 =
  | EngineEventBase<
      'ENGINE_COMMAND_ACCEPTED',
      'CLIENT_CONTROL',
      {
        commandId: string;
        commandType: SovereignEngineCommandType;
        expectedJobId?: string;
        adoptJob: boolean;
        repoUrl?: string;
        branch?: string;
      }
    >
  | EngineEventBase<
      'CANONICAL_JOB_SNAPSHOT_ACCEPTED',
      'SOVEREIGN_BACKEND',
      {
        commandId: string;
        commandType: 'RESTORE_LATEST_JOB' | 'READ_JOB' | 'START_REPOSITORY_EXECUTION' | 'START_TOOLCHAIN_JOB' | 'CANCEL_JOB';
        job: SovereignAgentJobSnapshot;
      }
    >
  | EngineEventBase<
      'CANONICAL_JOB_LIST_EMPTY',
      'SOVEREIGN_BACKEND',
      { commandId: string; commandType: 'RESTORE_LATEST_JOB' }
    >
  | EngineEventBase<
      'CANONICAL_PROJECTIONS_ACCEPTED',
      'SOVEREIGN_BACKEND',
      { commandId: string; commandType: 'READ_PROJECTIONS'; projections: SovereignLiveProjection[] }
    >
  | EngineEventBase<
      'CANONICAL_EVIDENCE_ANCHORS_ACCEPTED',
      'SOVEREIGN_BACKEND',
      {
        commandId: string;
        commandType: 'READ_EVIDENCE_ANCHORS';
        evidenceAnchors: SovereignWorkspaceEvidenceAnchor[];
      }
    >
  | EngineEventBase<
      'ENGINE_OPERATION_RESULT_ACCEPTED',
      'SOVEREIGN_BACKEND',
      {
        commandId: string;
        commandType: 'RUN_JANITOR' | 'PREPARE_DRAFT_PR' | 'CREATE_DRAFT_PR';
        resultKind: SovereignEngineOperationResultKind;
        result: SovereignEngineOperationResultByKind[SovereignEngineOperationResultKind];
      }
    >
  | EngineEventBase<
      'ENGINE_COMMAND_FAILED',
      'CLIENT_CONTROL',
      { commandId: string; commandType: SovereignEngineCommandType; message: string; userVisible: boolean }
    >
  | EngineEventBase<
      'CLIENT_BOUNDARY_BLOCKED',
      'CLIENT_CONTROL',
      { operation: string; message: string; repoUrl?: string; branch?: string }
    >;

export interface SovereignEnginePendingCommand {
  commandId: string;
  commandType: SovereignEngineCommandType;
  correlationId: string;
  startedAt: number;
  sequence: number;
  expectedJobId?: string;
  adoptJob: boolean;
  repoUrl?: string;
  branch?: string;
}

export interface SovereignEngineClientNotice {
  operation: string;
  message: string;
  correlationId: string;
  occurredAt: number;
}

export interface SovereignEngineState {
  sessionId: string;
  canonicalJob: SovereignAgentJobSnapshot;
  projections: SovereignLiveProjection[];
  evidenceAnchors: SovereignWorkspaceEvidenceAnchor[];
  pendingCommands: Readonly<Record<string, SovereignEnginePendingCommand>>;
  clientNotice?: SovereignEngineClientNotice;
  acceptedEventIds: readonly string[];
  nextCommandSequence: number;
  canonicalJobSequence: number;
  projectionSequence: number;
  evidenceAnchorSequence: number;
}

export interface SovereignEngineTransport {
  listJobs(): Promise<SovereignAgentJobSnapshot[]>;
  getJob(jobId: string): Promise<SovereignAgentJobSnapshot>;
  startRepositoryExecution(input: SovereignRepositoryExecutionInput): Promise<SovereignAgentJobSnapshot>;
  startToolchainJob(input: SovereignToolchainStartJobInput): Promise<SovereignAgentJobSnapshot>;
  cancelJob(jobId: string): Promise<SovereignAgentJobSnapshot>;
  getProjections(jobId: string): Promise<SovereignLiveProjection[]>;
  getEvidenceAnchors(jobId: string): Promise<SovereignWorkspaceEvidenceAnchor[]>;
  runJanitor(jobId: string, input?: SovereignJanitorInput): Promise<SovereignJanitorToolResponse>;
  prepareDraftPr(jobId: string, headBranch?: string): Promise<SovereignDraftPrPreparationResponse>;
  createDraftPr(jobId: string, githubAccessToken?: string): Promise<SovereignDraftPrCreateResponse>;
}

const COMMAND_TYPES = new Set<SovereignEngineCommandType>([
  'RESTORE_LATEST_JOB',
  'READ_JOB',
  'START_REPOSITORY_EXECUTION',
  'START_TOOLCHAIN_JOB',
  'CANCEL_JOB',
  'READ_PROJECTIONS',
  'READ_EVIDENCE_ANCHORS',
  'RUN_JANITOR',
  'PREPARE_DRAFT_PR',
  'CREATE_DRAFT_PR',
]);

const JOB_STATUSES = new Set([
  'idle',
  'queued',
  'provisioning',
  'running',
  'waiting-for-user',
  'validating',
  'blocked',
  'failed',
  'completed',
  'cleaned',
]);

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const REVISION = /^[a-f0-9]{40}$/;
const IMAGE_DIGEST = /^sha256:[a-f0-9]{64}$/;
const EVIDENCE_VERDICTS = new Set(['OBSERVED', 'UNVERIFIED', 'VERIFIED', 'BLOCKED', 'CONTRADICTED', 'STALE']);
const EVIDENCE_SOURCE_KINDS = new Set(['AGENT_RUN_RECEIPT', 'GITHUB_READBACK', 'PATCHMON_READBACK', 'DATABASE_READBACK', 'TARGET_READBACK', 'FRAME_OBSERVATION']);
const FORBIDDEN_EVIDENCE_TEXT = ['chain-of-thought', 'reasoning:', 'system prompt', 'tool schema', 'provider_request_id', 'runtime_flags'];
const CANONICAL_JOB_COMMAND_TYPES = new Set<SovereignEngineCommandType>([
  'RESTORE_LATEST_JOB',
  'READ_JOB',
  'START_REPOSITORY_EXECUTION',
  'START_TOOLCHAIN_JOB',
  'CANCEL_JOB',
]);
const OPERATION_RESULT_KINDS = new Set<SovereignEngineOperationResultKind>([
  'JANITOR',
  'DRAFT_PR_PREPARATION',
  'DRAFT_PR_CREATE',
]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isSafeId(value: unknown): value is string {
  return typeof value === 'string' && SAFE_ID.test(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function eventId(prefix: string): string {
  const uuid = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID().replaceAll('-', '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${uuid.slice(0, 32)}`;
}

function boundedMessage(value: unknown): string {
  return maskSovereignAgentSensitiveText(String(value || 'Sovereign Engine command failed.')).slice(0, 1200);
}

function boundedDisplayText(value: unknown, maxLength: number): string | undefined {
  if (!isNonEmptyString(value)) return undefined;
  return maskSovereignAgentSensitiveText(value.trim()).slice(0, maxLength);
}

function repositoryForProjection(value: unknown): string | undefined {
  if (!isNonEmptyString(value)) return undefined;
  try {
    const parsed = new URL(value.trim());
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return undefined;
    parsed.username = '';
    parsed.password = '';
    return boundedDisplayText(parsed.toString(), 600);
  } catch {
    return undefined;
  }
}

function expectedJobId(command: SovereignEngineCommandV1): string | undefined {
  switch (command.commandType) {
    case 'READ_JOB':
    case 'CANCEL_JOB':
    case 'READ_PROJECTIONS':
    case 'READ_EVIDENCE_ANCHORS':
    case 'RUN_JANITOR':
    case 'PREPARE_DRAFT_PR':
    case 'CREATE_DRAFT_PR':
      return command.payload.jobId.trim();
    default:
      return undefined;
  }
}

function commandRepository(command: SovereignEngineCommandV1): { repoUrl?: string; branch?: string } {
  if (command.commandType === 'START_REPOSITORY_EXECUTION' || command.commandType === 'START_TOOLCHAIN_JOB') {
    return {
      repoUrl: repositoryForProjection(command.payload.input.repoUrl),
      branch: boundedDisplayText(command.payload.input.branch || 'main', 200),
    };
  }
  return {};
}

function commandAdoptsJob(command: SovereignEngineCommandV1): boolean {
  return command.commandType === 'READ_JOB' && command.payload.adopt === true;
}

function assertExactKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
  const unknown = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unknown.length > 0) throw new Error(`${label} contains unknown fields: ${unknown.join(', ')}`);
}

function assertCommand(command: SovereignEngineCommandV1): void {
  if (!isObject(command)) throw new Error('Sovereign Engine command must be an object.');
  assertExactKeys(
    command,
    ['schemaVersion', 'commandId', 'commandType', 'sessionId', 'correlationId', 'issuedAt', 'payload'],
    'Sovereign Engine command',
  );
  if (command.schemaVersion !== SOVEREIGN_ENGINE_COMMAND_SCHEMA_VERSION) {
    throw new Error('Unsupported Sovereign Engine command schema.');
  }
  if (!COMMAND_TYPES.has(command.commandType)) throw new Error('Unsupported Sovereign Engine command type.');
  if (!isSafeId(command.commandId) || !isSafeId(command.sessionId) || !isSafeId(command.correlationId)) {
    throw new Error('Sovereign Engine command identity is invalid.');
  }
  if (!Number.isFinite(command.issuedAt) || command.issuedAt <= 0) {
    throw new Error('Sovereign Engine command timestamp is invalid.');
  }
  if (!isObject(command.payload)) throw new Error('Sovereign Engine command payload must be an object.');

  switch (command.commandType) {
    case 'RESTORE_LATEST_JOB':
      assertExactKeys(command.payload, [], command.commandType);
      return;
    case 'READ_JOB':
      assertExactKeys(command.payload, ['jobId', 'adopt'], command.commandType);
      if (!isSafeId(command.payload.jobId)) throw new Error('READ_JOB requires a valid jobId.');
      if (command.payload.adopt !== undefined && typeof command.payload.adopt !== 'boolean') {
        throw new Error('READ_JOB adopt must be boolean.');
      }
      return;
    case 'CANCEL_JOB':
    case 'READ_PROJECTIONS':
    case 'READ_EVIDENCE_ANCHORS':
      assertExactKeys(command.payload, ['jobId'], command.commandType);
      if (!isSafeId(command.payload.jobId)) throw new Error(`${command.commandType} requires a valid jobId.`);
      return;
    case 'RUN_JANITOR':
      assertExactKeys(command.payload, ['jobId', 'input'], command.commandType);
      if (!isSafeId(command.payload.jobId) || !isObject(command.payload.input)) {
        throw new Error('RUN_JANITOR requires a valid jobId and input.');
      }
      return;
    case 'PREPARE_DRAFT_PR':
      assertExactKeys(command.payload, ['jobId', 'headBranch'], command.commandType);
      if (!isSafeId(command.payload.jobId)
        || (command.payload.headBranch !== undefined && !isNonEmptyString(command.payload.headBranch))) {
        throw new Error('PREPARE_DRAFT_PR requires a valid jobId and optional headBranch.');
      }
      return;
    case 'CREATE_DRAFT_PR':
      assertExactKeys(command.payload, ['jobId', 'githubAccessToken'], command.commandType);
      if (!isSafeId(command.payload.jobId)
        || (command.payload.githubAccessToken !== undefined && !isNonEmptyString(command.payload.githubAccessToken))) {
        throw new Error('CREATE_DRAFT_PR requires a valid jobId and optional credential.');
      }
      return;
    case 'START_REPOSITORY_EXECUTION':
    case 'START_TOOLCHAIN_JOB':
      assertExactKeys(command.payload, ['input'], command.commandType);
      if (!isObject(command.payload.input)) throw new Error(`${command.commandType} requires an input object.`);
      if (!isNonEmptyString(command.payload.input.repoUrl) || !isNonEmptyString(command.payload.input.mission)) {
        throw new Error(`${command.commandType} requires repository and mission.`);
      }
      return;
  }
}

function isCanonicalJobSnapshot(value: unknown): value is SovereignAgentJobSnapshot {
  if (!isObject(value) || !JOB_STATUSES.has(String(value.status || ''))) return false;
  if (!Array.isArray(value.changedFiles) || !value.changedFiles.every((item) => typeof item === 'string')) return false;
  if (!Array.isArray(value.events) || !value.events.every(isObject)) return false;
  if (value.status !== 'idle' && !isSafeId(value.jobId)) return false;
  if (value.workspaceId !== undefined && !isNonEmptyString(value.workspaceId)) return false;
  return true;
}

function isCanonicalProjection(value: unknown): value is SovereignLiveProjection {
  if (!isObject(value)) return false;
  return value.authoritative === false
    && value.claim === 'OBSERVED'
    && isNonEmptyString(value.projectionId)
    && isNonEmptyString(value.eventId)
    && isNonEmptyString(value.sessionId)
    && isNonEmptyString(value.sessionBindingHash)
    && isNonEmptyString(value.attemptId)
    && isNonEmptyString(value.workspaceId)
    && isNonEmptyString(value.actionId)
    && isNonEmptyString(value.sourceReceiptRef)
    && isNonEmptyString(value.sourceIdentityHash)
    && isNonEmptyString(value.projectionHash)
    && isObject(value.payload);
}

function isCanonicalEvidenceAnchor(value: unknown): value is SovereignWorkspaceEvidenceAnchor {
  if (!isObject(value)) return false;
  const anchorId = value.anchorId;
  const claimKind = value.claimKind;
  const verdict = value.verdict;
  const sourceVerdict = value.sourceVerdict;
  const sessionBindingHash = value.sessionBindingHash;
  const runId = value.runId;
  const taskId = value.taskId;
  const attemptId = value.attemptId;
  const actionId = value.actionId;
  const scope = value.scope;
  const sourceKind = value.sourceKind;
  const sourceRefs = value.sourceRefs;
  const repositoryRevision = value.repositoryRevision;
  const targetRevision = value.targetRevision;
  const imageDigest = value.imageDigest;
  const runtimeIdentityHash = value.runtimeIdentityHash;
  const observedAt = value.observedAt;
  const freshnessReasons = value.freshnessReasons;
  const evidenceHash = value.evidenceHash;
  const foldedText = `${String(claimKind || '')} ${String(scope || '')}`.toLowerCase();
  return value.authoritative === false
    && typeof anchorId === 'string' && /^evidence-[a-f0-9]{24}$/.test(anchorId)
    && typeof claimKind === 'string' && claimKind.trim().length > 0
    && !['EVERYTHING_WORKS', 'READY', 'DONE', 'GREEN', 'ALL_GREEN'].includes(claimKind.toUpperCase())
    && typeof verdict === 'string' && EVIDENCE_VERDICTS.has(verdict)
    && typeof sourceVerdict === 'string' && EVIDENCE_VERDICTS.has(sourceVerdict)
    && typeof sessionBindingHash === 'string' && SHA256.test(sessionBindingHash.toLowerCase())
    && typeof runId === 'string' && runId.trim().length > 0
    && typeof taskId === 'string' && taskId.trim().length > 0
    && typeof attemptId === 'string' && attemptId.trim().length > 0
    && typeof actionId === 'string' && actionId.trim().length > 0
    && typeof scope === 'string' && scope.trim().length > 0
    && !FORBIDDEN_EVIDENCE_TEXT.some((marker) => foldedText.includes(marker))
    && typeof sourceKind === 'string' && EVIDENCE_SOURCE_KINDS.has(sourceKind)
    && Array.isArray(sourceRefs) && sourceRefs.length > 0 && sourceRefs.length <= 32
    && sourceRefs.every((ref) => typeof ref === 'string' && SHA256.test(ref.toLowerCase()))
    && typeof repositoryRevision === 'string' && REVISION.test(repositoryRevision.toLowerCase())
    && (targetRevision === undefined || (typeof targetRevision === 'string' && REVISION.test(targetRevision.toLowerCase())))
    && (imageDigest === undefined || (typeof imageDigest === 'string' && IMAGE_DIGEST.test(imageDigest.toLowerCase())))
    && (runtimeIdentityHash === undefined || (typeof runtimeIdentityHash === 'string' && SHA256.test(runtimeIdentityHash.toLowerCase())))
    && typeof observedAt === 'string' && Number.isFinite(Date.parse(observedAt))
    && Array.isArray(freshnessReasons) && freshnessReasons.every((reason) => typeof reason === 'string')
    && typeof evidenceHash === 'string' && SHA256.test(evidenceHash.toLowerCase())
    && !(sourceKind === 'FRAME_OBSERVATION' && verdict === 'VERIFIED');
}

function isCommandEnvelope(
  payload: unknown,
): payload is { commandId: string; commandType: SovereignEngineCommandType } {
  if (!isObject(payload) || !isSafeId(payload.commandId) || typeof payload.commandType !== 'string') {
    return false;
  }
  return COMMAND_TYPES.has(payload.commandType as SovereignEngineCommandType);
}

function baseEvent(
  command: SovereignEngineCommandV1,
  eventType: SovereignEngineEventV1['eventType'],
  source: SovereignEngineEventV1['source'],
  now: () => number,
): Omit<SovereignEngineEventV1, 'eventType' | 'source' | 'payload'> {
  return {
    schemaVersion: SOVEREIGN_ENGINE_EVENT_SCHEMA_VERSION,
    eventId: eventId('engine-event'),
    sessionId: command.sessionId,
    causationId: command.commandId,
    correlationId: command.correlationId,
    occurredAt: now(),
    jobId: expectedJobId(command),
  };
}

export function createSovereignEngineCommand<T extends SovereignEngineCommandType>(
  sessionId: string,
  commandType: T,
  payload: SovereignEngineCommandPayloads[T],
  options: {
    commandId?: string;
    correlationId?: string;
    issuedAt?: number;
  } = {},
): SovereignEngineCommandFor<T> {
  const commandId = options.commandId || eventId('engine-command');
  return {
    schemaVersion: SOVEREIGN_ENGINE_COMMAND_SCHEMA_VERSION,
    commandId,
    commandType,
    sessionId,
    correlationId: options.correlationId || commandId,
    issuedAt: options.issuedAt || Date.now(),
    payload,
  } as SovereignEngineCommandFor<T>;
}

export function createSovereignEngineCommandAcceptedEvent(
  command: SovereignEngineCommandV1,
  now: () => number = Date.now,
): SovereignEngineEventV1 {
  assertCommand(command);
  const repository = commandRepository(command);
  return {
    ...baseEvent(command, 'ENGINE_COMMAND_ACCEPTED', 'CLIENT_CONTROL', now),
    eventType: 'ENGINE_COMMAND_ACCEPTED',
    source: 'CLIENT_CONTROL',
    payload: {
      commandId: command.commandId,
      commandType: command.commandType,
      expectedJobId: expectedJobId(command),
      adoptJob: commandAdoptsJob(command),
      ...repository,
    },
  };
}

function commandFailureIsUserVisible(command: SovereignEngineCommandV1): boolean {
  if (command.commandType === 'READ_JOB' && command.payload.adopt === true) return true;
  return !['RESTORE_LATEST_JOB', 'READ_JOB', 'READ_PROJECTIONS', 'READ_EVIDENCE_ANCHORS'].includes(command.commandType);
}

export function createSovereignEngineCommandFailedEvent(
  command: SovereignEngineCommandV1,
  error: unknown,
  now: () => number = Date.now,
): SovereignEngineEventV1 {
  assertCommand(command);
  return {
    ...baseEvent(command, 'ENGINE_COMMAND_FAILED', 'CLIENT_CONTROL', now),
    eventType: 'ENGINE_COMMAND_FAILED',
    source: 'CLIENT_CONTROL',
    payload: {
      commandId: command.commandId,
      commandType: command.commandType,
      message: boundedMessage(error instanceof Error ? error.message : error),
      userVisible: commandFailureIsUserVisible(command),
    },
  };
}

export function createSovereignClientBoundaryBlockedEvent(
  sessionId: string,
  operation: string,
  message: string,
  options: { correlationId?: string; repoUrl?: string; branch?: string; occurredAt?: number } = {},
): SovereignEngineEventV1 {
  const id = eventId('engine-client-blocked');
  return {
    schemaVersion: SOVEREIGN_ENGINE_EVENT_SCHEMA_VERSION,
    eventId: id,
    eventType: 'CLIENT_BOUNDARY_BLOCKED',
    source: 'CLIENT_CONTROL',
    sessionId,
    causationId: id,
    correlationId: options.correlationId || id,
    occurredAt: options.occurredAt || Date.now(),
    payload: {
      operation: operation.slice(0, 120),
      message: boundedMessage(message),
      repoUrl: repositoryForProjection(options.repoUrl),
      branch: boundedDisplayText(options.branch, 200),
    },
  };
}

export async function executeSovereignEngineCommand(
  command: SovereignEngineCommandV1,
  transport: SovereignEngineTransport,
  now: () => number = Date.now,
): Promise<SovereignEngineEventV1> {
  assertCommand(command);

  switch (command.commandType) {
    case 'RESTORE_LATEST_JOB': {
      const jobs = await transport.listJobs();
      if (!Array.isArray(jobs)) {
        throw new Error('Sovereign backend returned an invalid canonical job list.');
      }
      if (jobs.length === 0) {
        return {
          ...baseEvent(command, 'CANONICAL_JOB_LIST_EMPTY', 'SOVEREIGN_BACKEND', now),
          eventType: 'CANONICAL_JOB_LIST_EMPTY',
          source: 'SOVEREIGN_BACKEND',
          payload: { commandId: command.commandId, commandType: command.commandType },
        };
      }
      return canonicalJobEvent(command, jobs[0], now);
    }
    case 'READ_JOB':
      return canonicalJobEvent(command, await transport.getJob(command.payload.jobId), now);
    case 'START_REPOSITORY_EXECUTION':
      return canonicalJobEvent(command, await transport.startRepositoryExecution(command.payload.input), now);
    case 'START_TOOLCHAIN_JOB':
      return canonicalJobEvent(command, await transport.startToolchainJob(command.payload.input), now);
    case 'CANCEL_JOB':
      return canonicalJobEvent(command, await transport.cancelJob(command.payload.jobId), now);
    case 'READ_PROJECTIONS': {
      const projections = await transport.getProjections(command.payload.jobId);
      if (!Array.isArray(projections) || !projections.every(isCanonicalProjection)) {
        throw new Error('Sovereign backend returned an invalid projection contract.');
      }
      return {
        ...baseEvent(command, 'CANONICAL_PROJECTIONS_ACCEPTED', 'SOVEREIGN_BACKEND', now),
        eventType: 'CANONICAL_PROJECTIONS_ACCEPTED',
        source: 'SOVEREIGN_BACKEND',
        jobId: command.payload.jobId,
        workspaceId: projections[0]?.workspaceId,
        attemptId: uniqueProjectionAttempt(projections),
        payload: {
          commandId: command.commandId,
          commandType: command.commandType,
          projections,
        },
      };
    }
    case 'READ_EVIDENCE_ANCHORS': {
      const evidenceAnchors = await transport.getEvidenceAnchors(command.payload.jobId);
      if (!Array.isArray(evidenceAnchors) || !evidenceAnchors.every(isCanonicalEvidenceAnchor)) {
        throw new Error('Sovereign backend returned an invalid evidence anchor contract.');
      }
      return {
        ...baseEvent(command, 'CANONICAL_EVIDENCE_ANCHORS_ACCEPTED', 'SOVEREIGN_BACKEND', now),
        eventType: 'CANONICAL_EVIDENCE_ANCHORS_ACCEPTED',
        source: 'SOVEREIGN_BACKEND',
        jobId: command.payload.jobId,
        attemptId: uniqueEvidenceAnchorAttempt(evidenceAnchors),
        payload: {
          commandId: command.commandId,
          commandType: command.commandType,
          evidenceAnchors,
        },
      };
    }
    case 'RUN_JANITOR':
      return operationResultEvent(
        command,
        'JANITOR',
        await transport.runJanitor(command.payload.jobId, command.payload.input),
        now,
      );
    case 'PREPARE_DRAFT_PR':
      return operationResultEvent(
        command,
        'DRAFT_PR_PREPARATION',
        await transport.prepareDraftPr(command.payload.jobId, command.payload.headBranch),
        now,
      );
    case 'CREATE_DRAFT_PR':
      return operationResultEvent(
        command,
        'DRAFT_PR_CREATE',
        await transport.createDraftPr(command.payload.jobId, command.payload.githubAccessToken),
        now,
      );
  }
}

function canonicalJobEvent(
  command: Extract<
    SovereignEngineCommandV1,
    { commandType: 'RESTORE_LATEST_JOB' | 'READ_JOB' | 'START_REPOSITORY_EXECUTION' | 'START_TOOLCHAIN_JOB' | 'CANCEL_JOB' }
  >,
  job: SovereignAgentJobSnapshot,
  now: () => number,
): SovereignEngineEventV1 {
  if (!isCanonicalJobSnapshot(job)) {
    throw new Error('Sovereign backend returned an invalid canonical job snapshot.');
  }
  const expected = expectedJobId(command);
  if (expected && job.jobId !== expected) {
    throw new Error('Sovereign backend returned a job snapshot for another identity.');
  }
  return {
    ...baseEvent(command, 'CANONICAL_JOB_SNAPSHOT_ACCEPTED', 'SOVEREIGN_BACKEND', now),
    eventType: 'CANONICAL_JOB_SNAPSHOT_ACCEPTED',
    source: 'SOVEREIGN_BACKEND',
    jobId: job.jobId,
    workspaceId: job.workspaceId,
    payload: {
      commandId: command.commandId,
      commandType: command.commandType,
      job,
    },
  };
}

function operationResultEvent<K extends SovereignEngineOperationResultKind>(
  command: Extract<SovereignEngineCommandV1, { commandType: 'RUN_JANITOR' | 'PREPARE_DRAFT_PR' | 'CREATE_DRAFT_PR' }>,
  resultKind: K,
  result: SovereignEngineOperationResultByKind[K],
  now: () => number,
): SovereignEngineEventV1 {
  return {
    ...baseEvent(command, 'ENGINE_OPERATION_RESULT_ACCEPTED', 'SOVEREIGN_BACKEND', now),
    eventType: 'ENGINE_OPERATION_RESULT_ACCEPTED',
    source: 'SOVEREIGN_BACKEND',
    jobId: expectedJobId(command),
    payload: {
      commandId: command.commandId,
      commandType: command.commandType,
      resultKind,
      result,
    },
  } as SovereignEngineEventV1;
}

function uniqueProjectionAttempt(projections: readonly SovereignLiveProjection[]): string | undefined {
  const attempts = new Set(projections.map((projection) => projection.attemptId).filter(Boolean));
  return attempts.size === 1 ? [...attempts][0] : undefined;
}

function uniqueEvidenceAnchorAttempt(anchors: readonly SovereignWorkspaceEvidenceAnchor[]): string | undefined {
  const attempts = new Set(anchors.map((anchor) => anchor.attemptId).filter(Boolean));
  return attempts.size === 1 ? [...attempts][0] : undefined;
}

export function createInitialSovereignEngineState(
  options: { sessionId?: string; job?: SovereignAgentJobSnapshot } = {},
): SovereignEngineState {
  return {
    sessionId: options.sessionId || eventId('engine-session'),
    canonicalJob: options.job || createSovereignAgentIdleSnapshot(),
    projections: [],
    evidenceAnchors: [],
    pendingCommands: {},
    acceptedEventIds: [],
    nextCommandSequence: 1,
    canonicalJobSequence: 0,
    projectionSequence: 0,
    evidenceAnchorSequence: 0,
  };
}

function isBaseEventAccepted(state: SovereignEngineState, event: SovereignEngineEventV1): boolean {
  if (!isObject(event)) return false;
  return event.schemaVersion === SOVEREIGN_ENGINE_EVENT_SCHEMA_VERSION
    && event.sessionId === state.sessionId
    && isSafeId(event.eventId)
    && isSafeId(event.causationId)
    && isSafeId(event.correlationId)
    && Number.isFinite(event.occurredAt)
    && event.occurredAt > 0
    && !state.acceptedEventIds.includes(event.eventId);
}

function rememberEvent(state: SovereignEngineState, eventIdValue: string): readonly string[] {
  // Engine sessions are bounded by the page/session lifecycle. Keeping the
  // complete set prevents an old accepted command/result pair from becoming
  // replayable merely because a fixed-size cache evicted its identifiers.
  return [...state.acceptedEventIds, eventIdValue];
}

function withoutPending(
  pending: Readonly<Record<string, SovereignEnginePendingCommand>>,
  commandId: string,
): Readonly<Record<string, SovereignEnginePendingCommand>> {
  const next = { ...pending };
  delete next[commandId];
  return next;
}

function pendingMatches(
  state: SovereignEngineState,
  event: Extract<SovereignEngineEventV1, { payload: { commandId: string; commandType: SovereignEngineCommandType } }>,
): SovereignEnginePendingCommand | undefined {
  const pending = state.pendingCommands[event.payload.commandId];
  if (!pending || pending.commandId !== event.causationId || pending.commandType !== event.payload.commandType) {
    return undefined;
  }
  return pending;
}

function canonicalJobIdentityAllowed(
  state: SovereignEngineState,
  pending: SovereignEnginePendingCommand,
  job: SovereignAgentJobSnapshot,
): boolean {
  if (!isCanonicalJobSnapshot(job)) return false;
  const currentJobId = state.canonicalJob.jobId;
  switch (pending.commandType) {
    case 'RESTORE_LATEST_JOB':
      return state.canonicalJob.status === 'idle' || currentJobId === job.jobId;
    case 'START_REPOSITORY_EXECUTION':
    case 'START_TOOLCHAIN_JOB':
      return true;
    case 'READ_JOB':
      if (pending.expectedJobId !== job.jobId) return false;
      return pending.adoptJob || !currentJobId || currentJobId === job.jobId;
    case 'CANCEL_JOB':
      return pending.expectedJobId === job.jobId && currentJobId === job.jobId;
    default:
      return false;
  }
}

function resultKindMatchesCommand(
  commandType: SovereignEngineCommandType,
  resultKind: SovereignEngineOperationResultKind,
): boolean {
  return (commandType === 'RUN_JANITOR' && resultKind === 'JANITOR')
    || (commandType === 'PREPARE_DRAFT_PR' && resultKind === 'DRAFT_PR_PREPARATION')
    || (commandType === 'CREATE_DRAFT_PR' && resultKind === 'DRAFT_PR_CREATE');
}

function resolvePendingWithoutProjection(
  state: SovereignEngineState,
  pending: SovereignEnginePendingCommand,
  event: SovereignEngineEventV1,
): SovereignEngineState {
  return {
    ...state,
    pendingCommands: withoutPending(state.pendingCommands, pending.commandId),
    acceptedEventIds: rememberEvent(state, event.eventId),
  };
}

/**
 * The only reducer allowed to change the canonical frontend runtime projection.
 * A result event without a previously accepted typed command is ignored.
 */
export function sovereignEngineReducer(
  state: SovereignEngineState,
  event: SovereignEngineEventV1,
): SovereignEngineState {
  if (!isBaseEventAccepted(state, event)) return state;

  switch (event.eventType) {
    case 'ENGINE_COMMAND_ACCEPTED': {
      if (event.source !== 'CLIENT_CONTROL'
        || !isCommandEnvelope(event.payload)
        || event.payload.commandId !== event.causationId
        || typeof event.payload.adoptJob !== 'boolean'
        || (event.payload.expectedJobId !== undefined && !isSafeId(event.payload.expectedJobId))
        || (event.payload.repoUrl !== undefined && !isNonEmptyString(event.payload.repoUrl))
        || (event.payload.branch !== undefined && !isNonEmptyString(event.payload.branch))
        || state.pendingCommands[event.payload.commandId]) {
        return state;
      }
      const pending: SovereignEnginePendingCommand = {
        commandId: event.payload.commandId,
        commandType: event.payload.commandType,
        correlationId: event.correlationId,
        startedAt: event.occurredAt,
        sequence: state.nextCommandSequence,
        expectedJobId: event.payload.expectedJobId,
        adoptJob: event.payload.adoptJob,
        repoUrl: event.payload.repoUrl,
        branch: event.payload.branch,
      };
      return {
        ...state,
        pendingCommands: { ...state.pendingCommands, [pending.commandId]: pending },
        nextCommandSequence: state.nextCommandSequence + 1,
        clientNotice: event.payload.commandType === 'READ_JOB' && event.payload.adoptJob
          ? undefined
          : !['RESTORE_LATEST_JOB', 'READ_JOB', 'READ_PROJECTIONS', 'READ_EVIDENCE_ANCHORS'].includes(event.payload.commandType)
            ? undefined
            : state.clientNotice,
        acceptedEventIds: rememberEvent(state, event.eventId),
      };
    }

    case 'CANONICAL_JOB_SNAPSHOT_ACCEPTED': {
      if (event.source !== 'SOVEREIGN_BACKEND'
        || !isCommandEnvelope(event.payload)
        || !isCanonicalJobSnapshot(event.payload.job)) return state;
      const pending = pendingMatches(state, event);
      if (!pending || !canonicalJobIdentityAllowed(state, pending, event.payload.job)) return state;
      if (pending.sequence < state.canonicalJobSequence) {
        return resolvePendingWithoutProjection(state, pending, event);
      }
      return {
        ...state,
        canonicalJob: event.payload.job,
        canonicalJobSequence: pending.sequence,
        projections: state.canonicalJob.jobId === event.payload.job.jobId
          && event.payload.job.status !== 'cleaned'
          ? state.projections
          : [],
        evidenceAnchors: state.canonicalJob.jobId === event.payload.job.jobId
          && event.payload.job.status !== 'cleaned'
          ? state.evidenceAnchors
          : [],
        pendingCommands: withoutPending(state.pendingCommands, pending.commandId),
        clientNotice: undefined,
        acceptedEventIds: rememberEvent(state, event.eventId),
      };
    }

    case 'CANONICAL_JOB_LIST_EMPTY': {
      if (event.source !== 'SOVEREIGN_BACKEND' || !isCommandEnvelope(event.payload)) return state;
      const pending = pendingMatches(state, event);
      if (!pending || pending.commandType !== 'RESTORE_LATEST_JOB') return state;
      return {
        ...state,
        pendingCommands: withoutPending(state.pendingCommands, pending.commandId),
        acceptedEventIds: rememberEvent(state, event.eventId),
      };
    }

    case 'CANONICAL_PROJECTIONS_ACCEPTED': {
      if (event.source !== 'SOVEREIGN_BACKEND'
        || !isCommandEnvelope(event.payload)
        || !Array.isArray(event.payload.projections)) return state;
      const pending = pendingMatches(state, event);
      if (!pending
        || pending.commandType !== 'READ_PROJECTIONS'
        || pending.expectedJobId !== state.canonicalJob.jobId
        || event.jobId !== state.canonicalJob.jobId
        || !event.payload.projections.every(isCanonicalProjection)) {
        return state;
      }
      if (pending.sequence < state.projectionSequence) {
        return resolvePendingWithoutProjection(state, pending, event);
      }
      return {
        ...state,
        projections: [...event.payload.projections],
        projectionSequence: pending.sequence,
        pendingCommands: withoutPending(state.pendingCommands, pending.commandId),
        acceptedEventIds: rememberEvent(state, event.eventId),
      };
    }

    case 'CANONICAL_EVIDENCE_ANCHORS_ACCEPTED': {
      if (event.source !== 'SOVEREIGN_BACKEND'
        || !isCommandEnvelope(event.payload)
        || !Array.isArray(event.payload.evidenceAnchors)) return state;
      const pending = pendingMatches(state, event);
      if (!pending
        || pending.commandType !== 'READ_EVIDENCE_ANCHORS'
        || pending.expectedJobId !== state.canonicalJob.jobId
        || event.jobId !== state.canonicalJob.jobId
        || !event.payload.evidenceAnchors.every(isCanonicalEvidenceAnchor)) {
        return state;
      }
      if (pending.sequence < state.evidenceAnchorSequence) {
        return resolvePendingWithoutProjection(state, pending, event);
      }
      return {
        ...state,
        evidenceAnchors: [...event.payload.evidenceAnchors],
        evidenceAnchorSequence: pending.sequence,
        pendingCommands: withoutPending(state.pendingCommands, pending.commandId),
        acceptedEventIds: rememberEvent(state, event.eventId),
      };
    }

    case 'ENGINE_OPERATION_RESULT_ACCEPTED': {
      if (event.source !== 'SOVEREIGN_BACKEND'
        || !isCommandEnvelope(event.payload)
        || !OPERATION_RESULT_KINDS.has(event.payload.resultKind)) return state;
      const pending = pendingMatches(state, event);
      if (!pending
        || pending.expectedJobId !== state.canonicalJob.jobId
        || !resultKindMatchesCommand(pending.commandType, event.payload.resultKind)) {
        return state;
      }
      return {
        ...state,
        pendingCommands: withoutPending(state.pendingCommands, pending.commandId),
        clientNotice: undefined,
        acceptedEventIds: rememberEvent(state, event.eventId),
      };
    }

    case 'ENGINE_COMMAND_FAILED': {
      if (event.source !== 'CLIENT_CONTROL'
        || !isCommandEnvelope(event.payload)
        || typeof event.payload.message !== 'string'
        || typeof event.payload.userVisible !== 'boolean') return state;
      const pending = pendingMatches(state, event);
      if (!pending) return state;
      const staleCanonicalFailure = CANONICAL_JOB_COMMAND_TYPES.has(pending.commandType)
        && pending.sequence < state.canonicalJobSequence;
      return {
        ...state,
        pendingCommands: withoutPending(state.pendingCommands, pending.commandId),
        clientNotice: event.payload.userVisible && !staleCanonicalFailure
          ? {
              operation: event.payload.commandType,
              message: boundedMessage(event.payload.message),
              correlationId: event.correlationId,
              occurredAt: event.occurredAt,
            }
          : state.clientNotice,
        acceptedEventIds: rememberEvent(state, event.eventId),
      };
    }

    case 'CLIENT_BOUNDARY_BLOCKED': {
      if (event.source !== 'CLIENT_CONTROL'
        || !isObject(event.payload)
        || !isNonEmptyString(event.payload.operation)
        || !isNonEmptyString(event.payload.message)) return state;
      return {
        ...state,
        clientNotice: {
          operation: event.payload.operation,
          message: boundedMessage(event.payload.message),
          correlationId: event.correlationId,
          occurredAt: event.occurredAt,
        },
        acceptedEventIds: rememberEvent(state, event.eventId),
      };
    }
  }

  // Runtime defense for callers crossing the TypeScript boundary from plain JS.
  // Unknown event kinds are observations at most and never mutate state.
  return state;
}

/**
 * UI-only projection. Local validation/pending state is visually useful but is
 * never written into canonicalJob and therefore cannot fabricate runtime truth.
 */
export function selectSovereignEngineJobProjection(state: SovereignEngineState): SovereignAgentJobSnapshot {
  if (state.canonicalJob.status !== 'idle') {
    return state.clientNotice
      ? { ...state.canonicalJob, lastError: state.clientNotice.message }
      : state.canonicalJob;
  }

  if (state.clientNotice) {
    return {
      status: 'blocked',
      changedFiles: [],
      events: [],
      lastError: state.clientNotice.message,
    };
  }

  const pendingStart = Object.values(state.pendingCommands)
    .filter((pending) => pending.commandType === 'START_REPOSITORY_EXECUTION'
      || pending.commandType === 'START_TOOLCHAIN_JOB')
    .reduce<SovereignEnginePendingCommand | undefined>(
      (latest, pending) => !latest || pending.sequence > latest.sequence ? pending : latest,
      undefined,
    );
  if (pendingStart) {
    return {
      status: 'queued',
      repoUrl: pendingStart.repoUrl,
      branch: pendingStart.branch,
      changedFiles: [],
      events: [],
    };
  }

  return state.canonicalJob;
}

export function hasSovereignEnginePendingCommand(
  state: SovereignEngineState,
  commandTypes?: readonly SovereignEngineCommandType[],
): boolean {
  const pending = Object.values(state.pendingCommands);
  return commandTypes ? pending.some((item) => commandTypes.includes(item.commandType)) : pending.length > 0;
}

export function sovereignEngineJobFromEvent(
  event: SovereignEngineEventV1,
): SovereignAgentJobSnapshot | undefined {
  return event.eventType === 'CANONICAL_JOB_SNAPSHOT_ACCEPTED' ? event.payload.job : undefined;
}

export function sovereignEngineOperationResultFromEvent<K extends SovereignEngineOperationResultKind>(
  event: SovereignEngineEventV1,
  resultKind: K,
): SovereignEngineOperationResultByKind[K] | undefined {
  if (event.eventType !== 'ENGINE_OPERATION_RESULT_ACCEPTED' || event.payload.resultKind !== resultKind) {
    return undefined;
  }
  return event.payload.result as SovereignEngineOperationResultByKind[K];
}
