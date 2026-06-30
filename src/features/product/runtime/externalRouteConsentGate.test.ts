import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import type { RepoFile } from '../../github/types';
import {
  buildSovereignPackageWithConsentGate,
  buildSovereignPackageWithConsentGranted,
  grantConsentForMission,
  denyConsentForMission,
  isConsentGrantedForMission,
  clearAllConsents,
  generateMissionConsentToken,
  detectConsentForCurrentMission,
  getCurrentMissionId,
  setCurrentMissionId,
  type ExternalRouteConsentGateInput,
  type ExternalRouteConsentGateResult,
} from './externalRouteConsentGate';
import { buildSovereignPackageFromRepoFilesWithLlm } from './sovereignPackageFromRepoFiles';

vi.mock('./sovereignPackageFromRepoFiles', () => ({
  buildSovereignPackageFromRepoFilesWithLlm: vi.fn(),
}));

type ConsentRequiredResult = Extract<ExternalRouteConsentGateResult, { ok: false; consentRequired: true }>;
type NonConsentFailureResult = Extract<ExternalRouteConsentGateResult, { ok: false; consentRequired: false }>;
type MockPackage = Awaited<ReturnType<typeof buildSovereignPackageFromRepoFilesWithLlm>>;

function consentRequiredError(attempts: number): Error & { code: 'CONSENT_REQUIRED'; attempts: number } {
  return Object.assign(new Error('consent required'), {
    code: 'CONSENT_REQUIRED' as const,
    attempts,
  });
}

function mockPackage(): MockPackage {
  return {
    architecture: { summary: 'test' },
    brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
    files: [],
    suggestions: [],
    providerRoutes: [],
    requestedWork: { type: 'implementation' },
  } as unknown as MockPackage;
}

function expectConsentRequired(result: ExternalRouteConsentGateResult): asserts result is ConsentRequiredResult {
  expect(result.ok).toBe(false);
  expect('consentRequired' in result ? result.consentRequired : undefined).toBe(true);
  if (result.ok || !('consentRequired' in result) || result.consentRequired !== true) {
    throw new Error('Expected consentRequired=true result.');
  }
}

function expectNonConsentFailure(result: ExternalRouteConsentGateResult): asserts result is NonConsentFailureResult {
  expect(result.ok).toBe(false);
  expect('consentRequired' in result ? result.consentRequired : undefined).toBe(false);
  if (result.ok || !('consentRequired' in result) || result.consentRequired !== false) {
    throw new Error('Expected consentRequired=false result.');
  }
}

function mockedBuilder() {
  return buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>;
}

const mockRepoFile: RepoFile = {
  path: 'README.md',
  type: 'blob',
  size: 11,
};

const baseInput: ExternalRouteConsentGateInput = {
  mission: 'Add tests',
  repoFiles: [mockRepoFile],
  selectedFilePath: 'README.md',
};

describe('externalRouteConsentGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearAllConsents();
    setCurrentMissionId(null);
  });

  afterEach(() => {
    clearAllConsents();
    setCurrentMissionId(null);
  });

  it('generates unique consent tokens for different missions', () => {
    expect(generateMissionConsentToken('mission 1')).not.toBe(generateMissionConsentToken('mission 2'));
  });

  it('grants, denies and clears consent by mission', () => {
    grantConsentForMission('mission-a');
    expect(isConsentGrantedForMission('mission-a')).toBe(true);
    expect(isConsentGrantedForMission('mission-b')).toBe(false);

    denyConsentForMission('mission-a');
    expect(isConsentGrantedForMission('mission-a')).toBe(false);

    grantConsentForMission('mission-a');
    grantConsentForMission('mission-b');
    clearAllConsents();
    expect(isConsentGrantedForMission('mission-a')).toBe(false);
    expect(isConsentGrantedForMission('mission-b')).toBe(false);
  });

  it('builds with allowExternalNoKey=false by default', async () => {
    mockedBuilder().mockResolvedValue(mockPackage());

    const result = await buildSovereignPackageWithConsentGate(baseInput);

    expect(result.ok).toBe(true);
    expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
      expect.objectContaining({ allowExternalNoKey: false }),
    );
  });

  it('uses mission-bound consent when granted and clears it after success', async () => {
    const missionId = 'test-mission-consent';
    grantConsentForMission(missionId);
    mockedBuilder().mockResolvedValue(mockPackage());

    const result = await buildSovereignPackageWithConsentGate({
      ...baseInput,
      missionId,
    });

    expect(result.ok).toBe(true);
    expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
      expect.objectContaining({ allowExternalNoKey: true }),
    );
    expect(isConsentGrantedForMission(missionId)).toBe(false);
  });

  it('returns consentRequired with missionId when consent error is thrown', async () => {
    mockedBuilder().mockRejectedValue(consentRequiredError(5));

    const result = await buildSovereignPackageWithConsentGate(baseInput);

    expectConsentRequired(result);
    expect(result.missionId).toBeDefined();
    expect(result.attempts).toBe(5);
  });

  it('returns non-consent failure for regular errors', async () => {
    mockedBuilder().mockRejectedValue(new Error('Network error'));

    const result = await buildSovereignPackageWithConsentGate(baseInput);

    expectNonConsentFailure(result);
    expect(result.error).toBe('Network error');
  });

  it('calls onConsentRequired callback when consent is required', async () => {
    mockedBuilder().mockRejectedValue(consentRequiredError(3));
    const callback = vi.fn();

    const result = await buildSovereignPackageWithConsentGate(baseInput, {
      onConsentRequired: callback,
    });

    expectConsentRequired(result);
    expect(callback).toHaveBeenCalledWith(result.missionId, 3);
  });

  it('supports full grant and retry flow', async () => {
    const missionId = 'test-full-flow-mission';
    mockedBuilder().mockRejectedValueOnce(consentRequiredError(2));

    const firstResult = await buildSovereignPackageWithConsentGate({
      ...baseInput,
      missionId,
    });
    expectConsentRequired(firstResult);

    grantConsentForMission(missionId);
    mockedBuilder().mockResolvedValueOnce(mockPackage());

    const secondResult = await buildSovereignPackageWithConsentGate({
      ...baseInput,
      missionId,
    });

    expect(secondResult.ok).toBe(true);
    expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenLastCalledWith(
      expect.objectContaining({ allowExternalNoKey: true }),
    );
    expect(isConsentGrantedForMission(missionId)).toBe(false);
  });

  it('buildSovereignPackageWithConsentGranted grants consent and retries once', async () => {
    const missionId = 'test-granted-mission';
    mockedBuilder().mockResolvedValue(mockPackage());

    const result = await buildSovereignPackageWithConsentGranted({
      ...baseInput,
      missionId,
    });

    expect(result.ok).toBe(true);
    expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
      expect.objectContaining({ allowExternalNoKey: true }),
    );
    expect(isConsentGrantedForMission(missionId)).toBe(false);
  });

  it('detects consent for repeated mission text and tracks current mission id', () => {
    const firstResult = detectConsentForCurrentMission('Build feature Y');
    expect(firstResult.missionId).toContain('consent:');
    expect(firstResult.consentGranted).toBe(false);
    expect(getCurrentMissionId()).toBe(firstResult.missionId);

    grantConsentForMission(firstResult.missionId);

    const secondResult = detectConsentForCurrentMission('Build feature Y');
    expect(secondResult.consentGranted).toBe(true);
  });

  it('can set mission ID manually', () => {
    setCurrentMissionId('custom-mission-id');
    expect(getCurrentMissionId()).toBe('custom-mission-id');
    setCurrentMissionId(null);
    expect(getCurrentMissionId()).toBeNull();
  });
});
