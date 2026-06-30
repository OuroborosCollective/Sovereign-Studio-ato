import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { RepoFile } from '../../github/types';
import {
  buildSovereignPackageWithConsentGate,
  buildSovereignPackageWithConsentGranted,
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
    it('passes allowExternalNoKey: true to the function', async () => {
      const mockPackage = {
        architecture: { summary: 'test' },
        brain: { analysis: { severity: 'low' }, plan: { strategy: 'test' } },
        files: [],
        suggestions: [],
        providerRoutes: [],
        requestedWork: { type: 'implementation' },
      };

      (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue(mockPackage);

      await buildSovereignPackageWithConsentGranted(baseInput);

      expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenCalledWith(
        expect.objectContaining({
          allowExternalNoKey: true,
        })
      );
    });
  });
});