import {
  resolveSovereignAgentConfig,
  type SovereignAgentConfig,
} from '../../product/runtime/sovereignAgentRuntime';
import type { AgentMode } from '../types/domain';
import {
  extractGitHubRepositoryUrl,
  SovereignProductionAdapter,
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

export function buildRepositoryBoundRunRequest(
  mission: string,
  agentMode: AgentMode = 'single',
): JsonRecord {
  const normalizedMission = mission.trim();
  if (!normalizedMission) throw new Error('Mission text is required.');
  if (agentMode !== 'single') {
    throw new Error('The vNext Draft-PR path currently requires one Free single agent.');
  }
  const explicitRepositoryUrl = extractGitHubRepositoryUrl(normalizedMission);
  return {
    mission: normalizedMission,
    mode: 'free',
    agentMode: 'single',
    intentMode: 'repository_execution',
    repositoryBranch: 'main',
    ...(explicitRepositoryUrl ? { repositoryUrl: explicitRepositoryUrl } : {}),
  };
}

/**
 * Product-specific vNext adapter.
 *
 * vNext is the repository mission surface. The repository capability therefore
 * comes from product/server context, not from whether the user repeats a GitHub
 * URL in natural-language prose. An explicit GitHub URL remains a bounded
 * override; otherwise the backend resolves its configured Sovereign repository.
 */
export class RepositoryBoundSovereignProductionAdapter extends SovereignProductionAdapter {
  private readonly repositoryConfig: SovereignAgentConfig;
  private readonly repositoryFetcher: typeof fetch;

  constructor(
    fetcher: typeof fetch = globalThis.fetch.bind(globalThis),
    config: SovereignAgentConfig = resolveSovereignAgentConfig(),
  ) {
    super(fetcher);
    this.repositoryFetcher = fetcher;
    this.repositoryConfig = config;
  }

  override async runSwarm(
    prompt: string,
    _toolchains: string[],
    _activeSkillIds: string[] = [],
    agentMode: AgentMode = 'single',
  ): Promise<{ jobId: string }> {
    if (!this.repositoryConfig.ready) throw new Error(this.repositoryConfig.reason);
    const payload = buildRepositoryBoundRunRequest(prompt, agentMode);
    const response = await this.repositoryFetcher(
      endpoint(this.repositoryConfig.agentApiUrl, '/api/user/agent/swarm/run'),
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
    const runId = stringValue(record.runId);
    if (runId) return { jobId: runId };
    const reason = stringValue(record.reason)
      || stringValue(record.error)
      || stringValue(record.blocker);
    throw new Error(reason || `Sovereign repository execution failed with HTTP ${response.status}.`);
  }
}
