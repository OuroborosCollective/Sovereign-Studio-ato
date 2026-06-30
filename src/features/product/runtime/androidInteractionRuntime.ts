import { parseDevChatGithubUrl } from './devChatWorkerBridge';

export function isSingleGithubRepoUrl(value: string): boolean {
  const clean = value.trim();
  if (!clean || clean.includes('\n')) return false;
  const parsed = parseDevChatGithubUrl(clean);
  return Boolean(parsed && parsed.repoUrl === clean.replace(/\.git$/i, '').replace(/\/$/, '')) || Boolean(parsed && /^https?:\/\/github\.com\/[^/\s]+\/[^/\s#?]+\/?$/i.test(clean));
}

export function buildRepoDetectedHint(value: string): string {
  const parsed = parseDevChatGithubUrl(value);
  return parsed ? `Repo erkannt · ${parsed.owner}/${parsed.repo} laden` : '';
}

export function safeVibrate(navigatorLike: Pick<Navigator, 'vibrate'> | undefined, pattern: number | number[]): boolean {
  if (!navigatorLike || typeof navigatorLike.vibrate !== 'function') return false;
  try {
    navigatorLike.vibrate(pattern);
    return true;
  } catch {
    return false;
  }
}
