import {
  resolveSovereignAgentConfig,
  type SovereignAgentConfig,
} from '../../product/runtime/sovereignAgentRuntime';
import type { AgentMode, Skill } from '../types/domain';
import type { RestoredRepositoryRun } from './interface';
import {
  extractGitHubRepositoryUrl,
  SovereignProductionAdapter as SovereignProductionAdapterBase,
} from './production-adapter';

type JsonRecord = Record<string, unknown>;

function endpoint(baseUrl: string, route: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/${route.replace(/^\/+/, '')}`;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

const RESUMABLE_REPOSITORY_STATUSES = new Set(['running', 'validating']);

function isResumableRepositoryRun(candidate: JsonRecord): boolean {
  const status = stringValue(candidate.status)?.toLowerCase();
  const workspaceId = stringValue(candidate.workspaceId);
  const externalRef = stringValue(candidate.externalRef);
  return Boolean(
    status
    && RESUMABLE_REPOSITORY_STATUSES.has(status)
    && workspaceId
    && externalRef?.startsWith('agent-zero-a2a:'),
  );
}

export function buildRepositoryBoundRunRequest(
  mission: string,
  agentMode: AgentMode = 'single',
  expectedHeadSha?: string,
): JsonRecord {
  const normalizedMission = mission.trim();
  if (!normalizedMission) throw new Error('Mission text is required.');
  if (agentMode !== 'single') {
    throw new Error('The vNext Draft-PR path currently requires one Free single agent.');
  }
  const explicitRepositoryUrl = extractGitHubRepositoryUrl(normalizedMission);
  const normalizedExpectedHeadSha = expectedHeadSha?.trim().toLowerCase();
  if (!/^[0-9a-f]{40}$/.test(normalizedExpectedHeadSha || '')) {
    throw new Error('Repository execution requires an exact expected repository HEAD SHA.');
  }
  return {
    mission: normalizedMission,
    mode: 'free',
    agentMode: 'single',
    intentMode: 'repository_execution',
    repositoryBranch: 'main',
    ...(normalizedExpectedHeadSha ? { expectedHeadSha: normalizedExpectedHeadSha } : {}),
    ...(explicitRepositoryUrl ? { repositoryUrl: explicitRepositoryUrl } : {}),
  };
}

/**
 * The single vNext production adapter.
 *
 * It inherits the existing live HTTP truth boundary and narrows only mission
 * policy: this product surface is repository/Draft-PR first, so repository
 * capability comes from product/server context rather than from whether the user
 * repeats a GitHub URL in prose. An explicit GitHub URL remains a bounded target
 * override; otherwise the backend resolves its configured Sovereign repository.
 */
export class SovereignProductionAdapter extends SovereignProductionAdapterBase {
  private readonly repositoryConfig: SovereignAgentConfig;
  private readonly repositoryFetcher: typeof fetch;

  constructor(
    fetcher: typeof fetch = globalThis.fetch.bind(globalThis),
    config: SovereignAgentConfig = resolveSovereignAgentConfig(),
  ) {
    super(fetcher, config);
    this.repositoryFetcher = fetcher;
    this.repositoryConfig = config;
  }

  override async checkHealth(): Promise<{ status: string; latencyMs: number }> {
    if (!this.repositoryConfig.ready) return { status: 'blocked', latencyMs: 0 };
    const startedAt = performance.now();
    try {
      const response = await this.repositoryFetcher(
        endpoint(this.repositoryConfig.agentApiUrl, '/api/user/agent/jobs?limit=1'),
        { method: 'GET', credentials: 'include', headers: { Accept: 'application/json' }, cache: 'no-store' },
      );
      return {
        status: response.ok ? 'ready' : 'blocked',
        latencyMs: Math.round(performance.now() - startedAt),
      };
    } catch {
      return { status: 'blocked', latencyMs: Math.round(performance.now() - startedAt) };
    }
  }

  override async getSkills(): Promise<Skill[]> {
    // Repository execution has no Swarm worker graph. An empty projection is
    // preferable to inventing worker capabilities from a Swarm manifest.
    return [];
  }

  override async restoreLatestRepositoryRun(): Promise<RestoredRepositoryRun | null> {
    if (!this.repositoryConfig.ready) return null;
    const response = await this.repositoryFetcher(
      endpoint(this.repositoryConfig.agentApiUrl, '/api/user/agent/jobs?limit=20'),
      {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      },
    );
    if (!response.ok) {
      throw new Error(`Repository session readback failed with HTTP ${response.status}.`);
    }
    const body: unknown = await response.json().catch(() => null);
    if (!isRecord(body) || !Array.isArray(body.jobs)) {
      throw new Error('Repository session readback returned an invalid jobs payload.');
    }
    for (const candidate of body.jobs) {
      if (!isRecord(candidate)) continue;
      const jobId = stringValue(candidate.jobId);
      const repoUrl = stringValue(candidate.repoUrl);
      if (!jobId || !repoUrl || !isResumableRepositoryRun(candidate)) continue;
      return {
        jobId,
        mission: stringValue(candidate.mission),
        status: stringValue(candidate.status),
        repoUrl,
        branch: stringValue(candidate.branch),
      };
    }
    return null;
  }

  private async getRepositoryHeadSnapshot(mission: string): Promise<{ headSha: string }> {
    const repositoryUrl = extractGitHubRepositoryUrl(mission);
    const response = await this.repositoryFetcher(
      endpoint(this.repositoryConfig.agentApiUrl, '/api/user/agent/repository/head'),
      {
        method: 'POST',
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...(repositoryUrl ? { repository: repositoryUrl } : {}),
          branch: 'main',
        }),
      },
    );
    const body: unknown = await response.json().catch(() => null);
    const record = isRecord(body) ? body : {};
    const headSha = stringValue(record.headSha)?.toLowerCase();
    if (!response.ok || !headSha || !/^[0-9a-f]{40}$/.test(headSha)) {
      const reason = stringValue(record.error) || stringValue(record.code);
      throw new Error(reason || `Repository HEAD readback failed with HTTP ${response.status}.`);
    }
    return { headSha };
  }

  override async runSwarm(
    prompt: string,
    _toolchains: string[],
    _activeSkillIds: string[] = [],
    agentMode: AgentMode = 'single',
  ): Promise<{ jobId: string }> {
    if (!this.repositoryConfig.ready) throw new Error(this.repositoryConfig.reason);
    const snapshot = await this.getRepositoryHeadSnapshot(prompt);
    const payload = buildRepositoryBoundRunRequest(prompt, agentMode, snapshot.headSha);
    const response = await this.repositoryFetcher(
      endpoint(this.repositoryConfig.agentApiUrl, '/api/user/agent/repository/run'),
      {
        method: 'POST',
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      },
    );
    const body: unknown = await response.json().catch(() => null);
    const record = isRecord(body) ? body : {};
    const nestedJob = isRecord(record.job) ? record.job : undefined;
    const jobId = stringValue(record.jobId) || stringValue(nestedJob?.jobId);
    if (jobId) return { jobId };
    const reason = stringValue(record.reason)
      || stringValue(record.error)
      || stringValue(record.blocker);
    throw new Error(reason || `Sovereign repository execution failed with HTTP ${response.status}.`);
  }
}
