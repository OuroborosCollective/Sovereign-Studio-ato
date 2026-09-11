import { describe, expect, it } from 'vitest';
import {
  composeMissionWithRepositoryTarget,
  DEFAULT_SOVEREIGN_REPOSITORY_TARGET,
} from '../components/ChatSurface/repositoryTarget';
import { buildRunRequest, extractGitHubRepositoryUrl } from './production-adapter';

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

  it('turns the visible repository target into the exact free single-agent repository request even when the owner mission contains no URL', () => {
    const routedMission = composeMissionWithRepositoryTarget(
      'Repariere den Draft-PR-Pfad und führe die passenden Regressionstests aus.',
      DEFAULT_SOVEREIGN_REPOSITORY_TARGET,
    );
    expect(buildRunRequest(routedMission, 'single')).toEqual({
      mission: routedMission,
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryUrl: DEFAULT_SOVEREIGN_REPOSITORY_TARGET,
      repositoryBranch: 'main',
    });
  });

  it('preserves conversation mode only when no repository target is supplied anywhere', () => {
    expect(buildRunRequest('Nur eine normale Gesprächsmission.', 'single')).toEqual({
      mission: 'Nur eine normale Gesprächsmission.',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'auto',
    });
  });
});
