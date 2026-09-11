import { describe, expect, it } from 'vitest';
import { buildRepositoryBoundRunRequest } from './repository-bound-adapter';

describe('vNext repository-bound Draft-PR mission contract', () => {
  it('keeps a normal repository instruction in repository execution even without a GitHub URL', () => {
    expect(buildRepositoryBoundRunRequest('Please add the repository readme a smiley like this :)')).toEqual({
      mission: 'Please add the repository readme a smiley like this :)',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryBranch: 'main',
    });
  });

  it('keeps an explicit GitHub repository URL as a bounded target override', () => {
    expect(buildRepositoryBoundRunRequest(
      'Ändere README.md in https://github.com/OuroborosCollective/Sovereign-Studio-ato.',
    )).toEqual({
      mission: 'Ändere README.md in https://github.com/OuroborosCollective/Sovereign-Studio-ato.',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repositoryBranch: 'main',
    });
  });

  it('fails closed instead of silently enabling swarm on the Draft-PR-first path', () => {
    expect(() => buildRepositoryBoundRunRequest('Ändere README.md.', 'swarm')).toThrow(/single agent/i);
  });
});
