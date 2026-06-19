export const MOBILE_REPO_SETUP_EVENT = 'sovereign:mobile-repo-setup';

export type MobileRepoSetupStage = 'created' | 'dispatched' | 'received' | 'applied' | 'loading' | 'loaded' | 'failed';

export interface MobileRepoSetupDetail {
  repoUrl: string;
  repoBranch: string;
  accessValue: string;
  autoLoad: boolean;
  source: 'mobile-setup-drawer';
  requestId: string;
  createdAt: number;
}

export interface MobileRepoSetupValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export interface MobileRepoSetupState {
  requestId: string;
  stage: MobileRepoSetupStage;
  repoUrl: string;
  repoBranch: string;
  autoLoad: boolean;
  message: string;
  updatedAt: number;
}

const MAX_REPO_URL_LENGTH = 500;
const MAX_BRANCH_LENGTH = 120;
const MAX_ACCESS_LENGTH = 500;
const STORAGE_KEY = 'sovereign-mobile-repo-setup-state';

function now(): number {
  return Date.now();
}

function makeRequestId(): string {
  return `mobile-repo-${now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function safeText(value: unknown, maxLength: number): string {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : '';
}

function isLikelyGithubRepoUrl(value: string): boolean {
  return /^https:\/\/github\.com\/[^\s/]+\/[^\s/]+\/?$/i.test(value.trim());
}

export function createMobileRepoSetupDetail(input: {
  repoUrl: unknown;
  repoBranch?: unknown;
  accessValue: unknown;
  autoLoad?: unknown;
  requestId?: unknown;
  createdAt?: unknown;
}): MobileRepoSetupDetail {
  const createdAt = typeof input.createdAt === 'number' && Number.isFinite(input.createdAt) && input.createdAt > 0
    ? input.createdAt
    : now();
  return {
    repoUrl: safeText(input.repoUrl, MAX_REPO_URL_LENGTH),
    repoBranch: safeText(input.repoBranch, MAX_BRANCH_LENGTH),
    accessValue: safeText(input.accessValue, MAX_ACCESS_LENGTH),
    autoLoad: input.autoLoad === false ? false : true,
    source: 'mobile-setup-drawer',
    requestId: safeText(input.requestId, 120) || makeRequestId(),
    createdAt,
  };
}

export function validateMobileRepoSetupDetail(detail: MobileRepoSetupDetail): MobileRepoSetupValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!detail.requestId.trim()) errors.push('requestId is required.');
  if (detail.source !== 'mobile-setup-drawer') errors.push('source must be mobile-setup-drawer.');
  if (!detail.repoUrl.trim()) errors.push('repoUrl is required.');
  if (detail.repoUrl.length > MAX_REPO_URL_LENGTH) errors.push('repoUrl is too long.');
  if (detail.repoBranch.length > MAX_BRANCH_LENGTH) errors.push('repoBranch is too long.');
  if (detail.accessValue.length > MAX_ACCESS_LENGTH) errors.push('accessValue is too long.');
  if (!Number.isFinite(detail.createdAt) || detail.createdAt <= 0) errors.push('createdAt must be a positive timestamp.');
  if (detail.repoUrl && !isLikelyGithubRepoUrl(detail.repoUrl)) warnings.push('repoUrl does not look like a canonical GitHub repository URL.');
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in mobile repo setup detail.`,
  };
}

export function assertMobileRepoSetupDetailValid(detail: MobileRepoSetupDetail): void {
  const report = validateMobileRepoSetupDetail(detail);
  if (!report.valid) throw new Error(`Mobile repo setup detail is invalid: ${report.errors.join(' | ')}`);
}

export function parseMobileRepoSetupDetail(value: unknown): MobileRepoSetupDetail | null {
  if (!value || typeof value !== 'object') return null;
  const detail = createMobileRepoSetupDetail(value as Record<string, unknown>);
  const report = validateMobileRepoSetupDetail(detail);
  return report.valid ? detail : null;
}

export function createMobileRepoSetupState(detail: MobileRepoSetupDetail, stage: MobileRepoSetupStage, message: string): MobileRepoSetupState {
  assertMobileRepoSetupDetailValid(detail);
  return {
    requestId: detail.requestId,
    stage,
    repoUrl: detail.repoUrl,
    repoBranch: detail.repoBranch,
    autoLoad: detail.autoLoad,
    message: safeText(message, 500) || stage,
    updatedAt: now(),
  };
}

export function validateMobileRepoSetupState(state: MobileRepoSetupState): MobileRepoSetupValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!state.requestId.trim()) errors.push('state requestId is required.');
  if (!['created', 'dispatched', 'received', 'applied', 'loading', 'loaded', 'failed'].includes(state.stage)) errors.push('state stage is invalid.');
  if (!state.repoUrl.trim()) errors.push('state repoUrl is required.');
  if (!Number.isFinite(state.updatedAt) || state.updatedAt <= 0) errors.push('state updatedAt must be positive.');
  if (state.message.length === 0) warnings.push('state message is empty.');
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in mobile repo setup state.`,
  };
}

export function writeMobileRepoSetupState(state: MobileRepoSetupState, storage: Storage | null = typeof window !== 'undefined' ? window.localStorage : null): boolean {
  const report = validateMobileRepoSetupState(state);
  if (!report.valid || !storage) return false;
  storage.setItem(STORAGE_KEY, JSON.stringify(state));
  return true;
}

export function readMobileRepoSetupState(storage: Storage | null = typeof window !== 'undefined' ? window.localStorage : null): MobileRepoSetupState | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MobileRepoSetupState;
    return validateMobileRepoSetupState(parsed).valid ? parsed : null;
  } catch {
    return null;
  }
}

export function dispatchMobileRepoSetup(detail: MobileRepoSetupDetail): boolean {
  if (typeof window === 'undefined') return false;
  assertMobileRepoSetupDetailValid(detail);
  writeMobileRepoSetupState(createMobileRepoSetupState(detail, 'dispatched', 'Repo setup dispatched.'));
  window.dispatchEvent(new CustomEvent(MOBILE_REPO_SETUP_EVENT, { detail }));
  return true;
}
