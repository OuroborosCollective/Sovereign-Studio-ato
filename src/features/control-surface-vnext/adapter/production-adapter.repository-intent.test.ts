import { describe, expect, it } from 'vitest';
import { extractGitHubRepositoryUrl } from './production-adapter';

describe('SovereignProductionAdapter repository intent', () => {
  it('extracts one exact GitHub repository target from an explicit mission URL', () => {
    expect(extractGitHubRepositoryUrl(
      'Prüfe https://github.com/OuroborosCollective/Sovereign-Studio-ato und ändere README.md.',
    )).toBe('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
  });

  it('normalizes an explicit .git suffix without swallowing sentence punctuation', () => {
    expect(extractGitHubRepositoryUrl(
      'Repository: https://github.com/OuroborosCollective/Sovereign-Studio-ato.git. Bitte prüfen.',
    )).toBe('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
  });

  it('does not infer repository execution from non-GitHub or malformed targets', () => {
    expect(extractGitHubRepositoryUrl('Prüfe https://example.com/OuroborosCollective/Sovereign-Studio-ato')).toBeUndefined();
    expect(extractGitHubRepositoryUrl('Prüfe github.com/OuroborosCollective/Sovereign-Studio-ato')).toBeUndefined();
    expect(extractGitHubRepositoryUrl('Nur eine normale Gesprächsmission.')).toBeUndefined();
  });
});
