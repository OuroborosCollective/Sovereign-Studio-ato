import {
  createSovereignAgentClient,
  type SovereignDraftPrCreateResponse,
} from '../../product/runtime/sovereignAgentClient';
import {
  resolveSovereignAgentConfig,
  type SovereignAgentJobSnapshot,
  type SovereignWorkspaceEvidenceAnchor,
} from '../../product/runtime/sovereignAgentRuntime';
import type {
  DraftPR,
  DraftPrPreparation,
  IntegrationAttachment,
  JobPhase,
  Skill,
  SovereignJob,
  Toolchain,
} from '../types/domain';
import type { AdapterStatus, SovereignBackendAdapter } from './interface';
import { projectRunAndJobPhase } from '../fsm/runtimePhaseProjection';

type JsonRecord = Record<string, unknown>;

interface PersistedRun {
  runId: string;
  jobId?: string;
  status: string;
  source?: string;
  evidenceId?: string;
  traceId?: string;
  reason?: string;
  nextAction?: string;
  missionSummary?: string;
  iterationCount?: number;
  maxIterations?: number;
  leaseActive?: boolean;
  resumeAvailable?: boolean;
}

interface PendingApproval {
  approvalId: string;
  runId: string;
  kind: string;
  reason: string;
  nextAction?: string;
  requiresProtectedOwnerInput: boolean;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null;
}
function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}
function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}
function boolValue(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}
function endpoint(baseUrl: string, route: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/${route.replace(/^\/+/, '')}`;
}

export function extractGitHubRepositoryUrl(mission: string): string | undefined {
  const candidates = mission.match(/https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+/gi) ?? [];
  for (const candidate of candidates) {
    const cleaned = candidate.replace(/[),.;!?]+$/g, '').replace(/\.git$/i, '');
    try {
      const parsed = new URL(cleaned);
      const segments = parsed.pathname.split('/').filter(Boolean);
      if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || segments.length !== 2) continue;
      return `https://github.com/${segments[0]}/${segments[1]}`;
    } catch {
      // Keep searching; a malformed URL never changes the execution intent.
    }
  }
  return undefined;
}

function parseRun(value: unknown): PersistedRun {
  if (!isRecord(value)) throw new Error('Sovereign run readback returned no object.');
  const runId = stringValue(value.runId);
  const status = stringValue(value.status);
  if (!runId || !status) throw new Error('Sovereign run readback lacks runId/status evidence.');
  return {
    runId,
    jobId: stringValue(value.jobId),
    status,
    source: stringValue(value.source),
    evidenceId: stringValue(value.evidenceId),
    traceId: stringValue(value.traceId),
    reason: stringValue(value.reason),
    nextAction: stringValue(value.nextAction),
    missionSummary: stringValue(value.missionSummary),
    iterationCount: numberValue(value.iterationCount),
    maxIterations: numberValue(value.maxIterations),
    leaseActive: boolValue(value.leaseActive),
    resumeAvailable: boolValue(value.resumeAvailable),
  };
}

function parsePendingApproval(value: unknown): PendingApproval | undefined {
  if (!isRecord(value)) return undefined;
  const approvalId = stringValue(value.approval_id) || stringValue(value.approvalId);
  const runId = stringValue(value.run_id) || stringValue(value.runId);
  const kind = stringValue(value.kind);
  const reason = stringValue(value.reason);
  if (!approvalId || !runId || !kind || !reason) return undefined;
  return {
    approvalId,
    runId,
    kind,
    reason,
    nextAction: stringValue(value.next_action) || stringValue(value.nextAction),
    requiresProtectedOwnerInput: value.requiresProtectedOwnerInput === true || value.requires_protected_owner_input === true,
  };
}

function phaseFromRun(status: string): JobPhase {
  switch (status.toUpperCase()) {
    case 'RECEIVED': return 'DISPATCHING';
    case 'QUEUED': return 'DISPATCHING';
    case 'RUNNING': return 'EXECUTING';
    case 'WAITING_FOR_OWNER': return 'AWAITING_OWNER_INPUT';
    case 'READY_FOR_DRAFT_PR': return 'READY_TO_PUBLISH';
    case 'BLOCKED':
    case 'FAILED_RECOVERABLE': return 'BLOCKED';
    case 'FAILED_FINAL': return 'FAILED';
    case 'SUCCEEDED':
    case 'COMPLETED': return 'COMPLETED';
    case 'CANCELLED': return 'CANCELLED';
    default: return 'DISPATCHING';
  }
}

function phaseFromJob(snapshot: SovereignAgentJobSnapshot, run: PersistedRun): JobPhase {
  switch (snapshot.status) {
    case 'idle': return phaseFromRun(run.status);
    case 'queued': return 'DISPATCHING';
    case 'provisioning': return 'PROVISIONING';
    case 'running': return 'EXECUTING';
    case 'waiting-for-user': return 'AWAITING_OWNER_INPUT';
    case 'validating': return 'FINALIZING';
    case 'blocked': return 'BLOCKED';
    case 'failed': return 'FAILED';
    case 'completed':
    case 'cleaned':
      return snapshot.changedFiles.length > 0 ? 'READY_TO_PUBLISH' : 'COMPLETED';
    default: return phaseFromRun(run.status);
  }
}

function eventLogs(snapshot: SovereignAgentJobSnapshot | undefined, run: PersistedRun): string[] {
  const logs: string[] = [];
  logs.push(`[RUN ${run.runId}] ${run.status}${run.source ? ` · ${run.source}` : ''}`);
  if (run.reason) logs.push(`STATE: ${run.reason}`);
  if (run.nextAction) logs.push(`NEXT: ${run.nextAction}`);
  for (const event of snapshot?.events ?? []) {
    const at = new Date(event.at).toISOString();
    logs.push(`${at} [${event.level.toUpperCase()}] ${event.stage}: ${event.message}`);
  }
  if (snapshot?.draftPrUrl) {
    logs.push(`OBSERVED: backend job reports Draft PR URL ${snapshot.draftPrUrl}; full GitHub verification is shown only after strict publication readback.`);
  }
  return logs;
}

function newestEvidenceRevision(anchors: readonly SovereignWorkspaceEvidenceAnchor[]): string {
  const sorted = [...anchors]
    .filter((item) => /^[0-9a-f]{40}$/.test(item.repositoryRevision))
    .sort((a, b) => Date.parse(b.observedAt) - Date.parse(a.observedAt));
  return sorted[0]?.repositoryRevision ?? '';
}

function mapDraftPr(response: SovereignDraftPrCreateResponse): DraftPR {
  const pr = response.draftPrCreate;
  return {
    url: pr.prUrl,
    revision: pr.readbackHeadSha,
    pullRequestNumber: pr.prNumber,
    branch: pr.headBranch,
    baseBranch: pr.baseBranch,
    verifiedRevisionHash: pr.readbackHeadSha,
    publishedHeadSha: pr.publishedHeadSha,
    readbackHeadSha: pr.readbackHeadSha,
    ciState: pr.ciState,
    draftVerified: true,
    readbackVerified: true,
    checksReadbackVerified: true,
    checkRunCount: pr.checkRunCount,
    checksPendingCount: pr.checksPendingCount,
    checksSuccessCount: pr.checksSuccessCount,
    checksFailureCount: pr.checksFailureCount,
    statusContextCount: pr.statusContextCount,
    timestamp: new Date().toISOString(),
  };
}

export class SovereignProductionAdapter implements SovereignBackendAdapter {
  private readonly config: ReturnType<typeof resolveSovereignAgentConfig>;
  private readonly client: ReturnType<typeof createSovereignAgentClient>;
  private readonly fetcher: typeof fetch;
  private readonly publications = new Map<string, DraftPR>();
  private lastPingMs?: number;
  private lastErrorMessage?: string;

  constructor(fetcher: typeof fetch = globalThis.fetch.bind(globalThis)) {
    this.fetcher = fetcher;
    this.config = resolveSovereignAgentConfig();
    this.client = createSovereignAgentClient({ config: this.config, fetcher });
  }

  getStatus(): AdapterStatus {
    return {
      mode: 'live_http',
      backendUrl: this.config.agentApiUrl || '(unconfigured)',
      isFallback: false,
      lastPingMs: this.lastPingMs,
      errorMessage: this.lastErrorMessage,
    };
  }

  private assertReady(): void {
    if (!this.config.ready) throw new Error(this.config.reason);
  }

  private async requestObject(route: string, init: RequestInit = {}): Promise<{ body: JsonRecord; status: number; ok: boolean }> {
    this.assertReady();
    const response = await this.fetcher(endpoint(this.config.agentApiUrl, route), {
      ...init,
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers ?? {}),
      },
      cache: init.method === 'GET' || !init.method ? 'no-store' : init.cache,
    });
    const text = await response.text();
    let payload: unknown = {};
    if (text.trim()) {
      try { payload = JSON.parse(text); }
      catch { throw new Error(`Sovereign backend returned non-JSON HTTP ${response.status}.`); }
    }
    if (!isRecord(payload)) throw new Error(`Sovereign backend returned a non-object HTTP ${response.status}.`);
    return { body: payload, status: response.status, ok: response.ok };
  }

  private async getPendingApproval(runId: string): Promise<PendingApproval | undefined> {
    const result = await this.requestObject('/api/controller/approvals', { method: 'GET' });
    if (!result.ok) throw new Error(`Sovereign approval readback HTTP ${result.status}.`);
    const approvals = Array.isArray(result.body.approvals) ? result.body.approvals : [];
    return approvals
      .map(parsePendingApproval)
      .find((approval): approval is PendingApproval => Boolean(approval && approval.runId === runId));
  }

  async checkHealth(): Promise<{ status: string; latencyMs: number }> {
    const startedAt = performance.now();
    try {
      const result = await this.requestObject('/api/user/agent/swarm/manifest', { method: 'GET' });
      if (!result.ok) throw new Error(`Swarm manifest HTTP ${result.status}`);
      const latencyMs = Math.round(performance.now() - startedAt);
      this.lastPingMs = latencyMs;
      this.lastErrorMessage = undefined;
      return { status: 'ready', latencyMs };
    } catch (error) {
      const latencyMs = Math.round(performance.now() - startedAt);
      this.lastPingMs = latencyMs;
      this.lastErrorMessage = error instanceof Error ? error.message : String(error);
      return { status: 'blocked', latencyMs };
    }
  }

  async runSwarm(prompt: string, _toolchains: string[], _activeSkillIds: string[] = []): Promise<{ jobId: string }> {
    const mission = prompt.trim();
    if (!mission) throw new Error('Mission text is required.');
    const repositoryUrl = extractGitHubRepositoryUrl(mission);
    const result = await this.requestObject('/api/user/agent/swarm/run', {
      method: 'POST',
      body: JSON.stringify(repositoryUrl ? {
        mission,
        mode: 'auto',
        intentMode: 'repository_execution',
        repositoryUrl,
        repositoryBranch: 'main',
      } : {
        mission,
        mode: 'auto',
        intentMode: 'auto',
      }),
    });
    const runId = stringValue(result.body.runId);
    if (runId) return { jobId: runId };
    const reason = stringValue(result.body.reason) || stringValue(result.body.error) || stringValue(result.body.blocker);
    throw new Error(reason || `Sovereign swarm start failed with HTTP ${result.status}.`);
  }

  private async getRun(runId: string): Promise<PersistedRun> {
    const requested = runId.trim();
    if (!requested) throw new Error('Run ID is required.');
    const result = await this.requestObject(`/api/user/agent/swarm/runs/${encodeURIComponent(requested)}`, { method: 'GET' });
    if (!result.ok) throw new Error(stringValue(result.body.error) || `Sovereign run readback HTTP ${result.status}.`);
    const run = parseRun(result.body.run);
    if (run.runId !== requested) throw new Error('Sovereign run readback identity mismatch.');
    return run;
  }

  async getJob(runId: string): Promise<SovereignJob> {
    const run = await this.getRun(runId);
    let snapshot: SovereignAgentJobSnapshot | undefined;
    let anchors: SovereignWorkspaceEvidenceAnchor[] = [];
    if (run.jobId) {
      snapshot = await this.client.getJob(run.jobId);
      try { anchors = await this.client.getEvidenceAnchors(run.jobId); } catch { anchors = []; }
    }
    const runPhase = phaseFromRun(run.status);
    const phase = projectRunAndJobPhase(
      runPhase,
      snapshot ? phaseFromJob(snapshot, run) : runPhase,
    );
    const approval = phase === 'AWAITING_OWNER_INPUT'
      ? await this.getPendingApproval(run.runId)
      : undefined;
    const currentRevision = newestEvidenceRevision(anchors);
    const publication = this.publications.get(runId);
    const now = new Date().toISOString();
    const pendingInteraction = phase === 'AWAITING_OWNER_INPUT'
      ? approval
        ? {
            id: approval.approvalId,
            prompt: approval.reason,
            options: approval.requiresProtectedOwnerInput ? undefined : ['approve', 'reject'],
            requiresText: approval.requiresProtectedOwnerInput,
            timestamp: now,
            context: approval.nextAction || run.nextAction || approval.kind,
          }
        : {
            id: run.runId,
            prompt: run.reason || 'Sovereign requires an explicit owner response before the persisted run can continue.',
            options: run.nextAction ? [run.nextAction] : undefined,
            requiresText: true,
            timestamp: now,
            context: run.nextAction,
          }
      : undefined;
    return {
      id: run.runId,
      runId: run.runId,
      backendJobId: run.jobId,
      phase: projectRunAndJobPhase(runPhase, publication ? 'COMPLETED' : phase),
      createdAt: now,
      updatedAt: now,
      sourceStatus: run.status,
      nextAction: run.nextAction,
      logs: eventLogs(snapshot, run),
      workspaceState: {
        modifiedFiles: snapshot?.changedFiles ?? [],
        currentRevision,
        diffStats: snapshot ? { additions: 0, deletions: 0, filesChanged: snapshot.changedFiles.length } : undefined,
      },
      pendingInteraction,
      draftPR: publication,
      publication: publication ? { draftPR: publication } : undefined,
      error: phase === 'BLOCKED' || phase === 'FAILED'
        ? {
            message: (runPhase === 'BLOCKED' || runPhase === 'FAILED' ? run.reason : snapshot?.lastError)
              || run.reason || 'Runtime execution is blocked.',
            code: run.nextAction,
          }
        : undefined,
    };
  }

  async resumeJob(runId: string, interactionId: string, response: string): Promise<void> {
    const evidence = response.trim();
    if (!evidence) throw new Error('Owner response is required.');
    if (interactionId.startsWith('approval-')) {
      const decision = evidence.toLowerCase();
      if (decision !== 'approve' && decision !== 'reject') {
        throw new Error('Approval interactions accept only approve or reject.');
      }
      const result = await this.requestObject(`/api/controller/approvals/${encodeURIComponent(interactionId)}/decision`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      });
      if (!result.ok) {
        throw new Error(stringValue(result.body.error) || stringValue(result.body.blocker) || `Sovereign approval decision HTTP ${result.status}.`);
      }
      const returnedRunId = stringValue(result.body.runId);
      if (returnedRunId && returnedRunId !== runId) throw new Error('Sovereign approval decision returned a mismatched run identity.');
      return;
    }
    const result = await this.requestObject(`/api/user/agent/swarm/runs/${encodeURIComponent(runId)}/resume`, {
      method: 'POST',
      body: JSON.stringify({ evidence, mode: 'auto' }),
    });
    const returnedRunId = stringValue(result.body.runId)
      || (isRecord(result.body.run) ? stringValue(result.body.run.runId) : undefined);
    if (!result.ok && !returnedRunId) {
      throw new Error(stringValue(result.body.reason) || stringValue(result.body.error) || `Sovereign resume HTTP ${result.status}.`);
    }
    if (returnedRunId && returnedRunId !== runId) throw new Error('Sovereign resume returned a mismatched run identity.');
  }

  async abortJob(runId: string): Promise<void> {
    const run = await this.getRun(runId);
    if (!run.jobId) throw new Error('This persisted run has no linked cancellable implementation job.');
    await this.client.cancelJob(run.jobId);
  }

  async prepareDraftPr(runId: string): Promise<DraftPrPreparation> {
    const run = await this.getRun(runId);
    if (!run.jobId) throw new Error('Draft PR preparation requires a linked implementation job.');
    const result = await this.client.prepareDraftPr(run.jobId);
    return {
      allowed: result.draftPrPreparation.allowed && result.draftPrPreparation.canCreateDraftPr !== false,
      decision: result.draftPrPreparation.decision,
      summary: result.draftPrPreparation.summary,
      headBranch: result.draftPrPreparation.headBranch,
      baseBranch: result.draftPrPreparation.baseBranch,
      nextAction: result.draftPrPreparation.nextAction,
      blockers: result.draftPrPreparation.blockers,
    };
  }

  async createDraftPr(runId: string): Promise<DraftPR> {
    const run = await this.getRun(runId);
    if (!run.jobId) throw new Error('Draft PR creation requires a linked implementation job.');
    const prepared = await this.client.prepareDraftPr(run.jobId);
    if (!prepared.ok || !prepared.draftPrPreparation.allowed || prepared.draftPrPreparation.canCreateDraftPr === false) {
      throw new Error(
        prepared.draftPrPreparation.blockers.join('; ')
        || prepared.draftPrPreparation.summary
        || prepared.draftPrPreparation.nextAction
        || 'Draft PR gate did not authorize publication.',
      );
    }
    const created = await this.client.createDraftPr(run.jobId);
    const publication = mapDraftPr(created);
    this.publications.set(runId, publication);
    return publication;
  }

  async getToolchains(): Promise<Toolchain[]> {
    const result = await this.requestObject('/api/user/agent/toolchain/manifest', { method: 'GET' });
    if (!result.ok) throw new Error(`Toolchain manifest HTTP ${result.status}.`);
    const name = stringValue(result.body.name) || 'Sovereign Universal Toolchain';
    const version = stringValue(result.body.version) || 'runtime';
    const policy = isRecord(result.body.policy) ? result.body.policy : {};
    return [{
      id: 'sovereign-universal-toolchain',
      name,
      description: 'Server-owned embedded toolchain. Execution remains in the Sovereign Agent workspace; Draft PR publication is a separate evidence-gated action.',
      status: 'active',
      driver: 'sovereign-agent',
      badge: policy.draftPrOnly === true ? `DRAFT-PR ONLY · ${version}` : version,
    }];
  }

  async getSkills(): Promise<Skill[]> {
    const result = await this.requestObject('/api/user/agent/swarm/manifest', { method: 'GET' });
    if (!result.ok) throw new Error(`Swarm manifest HTTP ${result.status}.`);
    const manifest = isRecord(result.body.manifest) ? result.body.manifest : {};
    const agents = Array.isArray(manifest.agents) ? manifest.agents.filter(isRecord) : [];
    return agents.flatMap((agent): Skill[] => {
      const role = stringValue(agent.role);
      const name = stringValue(agent.name);
      const description = stringValue(agent.responsibility);
      if (!role || !name || !description) return [];
      return [{ id: `agent-${role}`, name, source: 'core', description, tier: 'Sovereign' }];
    });
  }

  async getIntegrations(): Promise<IntegrationAttachment[]> {
    // No guessed integration-list contract. The control surface shows an empty,
    // read-only attachment registry until a real server projection is introduced.
    return [];
  }
}
