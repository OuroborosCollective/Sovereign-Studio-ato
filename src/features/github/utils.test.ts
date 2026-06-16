import { describe, expect, it } from 'vitest';
import { parseGithubRepoUrl } from './utils';

describe('parseGithubRepoUrl', () => {
  it('parses normal repository URLs', () => {
    expect(parseGithubRepoUrl('https://github.com/OuroborosCollective/Sovereign-Studio-ato')).toEqual({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
    });
  });

  it('strips git suffix and query strings', () => {
    expect(parseGithubRepoUrl('https://github.com/OuroborosCollective/Repop1mm3l.git?tab=readme')).toEqual({
      owner: 'OuroborosCollective',
      repo: 'Repop1mm3l',
    });
  });

  it('rejects non GitHub URLs', () => {
    expect(parseGithubRepoUrl('not-a-url')).toBeNull();
  });
});
