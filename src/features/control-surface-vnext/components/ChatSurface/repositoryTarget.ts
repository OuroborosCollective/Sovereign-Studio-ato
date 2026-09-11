export const DEFAULT_SOVEREIGN_REPOSITORY_TARGET = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato';
export const REPOSITORY_TARGET_STORAGE_KEY = 'sovereign-vnext-repository-target';

export function normalizeGitHubRepositoryTarget(value: string): string | undefined {
  const raw = value.trim();
  if (!raw) return undefined;
  const withoutTrailingSlash = raw.replace(/\/+$/, '');
  const cleaned = withoutTrailingSlash.replace(/\.git$/i, '');
  try {
    const parsed = new URL(cleaned);
    const segments = parsed.pathname.split('/').filter(Boolean);
    if (
      parsed.protocol !== 'https:'
      || parsed.hostname !== 'github.com'
      || segments.length !== 2
      || parsed.search
      || parsed.hash
    ) return undefined;
    return `https://github.com/${segments[0]}/${segments[1]}`;
  } catch {
    return undefined;
  }
}

export function composeMissionWithRepositoryTarget(mission: string, repositoryTarget: string): string {
  const cleanMission = mission.trim();
  if (!cleanMission) return '';
  if (!repositoryTarget.trim()) return cleanMission;
  const normalized = normalizeGitHubRepositoryTarget(repositoryTarget);
  if (!normalized) throw new Error('Repository target must be an exact https://github.com/owner/repository URL.');
  if (cleanMission.includes(normalized)) return cleanMission;
  return `${cleanMission}\n\nRepository: ${normalized}`;
}

export function readInitialRepositoryTarget(storage?: Pick<Storage, 'getItem'>): string {
  if (!storage) return DEFAULT_SOVEREIGN_REPOSITORY_TARGET;
  try {
    const stored = storage.getItem(REPOSITORY_TARGET_STORAGE_KEY);
    if (stored === null) return DEFAULT_SOVEREIGN_REPOSITORY_TARGET;
    if (!stored.trim()) return '';
    return normalizeGitHubRepositoryTarget(stored) ?? '';
  } catch {
    return DEFAULT_SOVEREIGN_REPOSITORY_TARGET;
  }
}
