import {
  buildSovereignAgentJobRequest,
  type SovereignAgentConfig,
  type SovereignAgentJobRequest,
  type SovereignAgentJobSnapshot,
  type SovereignAgentRuntimeEvent,
  type SovereignLiveProjection,
  type SovereignWorkspaceEvidenceAnchor,
  resolveSovereignAgentConfig,
} from './sovereignAgentRuntime';

export interface SovereignAgentClientOptions {
  config?: SovereignAgentConfig;
  fetcher?: typeof fetch;
  now?: () => number;
}

export interface SovereignRepositoryExecutionInput {
  repoUrl: string;
  branch?: string;
  expectedHeadSha?: string;
  mission: string;
  evidenceText?: string;
  githubAccessToken?: string;
}

export interface SovereignDesktopFrameObservation {
  readonly blob: Blob;
  readonly frameHash: string;
  readonly observedAt: number;
}

export interface SovereignPatternLearningEvidence {
  candidateId?: string;
  candidateCreated: boolean;
  allowed: boolean;
  decision: string;
  vectorStored: boolean;
  vectorStorage?: string;
  vectorReason?: string;
}

export interface SovereignStagedFile {
  path: string;
  content: string;
  baseContent?: string;
}

export interface SovereignAgentStartJobInput {
  repoUrl: string;
  branch?: string;
  expectedHeadSha?: string;
  mission: string;
  provisionWorkspace?: boolean;
  cloneRepo?: boolean;
  stagedFiles?: readonly SovereignStagedFile[];
  testCommand?: string;
  githubAccessToken?: string;
}

export interface SovereignToolchainStartJobInput extends SovereignAgentStartJobInput {
  evidenceText?: string;
}

export interface SovereignToolchainFailureFamily {
  code: string;
  title: string;
  severity: string;
  score: number;
  checks: string[];
}

export interface SovereignToolchainFollowup {
  fromFamily: string;
  prediction: string;
  checkNext: string;
}

export interface SovereignToolchainDiagnosis {
  evidenceHash?: string;
  failureFamilies: SovereignToolchainFailureFamily[];
  nextLogicalFailures: SovereignToolchainFollowup[];
}

export interface SovereignDraftPrPreparationResponse {
  ok: boolean;
  jobId: string;
  draftPrPreparation: {
    allowed: boolean;
    decision: string;
    summary?: string;
    headBranch?: string;
    baseBranch?: string;
    nextAction?: string;
    canCreateDraftPr?: boolean;
    blockers: string[];
  };
  learningEvidence?: SovereignPatternLearningEvidence;
}

export type SovereignDraftPrCiState = 'none' | 'pending' | 'success' | 'failure';

export interface SovereignDraftPrCreateResponse {
  ok: boolean;
  jobId: string;
  draftPrCreate: {
    allowed: boolean;
    status: string;
    prUrl: string;
    headSha: string;
    publishedHeadSha: string;
    readbackHeadSha: string;
    prNumber: number;
    draftVerified: true;
    prStateVerified: 'open';
    headBranch: string;
    baseBranch: string;
    readbackVerified: true;
    checksReadbackVerified: true;
    ciState: SovereignDraftPrCiState;
    checkRunCount: number;
    checksPendingCount: number;
    checksSuccessCount: number;
    checksFailureCount: number;
    statusContextCount: number;
    blocker?: string;
    summary?: string;
  };
}

export interface SovereignJanitorFinding {
  id: string;
  ruleId: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | string;
  path: string;
  line: number;
  message: string;
  evidence: string;
  contentSha256: string;
  fixAvailable: boolean;
  suggestedSearchText?: string | null;
  suggestedReplacementText?: string | null;
}

export interface SovereignJanitorScanInput {
  mode?: 'scan';
  family?: string;
  paths?: string[];
  maxFindings?: number;
  maxFiles?: number;
  includeDocs?: boolean;
  explainWithLocalModel?: boolean;
}

export interface SovereignJanitorApplyInput {
  mode: 'apply';
  path: string;
  searchText: string;
  replacementText: string;
  expectedSha256: string;
  confirm: true;
}

export type SovereignJanitorInput = SovereignJanitorScanInput | SovereignJanitorApplyInput;

export interface SovereignJanitorToolResponse {
  ok: boolean;
  jobId: string;
  tool: {
    status: string;
    output?: string;
    blocker?: string;
    changedFiles: string[];
    diffSummary?: string;
    testSummary?: string;
    metadata: Record<string, unknown>;
    evidenceGate?: unknown;
  };
}

interface RawSovereignAgentJobResponse {
  jobId?: unknown;
  id?: unknown;
  runtimeId?: unknown;
  workspaceId?: unknown;
  status?: unknown;
  repoUrl?: unknown;
  branch?: unknown;
  branchName?: unknown;
  draftPrUrl?: unknown;
  changedFiles?: unknown;
  events?: unknown;
  lastError?: unknown;
  error?: unknown;
  message?: unknown;
  details?: unknown;
  blocker?: unknown;
}

function endpoint(baseUrl: string, route: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/${route.replace(/^\/+/, '')}`;
}

// ── User-facing HTTP failure classification ─────────────────────────────────
//
// The backend answers blocked journeys with typed blocker codes, e.g.
// HTTP 503 + "free_route_revolver_exhausted" (free quota used up) or
// HTTP 428 + "step_up_required" (paid route needs explicit confirmation).
// The UI surfaces `error.message` verbatim in the action stream and runtime
// notices, so the message must be actionable instead of a raw blocker code.
// Fail-closed: unknown failures keep the previous generic behavior, and no
// classification ever implies an automatic escalation from free to paid.

export type SovereignAgentHttpFailureKind =
  | 'step_up_required'
  | 'free_route_exhausted'
  | 'paid_credits_required'
  | 'paid_purchase_required'
  | 'generic';

export interface SovereignAgentHttpFailureClassification {
  readonly kind: SovereignAgentHttpFailureKind;
  readonly title: string;
  readonly guidance: string;
}

export function classifySovereignAgentHttpFailure(
  status: number,
  code?: string,
  backendMessage?: string,
): SovereignAgentHttpFailureClassification {
  const text = `${code ?? ''} ${backendMessage ?? ''}`.toLowerCase();

  if (status === 428 || text.includes('step_up') || text.includes('step-up')) {
    return {
      kind: 'step_up_required',
      title: 'Zusätzliche Bestätigung erforderlich (Step-Up)',
      guidance: 'Nächste Aktion: Die Ausführung über eine kostenpflichtige Route erfordert eine ausdrückliche Step-Up-Bestätigung. Bestätigung erteilen und den Vorgang erneut anstoßen; es erfolgt kein automatischer Wechsel auf eine Paid-Route.',
    };
  }

  if (status === 402 || text.includes('paid_credits_required')) {
    return {
      kind: 'paid_credits_required',
      title: 'Paid-Route ohne ausreichendes Guthaben',
      guidance: 'Nächste Aktion: Guthaben aufladen oder die kostenlose Route wählen; es erfolgt kein stiller Wechsel auf eine kostenpflichtige Route.',
    };
  }

  if (status === 403 && (text.includes('paid_purchase_required') || text.includes('entitlement'))) {
    return {
      kind: 'paid_purchase_required',
      title: 'Paid-Route erfordert einen verifizierten Kauf',
      guidance: 'Nächste Aktion: Kauf abschließen oder die kostenlose Route verwenden; es erfolgt kein stiller Wechsel auf eine kostenpflichtige Route.',
    };
  }

  const looksLikeFreeRouteExhausted = status === 503
    && (text.includes('free_route_revolver_exhausted')
      || text.includes('free_route')
      || text.includes('revolver')
      || text.includes('quota_exhausted')
      || text.includes('no_free_route'));
  if (looksLikeFreeRouteExhausted) {
    return {
      kind: 'free_route_exhausted',
      title: 'Kostenlose Route erschöpft',
      guidance: 'Nächste Aktion: Auf den Kontingent-Reset warten oder eine Paid-Route ausdrücklich per Step-Up bestätigen; es erfolgt kein stiller Wechsel auf eine Paid-Route.',
    };
  }

  return { kind: 'generic', title: '', guidance: '' };
}

/** Error thrown for non-OK agent backend responses; carries status + blocker code. */
export class SovereignAgentRequestError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly failureKind: SovereignAgentHttpFailureKind;
  constructor(args: { message: string; status: number; code?: string; failureKind: SovereignAgentHttpFailureKind }) {
    super(args.message);
    this.name = 'SovereignAgentRequestError';
    this.status = args.status;
    this.code = args.code;
    this.failureKind = args.failureKind;
  }
}

function buildSovereignAgentHttpError(args: {
  status: number;
  body: unknown;
  fallback: string;
}): SovereignAgentRequestError {
  const backendMessage = isObject(args.body) ? backendErrorMessage(args.body) : undefined;
  const code = isObject(args.body) ? stringValue(args.body.error) : undefined;
  const classification = classifySovereignAgentHttpFailure(args.status, code, backendMessage);
  if (classification.kind === 'generic') {
    return new SovereignAgentRequestError({
      message: backendMessage || `${args.fallback} returned HTTP ${args.status}.`,
      status: args.status,
      code,
      failureKind: classification.kind,
    });
  }
  const reason = backendMessage && backendMessage !== code ? ` Grund: ${backendMessage}.` : '';
  return new SovereignAgentRequestError({
    message: `${classification.title} (HTTP ${args.status}).${reason} ${classification.guidance}`,
    status: args.status,
    code,
    failureKind: classification.kind,
  });
}
function isObject(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null; }
function stringValue(value: unknown): string | undefined { return typeof value === 'string' && value.trim() ? value.trim() : undefined; }
function integerValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : undefined;
}
function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0).map((item) => item.trim());
}
function projectionArray(
  value: unknown,
  binding: {
    readonly jobId: string;
    readonly workspaceId: string;
    readonly sessionBindingHash: string;
    readonly attemptId: string;
  },
): SovereignLiveProjection[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isObject).flatMap((item): SovereignLiveProjection[] => {
    if (stringValue(item.schemaVersion) !== 'sovereign.visual-projection-event.v1') return [];
    const kind = stringValue(item.projectionKind);
    const state = stringValue(item.projectionState);
    const source = stringValue(item.sourceKind);
    const claim = stringValue(item.claim);
    const payload = isObject(item.payload) ? item.payload : undefined;
    const authoritative = item.authoritative === false;
    if (!kind || !state || !source || !payload || !authoritative || claim !== 'OBSERVED') return [];
    if (!['IDE_FILE', 'IDE_DIFF', 'TERMINAL', 'BROWSER', 'WINDOW_FOCUS'].includes(kind)) return [];
    if (!['REQUESTED', 'VISIBLE', 'UNAVAILABLE', 'STALE'].includes(state)) return [];
    if (!['MCP', 'REPOSITORY', 'GIT', 'PROCESS', 'PLAYWRIGHT', 'RUNTIME', 'GUI'].includes(source)) return [];
    const projectionId = stringValue(item.projectionId) || stringValue(item.eventId);
    const eventId = stringValue(item.eventId) || projectionId;
    const sessionId = stringValue(item.sessionId);
    const sessionBindingHash = stringValue(item.sessionBindingHash);
    const attemptId = stringValue(item.attemptId);
    const itemJobId = stringValue(item.jobId);
    const workspaceId = stringValue(item.workspaceId);
    const actionId = stringValue(item.actionId);
    const sourceReceiptRef = stringValue(item.sourceReceiptRef);
    const sourceIdentityHash = stringValue(item.sourceIdentityHash);
    const projectionHash = stringValue(item.projectionHash);
    if (!projectionId || !eventId || !sessionId || !sessionBindingHash || !attemptId || !workspaceId || !actionId || !sourceReceiptRef || !sourceIdentityHash || !projectionHash) return [];
    if (
      (itemJobId && itemJobId !== binding.jobId)
      || workspaceId !== binding.workspaceId
      || sessionBindingHash !== binding.sessionBindingHash
      || attemptId !== binding.attemptId
    ) return [];
    return [{
      projectionId,
      eventId,
      sessionId,
      sessionBindingHash,
      attemptId,
      runId: stringValue(item.runId),
      taskId: stringValue(item.taskId),
      jobId: binding.jobId,
      workspaceId,
      actionId,
      sourceKind: source as SovereignLiveProjection['sourceKind'],
      projectionKind: kind as SovereignLiveProjection['projectionKind'],
      projectionState: state as SovereignLiveProjection['projectionState'],
      repositoryHead: stringValue(item.repositoryHead) ?? null,
      sourceReceiptRef,
      sourceIdentityHash,
      payload,
      projectionHash,
      authoritative: false,
      claim: 'OBSERVED',
    }];
  });
}

const EVIDENCE_VERDICTS = new Set(['OBSERVED', 'UNVERIFIED', 'VERIFIED', 'BLOCKED', 'CONTRADICTED', 'STALE']);
const EVIDENCE_SOURCE_KINDS = new Set(['AGENT_RUN_RECEIPT', 'GITHUB_READBACK', 'PATCHMON_READBACK', 'DATABASE_READBACK', 'TARGET_READBACK', 'FRAME_OBSERVATION']);
const SHA256_RE = /^[0-9a-f]{64}$/;
const REVISION_RE = /^[0-9a-f]{40}$/;
const IMAGE_DIGEST_RE = /^sha256:[0-9a-f]{64}$/;
const FORBIDDEN_EVIDENCE_TEXT = ['chain-of-thought', 'reasoning:', 'system prompt', 'tool schema', 'provider_request_id', 'runtime_flags'];

function evidenceAnchorArray(
  value: unknown,
  binding: {
    readonly jobId: string;
    readonly workspaceId: string;
    readonly sessionBindingHash: string;
    readonly attemptId: string;
  },
): SovereignWorkspaceEvidenceAnchor[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isObject).flatMap((item): SovereignWorkspaceEvidenceAnchor[] => {
    if (stringValue(item.schemaVersion) !== 'sovereign.workspace-evidence-anchor.v1' || item.authoritative !== false) return [];
    const anchorId = stringValue(item.anchorId);
    const claimKind = stringValue(item.claimKind)?.toUpperCase();
    const verdict = stringValue(item.verdict)?.toUpperCase();
    const sourceVerdict = stringValue(item.sourceVerdict)?.toUpperCase();
    const sourceKind = stringValue(item.sourceKind)?.toUpperCase();
    const sessionBindingHash = stringValue(item.sessionBindingHash)?.toLowerCase();
    const repositoryRevision = stringValue(item.repositoryRevision)?.toLowerCase();
    const evidenceHash = stringValue(item.evidenceHash)?.toLowerCase();
    const sourceRefs = stringArray(item.sourceRefs).map((entry) => entry.toLowerCase());
    const scope = stringValue(item.scope);
    const foldedText = `${claimKind ?? ''} ${scope ?? ''}`.toLowerCase();
    if (
      !anchorId || !/^evidence-[0-9a-f]{24}$/.test(anchorId)
      || !claimKind || ['EVERYTHING_WORKS', 'READY', 'DONE', 'GREEN', 'ALL_GREEN'].includes(claimKind)
      || !verdict || !EVIDENCE_VERDICTS.has(verdict)
      || !sourceVerdict || !EVIDENCE_VERDICTS.has(sourceVerdict)
      || !sourceKind || !EVIDENCE_SOURCE_KINDS.has(sourceKind)
      || !sessionBindingHash || !SHA256_RE.test(sessionBindingHash)
      || !repositoryRevision || !REVISION_RE.test(repositoryRevision)
      || !evidenceHash || !SHA256_RE.test(evidenceHash)
      || !scope || FORBIDDEN_EVIDENCE_TEXT.some((marker) => foldedText.includes(marker))
      || sourceRefs.length === 0 || sourceRefs.length > 32 || sourceRefs.some((entry) => !SHA256_RE.test(entry))
      || (sourceKind === 'FRAME_OBSERVATION' && verdict === 'VERIFIED')
    ) return [];
    const runId = stringValue(item.runId);
    const taskId = stringValue(item.taskId);
    const attemptId = stringValue(item.attemptId);
    const itemJobId = stringValue(item.jobId);
    const itemWorkspaceId = stringValue(item.workspaceId);
    const actionId = stringValue(item.actionId);
    const observedAt = stringValue(item.observedAt);
    if (!runId || !taskId || !attemptId || !actionId || !observedAt || !Number.isFinite(Date.parse(observedAt))) return [];
    if (
      (itemJobId && itemJobId !== binding.jobId)
      || (itemWorkspaceId && itemWorkspaceId !== binding.workspaceId)
      || sessionBindingHash !== binding.sessionBindingHash
      || attemptId !== binding.attemptId
    ) return [];
    const targetRevision = stringValue(item.targetRevision)?.toLowerCase();
    const imageDigest = stringValue(item.imageDigest)?.toLowerCase();
    const runtimeIdentityHash = stringValue(item.runtimeIdentityHash)?.toLowerCase();
    if (targetRevision && !REVISION_RE.test(targetRevision)) return [];
    if (imageDigest && !IMAGE_DIGEST_RE.test(imageDigest)) return [];
    if (runtimeIdentityHash && !SHA256_RE.test(runtimeIdentityHash)) return [];
    return [{
      anchorId,
      jobId: binding.jobId,
      workspaceId: binding.workspaceId,
      claimKind,
      verdict: verdict as SovereignWorkspaceEvidenceAnchor['verdict'],
      sourceVerdict: sourceVerdict as SovereignWorkspaceEvidenceAnchor['sourceVerdict'],
      sessionBindingHash,
      runId,
      taskId,
      attemptId,
      actionId,
      scope,
      sourceKind: sourceKind as SovereignWorkspaceEvidenceAnchor['sourceKind'],
      sourceRefs,
      repositoryRevision,
      ...(targetRevision ? { targetRevision } : {}),
      ...(imageDigest ? { imageDigest } : {}),
      ...(runtimeIdentityHash ? { runtimeIdentityHash } : {}),
      ...(stringValue(item.frameObservationId) ? { frameObservationId: stringValue(item.frameObservationId) } : {}),
      observedAt,
      freshnessReasons: stringArray(item.freshnessReasons),
      evidenceHash,
      authoritative: false,
    }];
  });
}

function eventArray(value: unknown, now: () => number): SovereignAgentRuntimeEvent[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isObject).map((item): SovereignAgentRuntimeEvent => ({
    at: typeof item.at === 'number' && Number.isFinite(item.at) ? item.at : now(),
    level: item.level === 'warning' || item.level === 'error' || item.level === 'success' ? item.level : 'info',
    stage: stringValue(item.stage) || 'sovereign-agent',
    message: stringValue(item.message) || 'Sovereign Agent runtime event.',
  }));
}
function normalizeStatus(value: unknown): SovereignAgentJobSnapshot['status'] {
  if (value === 'queued' || value === 'provisioning' || value === 'running' || value === 'waiting-for-user' || value === 'validating' || value === 'blocked' || value === 'failed' || value === 'completed' || value === 'cleaned') return value;
  return 'idle';
}
function backendErrorMessage(raw: RawSovereignAgentJobResponse): string | undefined {
  const value = raw as RawSovereignAgentJobResponse & Record<string, unknown>;
  const preparation = isObject(value.draftPrPreparation) ? value.draftPrPreparation : undefined;
  const creation = isObject(value.draftPrCreate) ? value.draftPrCreate : undefined;
  const preparationBlockers = preparation ? stringArray(preparation.blockers) : [];
  return stringValue(raw.error)
    || stringValue(raw.message)
    || stringValue(raw.details)
    || stringValue(raw.blocker)
    || stringValue(raw.lastError)
    || (preparationBlockers.length ? preparationBlockers.join('; ') : undefined)
    || (creation ? stringValue(creation.blocker) || stringValue(creation.summary) : undefined)
    || (preparation ? stringValue(preparation.summary) : undefined);
}
function unwrapJobPayload(raw: Record<string, unknown>): RawSovereignAgentJobResponse {
  return isObject(raw.job) ? raw.job as RawSovereignAgentJobResponse : raw as RawSovereignAgentJobResponse;
}
function sanitizeSnapshot(rawInput: RawSovereignAgentJobResponse, now: () => number): SovereignAgentJobSnapshot {
  const raw = unwrapJobPayload(rawInput as Record<string, unknown>);
  const workspaceId = stringValue(raw.workspaceId);
  return {
    jobId: stringValue(raw.jobId) || stringValue(raw.id),
    runtimeId: stringValue(raw.runtimeId) || workspaceId,
    workspaceId,
    status: normalizeStatus(raw.status),
    repoUrl: stringValue(raw.repoUrl),
    branch: stringValue(raw.branch),
    branchName: stringValue(raw.branchName),
    draftPrUrl: stringValue(raw.draftPrUrl),
    changedFiles: stringArray(raw.changedFiles),
    events: eventArray(raw.events, now),
    lastError: stringValue(raw.lastError) || backendErrorMessage(raw),
  };
}
async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text.trim()) return {};
  return JSON.parse(text);
}
function assertReady(config: SovereignAgentConfig): void { if (!config.ready) throw new Error(config.reason); }
function jobPath(jobId?: string, suffix = ''): string {
  const base = jobId ? `/api/user/agent/jobs/${encodeURIComponent(jobId.trim())}` : '/api/user/agent/jobs';
  return `${base}${suffix}`;
}
function headers(): HeadersInit { return { 'Content-Type': 'application/json', Accept: 'application/json' }; }
async function requestSnapshot(args: { url: string; init: RequestInit; fetcher: typeof fetch; now: () => number }): Promise<SovereignAgentJobSnapshot> {
  const response = await args.fetcher(args.url, args.init);
  const body = await readJson(response);
  if (!response.ok) {
    throw buildSovereignAgentHttpError({ status: response.status, body, fallback: 'Sovereign Agent backend' });
  }
  if (!isObject(body)) throw new Error('Sovereign Agent backend returned a non-object response.');
  return sanitizeSnapshot(body, args.now);
}

async function requestObject(args: { url: string; init: RequestInit; fetcher: typeof fetch; fallback: string }): Promise<Record<string, unknown>> {
  const response = await args.fetcher(args.url, args.init);
  const body = await readJson(response);
  if (!response.ok) {
    throw buildSovereignAgentHttpError({ status: response.status, body, fallback: args.fallback });
  }
  if (!isObject(body)) throw new Error(`${args.fallback} returned a non-object response.`);
  return body;
}

function patternLearningEvidence(body: Record<string, unknown>): SovereignPatternLearningEvidence | undefined {
  const pattern = isObject(body.patternLearning) ? body.patternLearning : undefined;
  const vector = isObject(body.vectorMemory) ? body.vectorMemory : undefined;
  const candidateId = stringValue(body.candidateId);
  if (!pattern && !vector && !candidateId) return undefined;
  const vectorStorage = stringValue(vector?.storage);
  const vectorReason = stringValue(vector?.reason);
  return {
    candidateCreated: body.candidateCreated === true,
    allowed: pattern?.allowed === true,
    decision: stringValue(pattern?.decision) || 'blocked',
    vectorStored: vector?.stored === true,
    ...(candidateId ? { candidateId } : {}),
    ...(vectorStorage ? { vectorStorage } : {}),
    ...(vectorReason ? { vectorReason } : {}),
  };
}

function diagnosisValue(value: unknown): SovereignToolchainDiagnosis {
  const raw = isObject(value) ? value : {};
  const families = Array.isArray(raw.failureFamilies)
    ? raw.failureFamilies.filter(isObject).map((item): SovereignToolchainFailureFamily => ({
        code: stringValue(item.code) || 'unknown',
        title: stringValue(item.title) || 'Unknown failure family',
        severity: stringValue(item.severity) || 'unknown',
        score: typeof item.score === 'number' && Number.isFinite(item.score) ? item.score : 0,
        checks: stringArray(item.checks),
      }))
    : [];
  const followups = Array.isArray(raw.nextLogicalFailures)
    ? raw.nextLogicalFailures.filter(isObject).map((item): SovereignToolchainFollowup => ({
        fromFamily: stringValue(item.fromFamily) || 'runtime_state_neighbour',
        prediction: stringValue(item.prediction) || 'Unknown neighbouring runtime risk.',
        checkNext: stringValue(item.checkNext) || 'verify runtime evidence',
      }))
    : [];
  return {
    evidenceHash: stringValue(raw.evidenceHash),
    failureFamilies: families,
    nextLogicalFailures: followups,
  };
}

function toolchainEvents(diagnosis: SovereignToolchainDiagnosis, now: () => number): SovereignAgentRuntimeEvent[] {
  const familySummary = diagnosis.failureFamilies.length
    ? diagnosis.failureFamilies.map((item) => item.code).join(', ')
    : 'no known family matched';
  return [
    {
      at: now(),
      level: 'success',
      stage: 'toolchain_diagnosis_completed',
      message: `Universal Toolchain diagnosis: ${familySummary}.`,
    },
    ...diagnosis.nextLogicalFailures.slice(0, 4).map((item, index): SovereignAgentRuntimeEvent => ({
      at: now(),
      level: 'info',
      stage: 'toolchain_predictive_handoff',
      message: `${index + 1}. ${item.prediction} Next check: ${item.checkNext}`,
    })),
  ];
}

async function requestJanitorTool(args: { url: string; init: RequestInit; fetcher: typeof fetch }): Promise<SovereignJanitorToolResponse> {
  const response = await args.fetcher(args.url, args.init);
  const body = await readJson(response);
  if (!response.ok) {
    throw buildSovereignAgentHttpError({ status: response.status, body, fallback: 'Sovereign Janitor' });
  }
  if (!isObject(body) || !isObject(body.tool)) throw new Error('Sovereign Janitor returned an invalid response.');
  const tool = body.tool;
  return {
    ok: body.ok === true,
    jobId: stringValue(body.jobId) || '',
    tool: {
      status: stringValue(tool.status) || 'error',
      output: stringValue(tool.stdout) || stringValue(tool.output),
      blocker: stringValue(tool.blocker),
      changedFiles: stringArray(tool.changedFiles),
      diffSummary: stringValue(tool.diffSummary),
      testSummary: stringValue(tool.testSummary),
      metadata: isObject(tool.metadata) ? tool.metadata : {},
      evidenceGate: tool.evidenceGate,
    },
  };
}

function draftPrCiState(value: unknown): SovereignDraftPrCiState | undefined {
  return value === 'none' || value === 'pending' || value === 'success' || value === 'failure' ? value : undefined;
}

function isCommitSha(value: string | undefined): value is string {
  return Boolean(value && /^[0-9a-f]{40}$/.test(value));
}

function isGithubPullRequestUrl(value: string | undefined): value is string {
  return Boolean(value && /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/[1-9][0-9]*$/.test(value));
}

export class SovereignAgentClient {
  private readonly config: SovereignAgentConfig;
  private readonly fetcher: typeof fetch;
  private readonly now: () => number;
  constructor(options: SovereignAgentClientOptions = {}) {
    this.config = options.config ?? resolveSovereignAgentConfig();
    this.fetcher = options.fetcher ?? globalThis.fetch.bind(globalThis);
    this.now = options.now ?? Date.now;
  }
  getConfig(): SovereignAgentConfig { return this.config; }
  buildJobRequest(input: SovereignAgentStartJobInput): SovereignAgentJobRequest { return buildSovereignAgentJobRequest(input); }
  async startJob(input: SovereignAgentStartJobInput): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    const job = this.buildJobRequest(input);
    const snapshot = await requestSnapshot({
      url: endpoint(this.config.agentApiUrl, jobPath()),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify({
          ...job,
          provisionWorkspace: input.provisionWorkspace ?? true,
          cloneRepo: input.cloneRepo ?? true,
          ...(input.expectedHeadSha?.trim() ? { expectedHeadSha: input.expectedHeadSha.trim() } : {}),
          ...(input.stagedFiles?.length ? { stagedFiles: input.stagedFiles } : {}),
          ...(input.testCommand?.trim() ? { testCommand: input.testCommand.trim() } : {}),
          ...(input.githubAccessToken?.trim() ? { githubAccessToken: input.githubAccessToken.trim() } : {}),
        }),
      },
      fetcher: this.fetcher,
      now: this.now,
    });
    return { ...snapshot, repoUrl: snapshot.repoUrl ?? job.repoUrl, branch: snapshot.branch ?? job.branch };
  }
  async startToolchainJob(input: SovereignToolchainStartJobInput): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    const job = this.buildJobRequest(input);
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, '/api/user/agent/toolchain/handoff'),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify({
          ...job,
          evidenceText: input.evidenceText || '',
          provisionWorkspace: input.provisionWorkspace ?? true,
          cloneRepo: input.cloneRepo ?? true,
          ...(input.expectedHeadSha?.trim() ? { expectedHeadSha: input.expectedHeadSha.trim() } : {}),
          ...(input.stagedFiles?.length ? { stagedFiles: input.stagedFiles } : {}),
          ...(input.testCommand?.trim() ? { testCommand: input.testCommand.trim() } : {}),
          ...(input.githubAccessToken?.trim() ? { githubAccessToken: input.githubAccessToken.trim() } : {}),
        }),
      },
      fetcher: this.fetcher,
      fallback: 'Sovereign Universal Toolchain handoff',
    });
    const snapshot = sanitizeSnapshot(isObject(body.job) ? body.job : body, this.now);
    const diagnosis = diagnosisValue(body.toolchain);
    return {
      ...snapshot,
      repoUrl: snapshot.repoUrl ?? job.repoUrl,
      branch: snapshot.branch ?? job.branch,
      events: [...toolchainEvents(diagnosis, this.now), ...snapshot.events],
    };
  }

  async startRepositoryExecution(input: SovereignRepositoryExecutionInput): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, '/api/user/agent/swarm/run'),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify({
          mission: input.mission.trim(),
          evidenceText: input.evidenceText || '',
          mode: 'auto',
          intentMode: 'repository_execution',
          repositoryUrl: input.repoUrl,
          repositoryBranch: input.branch || 'main',
          ...(input.expectedHeadSha?.trim() ? { expectedHeadSha: input.expectedHeadSha.trim() } : {}),
          ...(input.githubAccessToken?.trim() ? { githubAccessToken: input.githubAccessToken.trim() } : {}),
        }),
      },
      fetcher: this.fetcher,
      fallback: 'Sovereign repository execution',
    });
    const jobId = stringValue(body.jobId);
    if (!jobId) throw new Error('Sovereign repository execution returned no linked job id.');
    const snapshot = await this.getJob(jobId);
    return {
      ...snapshot,
      repoUrl: snapshot.repoUrl ?? input.repoUrl,
      branch: snapshot.branch ?? input.branch ?? 'main',
    };
  }

  async listJobs(): Promise<SovereignAgentJobSnapshot[]> {
    assertReady(this.config);
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, '/api/user/agent/jobs?limit=20'),
      init: { method: 'GET', headers: headers(), credentials: 'include' },
      fetcher: this.fetcher,
      fallback: 'Sovereign Agent job list',
    });
    const jobs = Array.isArray(body.jobs) ? body.jobs : [];
    return jobs.filter(isObject).map((job) => sanitizeSnapshot(job, this.now));
  }
  async getJob(jobId: string): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    return requestSnapshot({ url: endpoint(this.config.agentApiUrl, jobPath(jobId)), init: { method: 'GET', headers: headers(), credentials: 'include' }, fetcher: this.fetcher, now: this.now });
  }
  async getProjections(jobId: string): Promise<SovereignLiveProjection[]> {
    assertReady(this.config);
    const requestedJobId = jobId.trim();
    if (!requestedJobId) throw new Error('Sovereign Agent job id is required.');
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, jobPath(requestedJobId, '/projections?limit=100')),
      init: { method: 'GET', headers: headers(), credentials: 'include' },
      fetcher: this.fetcher,
      fallback: 'Sovereign Live Workspace projections',
    });
    const responseJobId = stringValue(body.jobId);
    const responseWorkspaceId = stringValue(body.workspaceId);
    const responseSessionBindingHash = stringValue(body.sessionBindingHash)?.toLowerCase();
    const responseAttemptId = stringValue(body.attemptId);
    const responseProjections = Array.isArray(body.projections) ? body.projections : [];
    if (responseJobId !== requestedJobId || !responseWorkspaceId) {
      throw new Error('Sovereign Live Workspace projections returned no exact job/workspace envelope binding.');
    }
    if (responseProjections.length === 0) return [];
    if (!responseSessionBindingHash || !SHA256_RE.test(responseSessionBindingHash) || !responseAttemptId) {
      throw new Error('Sovereign Live Workspace projections returned no exact session/attempt envelope binding.');
    }
    return projectionArray(responseProjections, {
      jobId: responseJobId,
      workspaceId: responseWorkspaceId,
      sessionBindingHash: responseSessionBindingHash,
      attemptId: responseAttemptId,
    });
  }
  async getDesktopFrame(jobId: string): Promise<SovereignDesktopFrameObservation> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    const response = await this.fetcher(
      endpoint(this.config.agentApiUrl, jobPath(jobId, '/live-workspace/desktop/frame')),
      {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'image/png' },
        cache: 'no-store',
      },
    );
    if (!response.ok) {
      let body: unknown = {};
      try { body = await readJson(response.clone()); } catch { body = {}; }
      throw buildSovereignAgentHttpError({
        status: response.status,
        body,
        fallback: 'Sovereign Live Desktop frame',
      });
    }
    const observation = response.headers.get('X-Sovereign-Observation')?.trim();
    const frameHash = response.headers.get('X-Sovereign-Frame-Hash')?.trim().toLowerCase() ?? '';
    const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
    if (observation !== 'OBSERVED' || !SHA256_RE.test(frameHash) || !contentType.includes('image/png')) {
      throw new Error('Sovereign Live Desktop frame returned no valid OBSERVED PNG/hash evidence.');
    }
    const blob = await response.blob();
    if (blob.size <= 0 || (blob.type && !blob.type.toLowerCase().includes('image/png'))) {
      throw new Error('Sovereign Live Desktop frame is empty or not PNG.');
    }
    return { blob, frameHash, observedAt: this.now() };
  }
  async getEvidenceAnchors(jobId: string): Promise<SovereignWorkspaceEvidenceAnchor[]> {
    assertReady(this.config);
    const requestedJobId = jobId.trim();
    if (!requestedJobId) throw new Error('Sovereign Agent job id is required.');
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, jobPath(requestedJobId, '/evidence-anchors?limit=100')),
      init: { method: 'GET', headers: headers(), credentials: 'include' },
      fetcher: this.fetcher,
      fallback: 'Sovereign Live Workspace evidence anchors',
    });
    const responseJobId = stringValue(body.jobId);
    const responseWorkspaceId = stringValue(body.workspaceId);
    const responseSessionBindingHash = stringValue(body.sessionBindingHash)?.toLowerCase();
    const responseAttemptId = stringValue(body.attemptId);
    const responseActive = typeof body.active === 'boolean' ? body.active : undefined;
    const responseAnchors = Array.isArray(body.evidenceAnchors) ? body.evidenceAnchors : [];
    if (responseJobId !== requestedJobId || !responseWorkspaceId) {
      throw new Error('Sovereign Live Workspace evidence returned no exact job/workspace envelope binding.');
    }
    if (responseAnchors.length === 0) return [];
    if (!responseSessionBindingHash || !SHA256_RE.test(responseSessionBindingHash) || !responseAttemptId || responseActive === undefined) {
      throw new Error('Sovereign Live Workspace evidence returned no exact session/attempt envelope binding.');
    }
    const anchors = evidenceAnchorArray(responseAnchors, {
      jobId: responseJobId,
      workspaceId: responseWorkspaceId,
      sessionBindingHash: responseSessionBindingHash,
      attemptId: responseAttemptId,
    });
    if (responseActive === false && anchors.some((anchor) => (
      anchor.verdict !== 'STALE' || !anchor.freshnessReasons.includes('SESSION_NOT_ACTIVE')
    ))) {
      throw new Error('Sovereign Live Workspace inactive evidence was not explicitly marked STALE.');
    }
    return anchors;
  }
  async cancelJob(jobId: string): Promise<SovereignAgentJobSnapshot> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    return requestSnapshot({ url: endpoint(this.config.agentApiUrl, jobPath(jobId, '/cancel')), init: { method: 'POST', headers: headers(), credentials: 'include' }, fetcher: this.fetcher, now: this.now });
  }
  async prepareDraftPr(jobId: string, headBranch?: string): Promise<SovereignDraftPrPreparationResponse> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, jobPath(jobId, '/draft-pr/prepare')),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify(headBranch ? { headBranch } : {}),
      },
      fetcher: this.fetcher,
      fallback: 'Sovereign Draft PR preparation',
    });
    const signal = isObject(body.draftPrPreparation) ? body.draftPrPreparation : {};
    return {
      ok: body.ok === true,
      jobId: stringValue(body.jobId) || jobId,
      draftPrPreparation: {
        allowed: signal.allowed === true,
        decision: stringValue(signal.decision) || 'blocked',
        summary: stringValue(signal.summary),
        headBranch: stringValue(signal.headBranch),
        baseBranch: stringValue(signal.baseBranch),
        nextAction: stringValue(signal.nextAction),
        canCreateDraftPr: signal.canCreateDraftPr === true,
        blockers: stringArray(signal.blockers),
      },
      learningEvidence: patternLearningEvidence(body),
    };
  }
  async createDraftPr(jobId: string, githubAccessToken?: string): Promise<SovereignDraftPrCreateResponse> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    const token = githubAccessToken?.trim();
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, jobPath(jobId, '/draft-pr/create')),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify(token ? { githubAccessToken: token } : {}),
      },
      fetcher: this.fetcher,
      fallback: 'Sovereign Draft PR create',
    });
    const signal = isObject(body.draftPrCreate) ? body.draftPrCreate : {};
    const prUrl = stringValue(signal.prUrl);
    const headSha = stringValue(signal.headSha);
    const publishedHeadSha = stringValue(signal.publishedHeadSha);
    const readbackHeadSha = stringValue(signal.readbackHeadSha);
    const prNumber = integerValue(signal.prNumber);
    const headBranch = stringValue(signal.headBranch);
    const baseBranch = stringValue(signal.baseBranch);
    const ciState = draftPrCiState(signal.ciState);
    const checkRunCount = integerValue(signal.checkRunCount);
    const checksPendingCount = integerValue(signal.checksPendingCount);
    const checksSuccessCount = integerValue(signal.checksSuccessCount);
    const checksFailureCount = integerValue(signal.checksFailureCount);
    const statusContextCount = integerValue(signal.statusContextCount);
    const verified = (
      body.ok === true
      && signal.allowed === true
      && stringValue(signal.status) === 'created'
      && isGithubPullRequestUrl(prUrl)
      && isCommitSha(headSha)
      && isCommitSha(publishedHeadSha)
      && isCommitSha(readbackHeadSha)
      && headSha === readbackHeadSha
      && publishedHeadSha === readbackHeadSha
      && typeof prNumber === 'number'
      && prNumber > 0
      && signal.draftVerified === true
      && stringValue(signal.prStateVerified) === 'open'
      && Boolean(headBranch)
      && Boolean(baseBranch)
      && signal.readbackVerified === true
      && signal.checksReadbackVerified === true
      && Boolean(ciState)
      && typeof checkRunCount === 'number'
      && typeof checksPendingCount === 'number'
      && typeof checksSuccessCount === 'number'
      && typeof checksFailureCount === 'number'
      && typeof statusContextCount === 'number'
      && checksPendingCount + checksSuccessCount + checksFailureCount === checkRunCount
    );
    if (!verified) {
      throw new Error(
        stringValue(signal.blocker)
          || 'Sovereign Draft PR create returned no complete GitHub Draft-PR/head-SHA/check readback evidence.',
      );
    }
    return {
      ok: true,
      jobId: stringValue(body.jobId) || jobId,
      draftPrCreate: {
        allowed: true,
        status: 'created',
        prUrl,
        headSha,
        publishedHeadSha,
        readbackHeadSha,
        prNumber,
        draftVerified: true,
        prStateVerified: 'open',
        headBranch,
        baseBranch,
        readbackVerified: true,
        checksReadbackVerified: true,
        ciState,
        checkRunCount,
        checksPendingCount,
        checksSuccessCount,
        checksFailureCount,
        statusContextCount,
        blocker: stringValue(signal.blocker),
        summary: stringValue(signal.summary),
      },
    };
  }
  async runJanitor(jobId: string, input: SovereignJanitorInput = {}): Promise<SovereignJanitorToolResponse> {
    assertReady(this.config);
    if (!jobId.trim()) throw new Error('Sovereign Agent job id is required.');
    return requestJanitorTool({
      url: endpoint(this.config.agentApiUrl, jobPath(jobId, '/tools/janitor')),
      init: { method: 'POST', headers: headers(), credentials: 'include', body: JSON.stringify(input) },
      fetcher: this.fetcher,
    });
  }
}
export function createSovereignAgentClient(options: SovereignAgentClientOptions = {}): SovereignAgentClient { return new SovereignAgentClient(options); }
