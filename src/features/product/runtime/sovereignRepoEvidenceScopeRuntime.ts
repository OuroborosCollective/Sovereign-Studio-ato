import type { DevChatRepoSnapshot } from './devChatWorkerBridge';
import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';

function normalizeRepoUrl(value: string | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    const path = parsed.pathname.replace(/\/+$/, '').replace(/\.git$/i, '');
    if (!parsed.hostname || !path || path === '/') return null;
    return `${parsed.protocol.toLowerCase()}//${parsed.hostname.toLowerCase()}${path.toLowerCase()}`;
  } catch {
    return trimmed.replace(/[?#].*$/, '').replace(/\/+$/, '').replace(/\.git$/i, '').toLowerCase();
  }
}

function normalizeBranch(value: string | undefined): string {
  return value?.trim() || 'main';
}

export function buildRepositoryTargetKey(snapshot: DevChatRepoSnapshot | null): string | null {
  if (!snapshot?.owner?.trim() || !snapshot.repo?.trim()) return null;
  return `${snapshot.owner.trim().toLowerCase()}/${snapshot.repo.trim().toLowerCase()}`;
}

export function buildRepoEvidenceScopeKey(snapshot: DevChatRepoSnapshot | null): string | null {
  const repoUrl = normalizeRepoUrl(snapshot?.repoUrl);
  if (!snapshot || !repoUrl || !snapshot.owner?.trim() || !snapshot.repo?.trim() || !snapshot.branch?.trim()) return null;
  return `${repoUrl}#${normalizeBranch(snapshot.branch)}`;
}

export function buildOpenHandsJobScopeKey(job: OpenHandsJobSnapshot | undefined): string | null {
  const repoUrl = normalizeRepoUrl(job?.repoUrl);
  if (!job || !repoUrl) return null;
  return `${repoUrl}#${normalizeBranch(job.branch)}`;
}

export function isOpenHandsJobScopedToRepo(
  job: OpenHandsJobSnapshot | undefined,
  snapshot: DevChatRepoSnapshot | null,
): boolean {
  const repoScope = buildRepoEvidenceScopeKey(snapshot);
  const jobScope = buildOpenHandsJobScopeKey(job);
  return Boolean(repoScope && jobScope && repoScope === jobScope);
}

export function selectRepoScopedOpenHandsJob(
  job: OpenHandsJobSnapshot | undefined,
  snapshot: DevChatRepoSnapshot | null,
): OpenHandsJobSnapshot | undefined {
  return isOpenHandsJobScopedToRepo(job, snapshot) ? job : undefined;
}

export function selectRepositoryScopedPullRequestUrl(
  url: string | undefined,
  repositoryTargetKey: string | null,
): string | undefined {
  const trimmed = url?.trim();
  if (!trimmed || !repositoryTargetKey) return undefined;
  try {
    const parsed = new URL(trimmed);
    if (parsed.hostname.toLowerCase() !== 'github.com') return undefined;
    const parts = parsed.pathname.split('/').filter(Boolean);
    if (parts.length < 4 || parts[2] !== 'pull' || !/^\d+$/.test(parts[3])) return undefined;
    const targetKey = `${parts[0].toLowerCase()}/${parts[1].toLowerCase()}`;
    return targetKey === repositoryTargetKey ? trimmed : undefined;
  } catch {
    return undefined;
  }
}
