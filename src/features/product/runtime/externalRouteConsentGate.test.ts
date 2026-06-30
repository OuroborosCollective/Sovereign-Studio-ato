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
  return Object.assign(new Error('CONSENT_REQUIRED_EXTERNAL_ROUTES: blocked'), {
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
  } as MockPackage;
}

function expectConsentRequired(result: ExternalRouteConsentGateResult): asserts result is ConsentRequiredResult {
  expect(result.ok).toBe(false);
  if (result.ok) throw new Error('Expected consent-required result, got ok result.');

  expect(result.consentRequired).toBe(true);
  if (!result.consentRequired) throw new Error('Expected consentRequired=true result.');
}

function expectNonConsentFailure(result: ExternalRouteConsentGateResult): asserts result is NonConsentFailureResult {
  expect(result.ok).toBe(false);
  if (result.ok) throw new Error('Expected failure result, got ok result.');

  expect(result.consentRequired).toBe(false);
  if (result.consentRequired) throw new Error('Expected consentRequired=false result.');
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

  describe('generateMissionConsentToken', () => {
    it('generates unique tokens for different missions', () => {
      const token1 = generateMissionConsentToken('mission 1');
      const token2 = generateMissionConsentToken('mission 2');
      expect(token1).not.toBe(token2);
    });

    it('includes consent prefix', () => {
      const token = generateMissionConsentToken('test');
      expect(token).toContain('consent:');
    });
  });

  describe('grantConsentForMission / denyConsentForMission / isConsentGrantedForMission', () => {
    it('defaults to false', () => {
      expect(isConsentGrantedForMission('test-mission-1')).toBe(false);
    });

    it('can grant consent for a mission', () => {
      const missionId = 'test-mission-2';
      grantConsentForMission(missionId);
      expect(isConsentGrantedForMission(missionId)).toBe(true);
    });

    it('can deny consent for a mission', () => {
      const missionId = 'test-mission-3';
      grantConsentForMission(missionId);
      denyConsentForMission(missionId);
      expect(isConsentGrantedForMission(missionId)).toBe(false);
    });

    it('keeps consents independent between missions', () => {
      const missionId1 = 'test-mission-4';
      const missionId2 = 'test-mission-5';
      grantConsentForMission(missionId1);
      expect(isConsentGrantedForMission(missionId1)).toBe(true);
      expect(isConsentGrantedForMission(missionId2)).toBe(false);
    });
  });

  describe('clearAllConsents', () => {
    it('clears all pending consents', () => {
      grantConsentForMission('mission-a');
      grantConsentForMission('mission-b');
      clearAllConsents();
      expect(isConsentGrantedForMission('mission-a')).toBe(false);
      expect(isConsentGrantedForMission('mission-b')).toBe(false);
    });
  });

  describe('buildSovereignPackageWithConsentGate', () => {
    it('returns ok result when package builds successfully', async () => {
      const pkg = mockPackage();
      mockedBuilder().mockResolvedValue(pkg);

      const result = await buildSovereignPackageWithConsentGate(baseInput);

      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.package).toBe(pkg);
      }
    });

    it('passes allowExternalNoKey: false by default', async () => {
      mockedBuilder().mockResolvedValue(mockPackage());

      await buildSovereignPackageWithConsentGate(baseInput);

      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
        expect.objectContaining({
          allowExternalNoKey: false,
        }),
      );
    });

    it('uses mission-bound consent when granted', async () => {
      const missionId = 'test-mission-consent';
      grantConsentForMission(missionId);
      mockedBuilder().mockResolvedValue(mockPackage());

      await buildSovereignPackageWithConsentGate({
        ...baseInput,
        missionId,
      });

      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
        expect.objectContaining({
          allowExternalNoKey: true,
        }),
      );
    });

    it('clears mission consent after successful use', async () => {
      const missionId = 'test-mission-reset';
      grantConsentForMission(missionId);
      mockedBuilder().mockResolvedValue(mockPackage());

      await buildSovereignPackageWithConsentGate({
        ...baseInput,
        missionId,
      });

      expect(isConsentGrantedForMission(missionId)).toBe(false);
    });

    it('returns consentRequired with missionId when CONSENT_REQUIRED error is thrown', async () => {
      mockedBuilder().mockRejectedValue(consentRequiredError(5));

      const result = await buildSovereignPackageWithConsentGate(baseInput);

      expectConsentRequired(result);
      expect(result.missionId).toBeDefined();
      expect(result.attempts).toBe(5);
    });

    it('returns error when regular error is thrown', async () => {
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
  });

  describe('Consent Retry Flow', () => {
    it('full flow: CONSENT_REQUIRED -> grant consent -> retry with allowExternalNoKey: true', async () => {
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
        expect.objectContaining({
          allowExternalNoKey: true,
        }),
      );
      expect(isConsentGrantedForMission(missionId)).toBe(false);
    });
  });

  describe('buildSovereignPackageWithConsentGranted', () => {
    it('grants consent and retries with allowExternalNoKey: true', async () => {
      const missionId = 'test-granted-mission';
      mockedBuilder().mockResolvedValue(mockPackage());

      const result = await buildSovereignPackageWithConsentGranted({
        ...baseInput,
        missionId,
      });

      expect(result.ok).toBe(true);
      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
        expect.objectContaining({
          allowExternalNoKey: true,
        }),
      );
      expect(isConsentGrantedForMission(missionId)).toBe(false);
    });
  });

  describe('detectConsentForCurrentMission', () => {
    it('generates new missionId for new mission', () => {
      const result = detectConsentForCurrentMission('Build feature X');
      expect(result.missionId).toBeDefined();
      expect(result.missionId).toContain('consent:');
      expect(result.consentGranted).toBe(false);
    });

    it('returns consentGranted: true when user previously approved same mission', () => {
      const missionText = 'Build feature Y';
      const firstResult = detectConsentForCurrentMission(missionText);

      grantConsentForMission(firstResult.missionId);

      const secondResult = detectConsentForCurrentMission(missionText);
      expect(secondResult.consentGranted).toBe(true);
    });

    it('tracks current mission ID', () => {
      const result = detectConsentForCurrentMission('Test mission');
      expect(getCurrentMissionId()).toBe(result.missionId);
    });

    it('can set mission ID manually', () => {
      setCurrentMissionId('custom-mission-id');
      expect(getCurrentMissionId()).toBe('custom-mission-id');
      setCurrentMissionId(null);
      expect(getCurrentMissionId()).toBeNull();
    });
  });
});
