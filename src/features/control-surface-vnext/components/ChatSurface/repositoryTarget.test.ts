import { describe, expect, it } from 'vitest';
import {
  composeMissionWithRepositoryTarget,
  DEFAULT_SOVEREIGN_REPOSITORY_TARGET,
  normalizeGitHubRepositoryTarget,
  readInitialRepositoryTarget,
  REPOSITORY_TARGET_STORAGE_KEY,
} from './repositoryTarget';

describe('vNext repository target contract', () => {
  it('normalizes only an exact GitHub owner/repository target', () => {
    expect(normalizeGitHubRepositoryTarget('https://github.com/OuroborosCollective/Sovereign-Studio-ato.git/'))
      .toBe(DEFAULT_SOVEREIGN_REPOSITORY_TARGET);
    expect(normalizeGitHubRepositoryTarget('https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues'))
      .toBeUndefined();
    expect(normalizeGitHubRepositoryTarget('http://github.com/OuroborosCollective/Sovereign-Studio-ato'))
      .toBeUndefined();
    expect(normalizeGitHubRepositoryTarget('github.com/OuroborosCollective/Sovereign-Studio-ato'))
      .toBeUndefined();
  });

  it('binds a mission without an embedded URL to the explicit repository target', () => {
    expect(composeMissionWithRepositoryTarget(
      'Repariere den Draft-PR-Pfad und führe Regressionstests aus.',
      DEFAULT_SOVEREIGN_REPOSITORY_TARGET,
    )).toBe(
      `Repariere den Draft-PR-Pfad und führe Regressionstests aus.\n\nRepository: ${DEFAULT_SOVEREIGN_REPOSITORY_TARGET}`,
    );
  });

  it('keeps explicit conversation mode when the repository field is deliberately cleared', () => {
    expect(composeMissionWithRepositoryTarget('Erkläre nur den aktuellen Status.', '')).toBe('Erkläre nur den aktuellen Status.');
  });

  it('fails closed instead of silently downgrading an invalid repository target to conversation', () => {
    expect(() => composeMissionWithRepositoryTarget(
      'Ändere README.md.',
      'github.com/OuroborosCollective/Sovereign-Studio-ato',
    )).toThrow('Repository target must be an exact https://github.com/owner/repository URL.');
  });

  it('defaults the first vNext session to the canonical Sovereign repository but preserves an explicit cleared target', () => {
    const emptyStorage = { getItem: (_key: string) => null };
    expect(readInitialRepositoryTarget(emptyStorage)).toBe(DEFAULT_SOVEREIGN_REPOSITORY_TARGET);

    const clearedStorage = {
      getItem: (key: string) => key === REPOSITORY_TARGET_STORAGE_KEY ? '' : null,
    };
    expect(readInitialRepositoryTarget(clearedStorage)).toBe('');
  });
});
