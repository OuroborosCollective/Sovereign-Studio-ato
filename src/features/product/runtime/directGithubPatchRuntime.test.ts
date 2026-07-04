import { describe, expect, it } from 'vitest';
import {
  buildDirectPatchPlan,
  buildDirectPatchPlanWithContentLoad,
  checkDirectPatchCapability,
  detectDirectPatchTarget,
  executeDirectPatchRuntime,
  generateDirectPatchContent,
  isDirectPatchIntent,
  loadGitHubFileContent,
} from './directGithubPatchRuntime';
import type {
  DirectGitHubPatchFailure,
  DirectGitHubPatchResult,
  DirectGitHubPatchSuccess,
  DirectPatchRepoContext,
} from './directGithubPatchTypes';
import {
  isDirectPatchAllowedPath,
  isDirectPatchForbiddenPath,
} from './directGithubPatchTypes';

function isPatchSuccess(result: DirectGitHubPatchResult): result is DirectGitHubPatchSuccess {
  return 'proposedContent' in result;
}

function isPatchFailure(result: DirectGitHubPatchResult): result is DirectGitHubPatchFailure {
  return 'blocker' in result;
}

function expectPatchSuccess(result: DirectGitHubPatchResult): DirectGitHubPatchSuccess {
  expect(isPatchSuccess(result)).toBe(true);
  if (!isPatchSuccess(result)) throw new Error('Expected patch success.');
  return result;
}

function expectPatchFailure(result: DirectGitHubPatchResult): DirectGitHubPatchFailure {
  expect(isPatchFailure(result)).toBe(true);
  if (!isPatchFailure(result)) throw new Error('Expected patch failure.');
  return result;
}

describe('Direct GitHub Patch path policy', () => {
  it('allows only README and docs markdown paths', () => {
    expect(isDirectPatchAllowedPath('README.md')).toBe(true);
    expect(isDirectPatchAllowedPath('README.de.md')).toBe(true);
    expect(isDirectPatchAllowedPath('docs/intro.md')).toBe(true);
    expect(isDirectPatchAllowedPath('doc/guide.md')).toBe(true);
    expect(isDirectPatchAllowedPath('documentation/readme.md')).toBe(true);
  });

  it('rejects code, Android, scripts, workflow and package paths', () => {
    expect(isDirectPatchAllowedPath('src/index.ts')).toBe(false);
    expect(isDirectPatchAllowedPath('android/app/build.gradle')).toBe(false);
    expect(isDirectPatchAllowedPath('scripts/deploy.sh')).toBe(false);
    expect(isDirectPatchAllowedPath('.github/workflows/ci.yml')).toBe(false);
    expect(isDirectPatchAllowedPath('package.json')).toBe(false);
    expect(isDirectPatchForbiddenPath('src/index.ts')).toBe(true);
    expect(isDirectPatchForbiddenPath('README.md')).toBe(false);
  });
});

describe('Direct GitHub Patch intent and target detection', () => {
  const repoFilePaths = ['README.md', 'docs/intro.md', 'src/index.ts', 'package.json'];

  it('detects simple README and docs intents', () => {
    expect(isDirectPatchIntent('Passe README an und füge 🐥 in den Titel ein')).toBe(true);
    expect(isDirectPatchIntent('Update the README title')).toBe(true);
    expect(isDirectPatchIntent('Aktualisiere die Dokumentation')).toBe(true);
    expect(isDirectPatchIntent('Update the docs')).toBe(true);
  });

  it('does not detect complex implementation tasks', () => {
    expect(isDirectPatchIntent('Implementiere eine neue API')).toBe(false);
    expect(isDirectPatchIntent('Baue die Komponente')).toBe(false);
    expect(isDirectPatchIntent('Schreibe Tests für die Funktion')).toBe(false);
  });

  it('finds safe README/docs targets', () => {
    expect(detectDirectPatchTarget('Update the README', repoFilePaths)).toBe('README.md');
    expect(detectDirectPatchTarget('Update the README', [])).toBe('README.md');
    expect(detectDirectPatchTarget('Update the docs', repoFilePaths)).toBe('docs/intro.md');
    expect(detectDirectPatchTarget('Update the README', ['src/index.ts'])).toBe(null);
  });
});

describe('Direct GitHub Patch capability', () => {
  const repoContext: DirectPatchRepoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    filePaths: ['README.md', 'docs/intro.md'],
  };

  it('requires GitHub access and repo context', () => {
    expect(checkDirectPatchCapability({ repoContext, githubAccessReady: false, instruction: 'Update README' }).blocker).toBe('github_access_missing');
    expect(checkDirectPatchCapability({ repoContext: null, githubAccessReady: true, instruction: 'Update README' }).blocker).toBe('repo_missing');
  });

  it('accepts simple README tasks and rejects complex tasks', () => {
    expect(checkDirectPatchCapability({ repoContext, githubAccessReady: true, instruction: 'Update the README title' }).available).toBe(true);
    expect(checkDirectPatchCapability({ repoContext, githubAccessReady: true, instruction: 'Implementiere eine neue API' }).blocker).toBe('unsupported_intent');
  });

  it('blocks missing real base content', () => {
    for (const baseContent of ['', '   ', '[loaded]']) {
      const result = checkDirectPatchCapability({
        repoContext,
        githubAccessReady: true,
        instruction: 'Update the README title',
        baseContent,
      });
      expect(result.available).toBe(false);
      expect(result.blocker).toBe('content_load_failed');
    }
  });
});

describe('Direct GitHub Patch content generation', () => {
  const baseReadme = '# Project Title\n\nThis is the project description.\n';

  it('generates a title emoji patch', () => {
    const result = generateDirectPatchContent(baseReadme, 'Füge 🐥 in den Titel ein');
    expect(result?.content).toContain('🐥');
    expect(result?.summary).toContain('Added');
  });

  it('generates a title update patch', () => {
    const result = generateDirectPatchContent(baseReadme, 'Update title to New Project Name');
    expect(result?.content).toContain('New Project Name');
    expect(result?.content).not.toContain('Project Title');
  });

  it('returns null for unsupported instructions', () => {
    expect(generateDirectPatchContent(baseReadme, 'Implementiere eine API')).toBeNull();
  });
});

describe('executeDirectPatchRuntime', () => {
  const repoContext: DirectPatchRepoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    filePaths: ['README.md'],
  };

  it('returns success for valid README patch', () => {
    const success = expectPatchSuccess(executeDirectPatchRuntime({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      baseContent: '# My Project\n\nDescription.',
      targetPath: 'README.md',
    }));

    expect(success.nextAction).toBe('preview_diff');
    expect(success.targetPath).toBe('README.md');
    expect(success.proposedContent).toContain('🐥');
  });

  it('returns failure for forbidden paths and empty patches', () => {
    const forbidden = expectPatchFailure(executeDirectPatchRuntime({
      repoContext,
      instruction: 'Update the file',
      baseContent: 'const x = 1;',
      targetPath: 'src/index.ts',
    }));
    expect(forbidden.blocker).toBe('unsafe_target');

    const empty = expectPatchFailure(executeDirectPatchRuntime({
      repoContext,
      instruction: 'Keep everything the same',
      baseContent: '# Title',
      targetPath: 'README.md',
    }));
    expect(empty.blocker).toBe('unsupported_intent');
  });
});

describe('buildDirectPatchPlan', () => {
  const repoContext: DirectPatchRepoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    filePaths: ['README.md'],
  };

  it('returns capability result when not available', () => {
    const result = buildDirectPatchPlan({
      repoContext,
      instruction: 'Implementiere API',
      baseContent: '# Title',
      githubAccessReady: false,
    });
    expect('capability' in result).toBe(true);
  });

  it('returns execution result when available', () => {
    const result = buildDirectPatchPlan({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      baseContent: '# Title\n\nDesc.',
      githubAccessReady: true,
    });

    expect('result' in result).toBe(true);
    if ('result' in result) expect(expectPatchSuccess(result.result).targetPath).toBe('README.md');
  });

  it('does not produce a patch suggestion without real README content', () => {
    const result = buildDirectPatchPlan({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      baseContent: '',
      githubAccessReady: true,
    });

    expect('capability' in result).toBe(true);
    if ('capability' in result) expect(result.capability.blocker).toBe('content_load_failed');
  });
});

describe('loadGitHubFileContent', () => {
  it('handles successful base64 content decode', async () => {
    const mockFetcher = async () => ({
      ok: true,
      json: async () => ({
        content: 'IyBNeSBQcm9qZWN0CgJUaGlzIGlzIHRoZSBwcm9qZWN0IGRlc2NyaXB0aW9uLg==',
        encoding: 'base64',
        sha: 'abc123',
        type: 'file',
      }),
    });

    const result = await loadGitHubFileContent({
      owner: 'test-owner',
      repo: 'test-repo',
      branch: 'main',
      filePath: 'README.md',
      token: 'x',
      fetcher: mockFetcher as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.content).toContain('# My Project');
    expect(result.sha).toBe('abc123');
  });

  it('encodes nested GitHub Contents API paths segment-wise', async () => {
    let calledUrl = '';
    const mockFetcher = async (url: RequestInfo | URL) => {
      calledUrl = String(url);
      return {
        ok: true,
        json: async () => ({ content: 'IyBEb2NzCg==', encoding: 'base64', sha: 'docs123', type: 'file' }),
      };
    };

    const result = await loadGitHubFileContent({
      owner: 'test owner',
      repo: 'test repo',
      branch: 'feature/docs',
      filePath: 'docs/guide file.md',
      token: 'x',
      fetcher: mockFetcher as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(calledUrl).toContain('/contents/docs/guide%20file.md?');
    expect(calledUrl).not.toContain('docs%2Fguide%20file.md');
  });

  it('handles API and network failures gracefully', async () => {
    const apiFailure = await loadGitHubFileContent({
      owner: 'test-owner',
      repo: 'test-repo',
      branch: 'main',
      filePath: 'README.md',
      token: 'x',
      fetcher: (async () => ({ ok: false, status: 404 })) as unknown as typeof fetch,
    });
    expect(apiFailure.ok).toBe(false);
    expect(apiFailure.error).toContain('404');

    const networkFailure = await loadGitHubFileContent({
      owner: 'test-owner',
      repo: 'test-repo',
      branch: 'main',
      filePath: 'README.md',
      token: 'x',
      fetcher: (async () => { throw new Error('Network error'); }) as unknown as typeof fetch,
    });
    expect(networkFailure.ok).toBe(false);
    expect(networkFailure.error).toContain('Network error');
  });
});

describe('buildDirectPatchPlanWithContentLoad', () => {
  const repoContext: DirectPatchRepoContext = {
    owner: 'test-owner',
    name: 'test-repo',
    branch: 'main',
    filePaths: ['README.md'],
  };

  it('loads content before building a patch plan', async () => {
    const result = await buildDirectPatchPlanWithContentLoad({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      githubAccessReady: true,
      token: 'x',
      fetcher: (async () => ({
        ok: true,
        json: async () => ({ content: 'IyBNeSBQcm9qZWN0Cg==', encoding: 'base64', sha: 'abc123', type: 'file' }),
      })) as unknown as typeof fetch,
    });

    expect('result' in result).toBe(true);
    if ('result' in result) expect(expectPatchSuccess(result.result).proposedContent).toContain('🐥');
  });

  it('blocks honestly when content loading fails', async () => {
    const result = await buildDirectPatchPlanWithContentLoad({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      githubAccessReady: true,
      token: 'x',
      fetcher: (async () => ({ ok: false, status: 404 })) as unknown as typeof fetch,
    });

    expect('capability' in result).toBe(true);
    if ('capability' in result) expect(result.capability.blocker).toBe('content_load_failed');
  });
});
