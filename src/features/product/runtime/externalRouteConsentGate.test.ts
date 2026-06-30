import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import type { RepoFile } from '../../github/types';
import {
  buildSovereignPackageWithConsentGate,
  buildSovereignPackageWithConsentGranted,
  setExternalRouteConsent,
  isExternalRouteConsentGranted,
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
    // Reset consent flag before each test
    setExternalRouteConsent(false);
  });

  afterEach(() => {
    setExternalRouteConsent(false);
  });

  describe('setExternalRouteConsent / isExternalRouteConsentGranted', () => {
    it('defaults to false', () => {
      expect(isExternalRouteConsentGranted()).toBe(false);
    });

    it('can be set to true', () => {
      setExternalRouteConsent(true);
      expect(isExternalRouteConsentGranted()).toBe(true);
    });

    it('can be set back to false', () => {
      setExternalRouteConsent(true);
      setExternalRouteConsent(false);
      expect(isExternalRouteConsentGranted()).toBe(false);
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

    it('uses consent flag when set', async () => {
      setExternalRouteConsent(true);
      
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
          allowExternalNoKey: true,
        })
      );
    });

    it('resets consent flag after use', async () => {
      setExternalRouteConsent(true);
      
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

      // Consent should be reset after successful use
      expect(isExternalRouteConsentGranted()).toBe(false);
    });

    it('returns consentRequired when CONSENT_REQUIRED error is thrown', async () => {
      const error = new Error('CONSENT_REQUIRED_EXTERNAL_ROUTES: blocked');
      (error as { code: string }).code = 'CONSENT_REQUIRED';
      (error as { attempts: number }).attempts = 5;

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockRejectedValue(error);

      const result = await buildSovereignPackageWithConsentGate(baseInput);

      expect(result.ok).toBe(false);
      expect(result.consentRequired).toBe(true);
      expect('attempts' in result && result.attempts).toBe(5);
    });

    it('returns error when regular error is thrown', async () => {
      const error = new Error('Network error');

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockRejectedValue(error);

      const result = await buildSovereignPackageWithConsentGate(baseInput);

      expect(result.ok).toBe(false);
      expect(result.consentRequired).toBe(false);
      expect('error' in result && result.error).toBe('Network error');
    });
  });

  describe('buildSovereignPackageWithConsentGranted', () => {
    it('sets consent flag and retries with allowExternalNoKey: true', async () => {
      const mockPackage = {
        architecture: { summary: 'test' },
        brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
        files: [],
        suggestions: [],
        providerRoutes: [],
        requestedWork: { type: 'implementation' },
      };

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue(mockPackage);

      const result = await buildSovereignPackageWithConsentGranted(baseInput);

      expect(isExternalRouteConsentGranted()).toBe(false); // Reset after use
      expect(result.ok).toBe(true);
      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
        expect.objectContaining({
          allowExternalNoKey: true,
        })
      );
    });
  });
});