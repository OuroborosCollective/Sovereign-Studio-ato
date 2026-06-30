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
} from './externalRouteConsentGate';
import { buildSovereignPackageFromRepoFilesWithLlm } from './sovereignPackageFromRepoFiles';

// Mock the module
vi.mock('./sovereignPackageFromRepoFiles', () => ({
  buildSovereignPackageFromRepoFilesWithLlm: vi.fn(),
}));

const mockRepoFile: RepoFile = {
  path: 'README.md',
  type: 'blob',
  content: '# Test Repo',
};

const baseInput: ExternalRouteConsentGateInput = {
  mission: 'Add tests',
  repoFiles: [mockRepoFile],
  selectedFilePath: 'README.md',
};

describe('externalRouteConsentGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset all consents before each test
    clearAllConsents();
  });

  afterEach(() => {
    clearAllConsents();
  });

  describe('generateMissionConsentToken', () => {
    it('generates unique tokens', () => {
      const token1 = generateMissionConsentToken('mission 1');
      const token2 = generateMissionConsentToken('mission 2');
      expect(token1).not.toBe(token2);
    });

    it('includes timestamp', () => {
      const token = generateMissionConsentToken('test');
      expect(token).toContain('consent:');
    });
  });

  describe('grantConsentForMission / denyConsentForMission / isConsentGrantedForMission', () => {
    it('defaults to false', () => {
      const missionId = 'test-mission-1';
      expect(isConsentGrantedForMission(missionId)).toBe(false);
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

    it('consents are independent between missions', () => {
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
      const mockPackage = {
        architecture: { summary: 'test' },
        brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
        files: [],
        suggestions: [],
        providerRoutes: [],
        requestedWork: { type: 'implementation' },
      };

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue(mockPackage);

      const result = await buildSovereignPackageWithConsentGate(baseInput);

      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.package).toBe(mockPackage);
      }
    });

    it('passes allowExternalNoKey: false by default', async () => {
      const mockPackage = {
        architecture: { summary: 'test' },
        brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
        files: [],
        suggestions: [],
        providerRoutes: [],
        requestedWork: { type: 'implementation' },
      };

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue(mockPackage);

      await buildSovereignPackageWithConsentGate(baseInput);

      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
        expect.objectContaining({
          allowExternalNoKey: false,
        })
      );
    });

    it('uses mission-bound consent when granted', async () => {
      const missionId = 'test-mission-consent';
      grantConsentForMission(missionId);
      
      const mockPackage = {
        architecture: { summary: 'test' },
        brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
        files: [],
        suggestions: [],
        providerRoutes: [],
        requestedWork: { type: 'implementation' },
      };

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue(mockPackage);

      await buildSovereignPackageWithConsentGate({
        ...baseInput,
        missionId,
      });

      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
        expect.objectContaining({
          allowExternalNoKey: true,
        })
      );
    });

    it('clears mission consent after successful use', async () => {
      const missionId = 'test-mission-reset';
      grantConsentForMission(missionId);
      
      const mockPackage = {
        architecture: { summary: 'test' },
        brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
        files: [],
        suggestions: [],
        providerRoutes: [],
        requestedWork: { type: 'implementation' },
      };

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue(mockPackage);

      await buildSovereignPackageWithConsentGate({
        ...baseInput,
        missionId,
      });

      // Consent should be cleared after successful use
      expect(isConsentGrantedForMission(missionId)).toBe(false);
    });

    it('returns consentRequired with missionId when CONSENT_REQUIRED error is thrown', async () => {
      const error = new Error('CONSENT_REQUIRED_EXTERNAL_ROUTES: blocked');
      (error as { code: string }).code = 'CONSENT_REQUIRED';
      (error as { attempts: number }).attempts = 5;

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockRejectedValue(error);

      const result = await buildSovereignPackageWithConsentGate(baseInput);

      expect(result.ok).toBe(false);
      expect(result.consentRequired).toBe(true);
      if (!result.ok && result.consentRequired) {
        expect(result.missionId).toBeDefined();
        expect(result.attempts).toBe(5);
      }
    });

    it('returns error when regular error is thrown', async () => {
      const error = new Error('Network error');

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockRejectedValue(error);

      const result = await buildSovereignPackageWithConsentGate(baseInput);

      expect(result.ok).toBe(false);
      expect(result.consentRequired).toBe(false);
      expect('error' in result && result.error).toBe('Network error');
    });

    it('calls onConsentRequired callback when consent is required', async () => {
      const error = new Error('CONSENT_REQUIRED_EXTERNAL_ROUTES: blocked');
      (error as { code: string }).code = 'CONSENT_REQUIRED';
      (error as { attempts: number }).attempts = 3;

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockRejectedValue(error);

      const callback = vi.fn();
      const result = await buildSovereignPackageWithConsentGate(baseInput, {
        onConsentRequired: callback,
      });

      expect(result.ok).toBe(false);
      expect(result.consentRequired).toBe(true);
      expect(callback).toHaveBeenCalled();
    });
  });

  describe('Consent Retry Flow', () => {
    it('full flow: CONSENT_REQUIRED → grant consent → retry with allowExternalNoKey: true', async () => {
      const missionId = 'test-full-flow-mission';
      
      // First call: fails with CONSENT_REQUIRED
      const consentError = new Error('CONSENT_REQUIRED_EXTERNAL_ROUTES: blocked');
      (consentError as { code: string }).code = 'CONSENT_REQUIRED';
      (consentError as { attempts: number }).attempts = 2;

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(consentError);

      const firstResult = await buildSovereignPackageWithConsentGate({
        ...baseInput,
        missionId,
      });

      expect(firstResult.ok).toBe(false);
      expect(firstResult.consentRequired).toBe(true);

      // User approves: grant consent
      grantConsentForMission(missionId);

      // Second call: succeeds with consent
      const mockPackage = {
        architecture: { summary: 'test' },
        brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
        files: [],
        suggestions: [],
        providerRoutes: [],
        requestedWork: { type: 'implementation' },
      };

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce(mockPackage);

      const secondResult = await buildSovereignPackageWithConsentGate({
        ...baseInput,
        missionId,
      });

      expect(secondResult.ok).toBe(true);
      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenLastCalledWith(
        expect.objectContaining({
          allowExternalNoKey: true,
          missionId,
        })
      );
    });
  });

  describe('buildSovereignPackageWithConsentGranted', () => {
    it('grants consent and retries with allowExternalNoKey: true', async () => {
      const missionId = 'test-granted-mission';
      
      const mockPackage = {
        architecture: { summary: 'test' },
        brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
        files: [],
        suggestions: [],
        providerRoutes: [],
        requestedWork: { type: 'implementation' },
      };

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue(mockPackage);

      const result = await buildSovereignPackageWithConsentGranted({
        ...baseInput,
        missionId,
      });

      expect(result.ok).toBe(true);
      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
        expect.objectContaining({
          allowExternalNoKey: true,
          missionId,
        })
      );
      
      // Consent should be cleared after use
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
      // First, grant consent for a specific mission text
      const missionText = 'Build feature Y';
      const firstResult = detectConsentForCurrentMission(missionText);
      
      // User approves
      grantConsentForMission(firstResult.missionId);
      
      // Same mission again
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