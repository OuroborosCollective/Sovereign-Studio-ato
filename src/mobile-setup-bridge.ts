export const MOBILE_REPO_SETUP_EVENT = 'sovereign:mobile-repo-setup';

export interface MobileRepoSetupDetail {
  repoUrl: string;
  repoBranch: string;
  accessValue: string;
  autoLoad: boolean;
  source: 'mobile-setup-drawer';
}

function safeText(value: unknown, maxLength: number): string {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : '';
}

export function createMobileRepoSetupDetail(input: {
  repoUrl: unknown;
  repoBranch?: unknown;
  accessValue: unknown;
  autoLoad?: unknown;
}): MobileRepoSetupDetail {
  return {
    repoUrl: safeText(input.repoUrl, 500),
    repoBranch: safeText(input.repoBranch, 120),
    accessValue: safeText(input.accessValue, 500),
    autoLoad: input.autoLoad === false ? false : true,
    source: 'mobile-setup-drawer',
  };
}

export function parseMobileRepoSetupDetail(value: unknown): MobileRepoSetupDetail | null {
  if (!value || typeof value !== 'object') return null;
  const detail = createMobileRepoSetupDetail(value as Record<string, unknown>);
  if (!detail.repoUrl) return null;
  return detail;
}

export function dispatchMobileRepoSetup(detail: MobileRepoSetupDetail): boolean {
  if (typeof window === 'undefined') return false;
  window.dispatchEvent(new CustomEvent(MOBILE_REPO_SETUP_EVENT, { detail }));
  return true;
}
