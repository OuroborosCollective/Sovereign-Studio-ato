/**
 * Direct GitHub Patch Runtime Tests
 */

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

function expectPatchSuccess(result: DirectGitHubPatchResult): DirectGitHubPatchSuccess {
  if (!result.ok) {
    throw new Error(`Expected Direct GitHub Patch success, got ${result.blocker}: ${result.reason}`);
  }
  return result;
}

function expectPatchFailure(result: DirectGitHubPatchResult): DirectGitHubPatchFailure {
  if (result.ok) {
    throw new Error(`Expected Direct GitHub Patch failure, got success for ${result.targetPath}`);
  }
  return result;
}

describe('isDirectPatchAllowedPath', () => {
  it('allows README.md', () => {
    expect(isDirectPatchAllowedPath('README.md')).toBe(true);
  });

  it('allows README with locale', () => {
    expect(isDirectPatchAllowedPath('README.de.md')).toBe(true);
    expect(isDirectPatchAllowedPath('README.en.md')).toBe(true);
  });

  it('allows docs/*.md files', () => {
    expect(isDirectPatchAllowedPath('docs/intro.md')).toBe(true);
    expect(isDirectPatchAllowedPath('docs/api/reference.md')).toBe(true);
  });

  it('allows doc/*.md and documentation/*.md files', () => {
    expect(isDirectPatchAllowedPath('doc/guide.md')).toBe(true);
    expect(isDirectPatchAllowedPath('documentation/readme.md')).toBe(true);
  });

  it('rejects forbidden and code paths', () => {
    expect(isDirectPatchAllowedPath('src/index.ts')).toBe(false);
    expect(isDirectPatchAllowedPath('src/App.tsx')).toBe(false);
    expect(isDirectPatchAllowedPath('android/app/build.gradle')).toBe(false);
    expect(isDirectPatchAllowedPath('scripts/deploy.sh')).toBe(false);
    expect(isDirectPatchAllowedPath('.github/workflows/ci.yml')).toBe(false);
    expect(isDirectPatchAllowedPath('package.json')).toBe(false);
  });
});

describe('isDirectPatchForbiddenPath', () => {
  it('marks code, Android, scripts and workflow files as forbidden', () => {
    expect(isDirectPatchForbiddenPath('src/index.ts')).toBe(true);
    expect(isDirectPatchForbiddenPath('src/components/App.tsx')).toBe(true);
    expect(isDirectPatchForbiddenPath('android/build.gradle')).toBe(true);
    expect(isDirectPatchForbiddenPath('scripts/test.sh')).toBe(true);
    expect(isDirectPatchForbiddenPath('.github/workflows/build.yml')).toBe(true);
  });

  it('marks README.md as not forbidden', () => {
    expect(isDirectPatchForbiddenPath('README.md')).toBe(false);
  });
});

describe('isDirectPatchIntent', () => {
  it('detects README and docs change intents', () => {
    expect(isDirectPatchIntent('Passe README an und füge 🐥 in den Titel ein')).toBe(true);
    expect(isDirectPatchIntent('Update the README title')).toBe(true);
    expect(isDirectPatchIntent('Aktualisiere die Dokumentation')).toBe(true);
    expect(isDirectPatchIntent('Update the docs')).toBe(true);
  });

  it('detects changelog and content addition intents', () => {
    expect(isDirectPatchIntent('Füge einen Changelog-Eintrag hinzu')).toBe(true);
    expect(isDirectPatchIntent('Füge einen Hinweis am Ende hinzu')).toBe(true);
  });

  it('does not flag complex code tasks', () => {
    expect(isDirectPatchIntent('Implementiere eine neue API')).toBe(false);
    expect(isDirectPatchIntent('Baue die Komponente')).toBe(false);
    expect(isDirectPatchIntent('Schreibe Tests für die Funktion')).toBe(false);
    expect(isDirectPatchIntent('Refaktoriere den Code')).toBe(false);
  });
});

describe('detectDirectPatchTarget', () => {
  const repoFilePaths = [
    'README.md',
    'docs/intro.md',
    'docs/api.md',
    'src/index.ts',
    'package.json',
  ];

  it('detects README.md for README instructions', () => {
    expect(detectDirectPatchTarget('Update the README', repoFilePaths)).toBe('README.md');
  });

  it('uses README.md as safe fallback when the snapshot has no precomputed file paths', () => {
    expect(detectDirectPatchTarget('Update the README', [])).toBe('README.md');
  });

  it('detects docs file for docs instructions', () => {
    const target = detectDirectPatchTarget('Update the docs', repoFilePaths);
    expect(target).toMatch(/^docs\/.*\.md$/);
  });

  it('returns null when no matching file exists in the repo snapshot', () => {
    expect(detectDirectPatchTarget('Update some file', ['src/index.ts'])).toBe(null);
    expect(detectDirectPatchTarget('Update the README', ['src/index.ts'])).toBe(null);
  });
});

describe('checkDirectPatchCapability', () => {
  const repoContext: DirectPatchRepoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    filePaths: ['README.md', 'docs/intro.md'],
  };

  it('returns unavailable when GitHub access is missing', () => {
    const result = checkDirectPatchCapability({
      repoContext,
      githubAccessReady: false,
      instruction: 'Update README',
    });

    expect(result.available).toBe(false);
    expect(result.blocker).toBe('github_access_missing');
  });

  it('returns unavailable when repo context is missing', () => {
    const result = checkDirectPatchCapability({
      repoContext: null,
      githubAccessReady: true,
      instruction: 'Update README',
    });

    expect(result.available).toBe(false);
    expect(result.blocker).toBe('repo_missing');
  });

  it('returns unavailable for complex tasks', () => {
    const result = checkDirectPatchCapability({
      repoContext,
      githubAccessReady: true,
      instruction: 'Implementiere eine neue API',
    });

    expect(result.available).toBe(false);
    expect(result.blocker).toBe('unsupported_intent');
  });

  it('returns available for simple README task', () => {
    const result = checkDirectPatchCapability({
      repoContext,
      githubAccessReady: true,
      instruction: 'Update the README title',
    });

    expect(result.available).toBe(true);
    expect(result.reason).toContain('Direct Patch');
  });

  it('blocks empty, whitespace and placeholder content', () => {
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

describe('generateDirectPatchContent', () => {
  const baseReadme = `# Project Title

This is the project description.

## Installation

Instructions here.
`;

  it('generates patch for title emoji addition', () => {
    const result = generateDirectPatchContent(baseReadme, 'Füge 🐥 in den Titel ein');

    expect(result).not.toBeNull();
    expect(result?.content).toContain('🐥');
    expect(result?.summary).toContain('Added');
  });

  it('generates patch for title update', () => {
    const result = generateDirectPatchContent(baseReadme, 'Update title to New Project Name');

    expect(result).not.toBeNull();
    expect(result?.content).toContain('New Project Name');
    expect(result?.content).not.toContain('Project Title');
  });

  it('returns null for unsupported instructions', () => {
    const result = generateDirectPatchContent(baseReadme, 'Implementiere eine API');
    expect(result).toBeNull();
  });

  it('adds content at end', () => {
    const result = generateDirectPatchContent(baseReadme, 'Füge "More info" am Ende hinzu');

    expect(result).not.toBeNull();
    expect(result?.content).toContain('More info');
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
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      baseContent: '# My Project\n\nDescription.',
      targetPath: 'README.md',
    });

    const success = expectPatchSuccess(result);
    expect(success.nextAction).toBe('preview_diff');
    expect(success.targetPath).toBe('README.md');
    expect(success.proposedContent).toContain('🐥');
  });

  it('returns failure for forbidden path', () => {
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Update the file',
      baseContent: 'const x = 1;',
      targetPath: 'src/index.ts',
    });

    const failure = expectPatchFailure(result);
    expect(failure.blocker).toBe('unsafe_target');
  });

  it('returns failure for empty patch', () => {
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Keep everything the same',
      baseContent: '# Title',
      targetPath: 'README.md',
    });

    expectPatchFailure(result);
  });

  it('rejects patch with secrets', () => {
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Füge ghp_abcdefghijklmnopqrstuvwxyz1234567890abcd am Ende hinzu',
      baseContent: '# Token',
      targetPath: 'README.md',
    });

    const failure = expectPatchFailure(result);
    expect(failure.blocker).toBe('unsafe_target');
  });
});

describe('buildDirectPatchPlan', () => {
  const repoContext: DirectPatchRepoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    filePaths: ['README.md'],
  };

  it('returns capability check result when not available', () => {
    const result = buildDirectPatchPlan({
      repoContext,
      instruction: 'Implementiere API',
      baseContent: '# Title',
      githubAccessReady: false,
    });

    expect('capability' in result).toBe(true);
    if ('capability' in result) {
      expect(result.capability.available).toBe(false);
    }
  });

  it('returns execution result when available', () => {
    const result = buildDirectPatchPlan({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      baseContent: '# Title\n\nDesc.',
      githubAccessReady: true,
    });

    expect('result' in result).toBe(true);
    if ('result' in result) {
      const success = expectPatchSuccess(result.result);
      expect(success.targetPath).toBe('README.md');
    }
  });

  it('blocks when baseContent is empty, whitespace, or placeholder only', () => {
    for (const baseContent of ['', '   \n\t  ', '[loaded]']) {
      const result = buildDirectPatchPlan({
        repoContext,
        instruction: 'Füge 🐥 in den Titel ein',
        baseContent,
        githubAccessReady: true,
      });

      expect('capability' in result).toBe(true);
      if ('capability' in result) {
        expect(result.capability.available).toBe(false);
        expect(result.capability.blocker).toBe('content_load_failed');
      }
    }
  });

  it('generates patch with real README base content', () => {
    const result = buildDirectPatchPlan({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      baseContent: `# My Project

This is a real README.

## Installation

Run npm install.
`,
      githubAccessReady: true,
    });

    expect('result' in result).toBe(true);
    if ('result' in result) {
      const success = expectPatchSuccess(result.result);
      expect(success.proposedContent).toContain('🐥');
      expect(success.targetPath).toBe('README.md');
    }
  });
});

describe('Direct GitHub Patch blocker types', () => {
  const repoContext: DirectPatchRepoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    filePaths: ['README.md', 'src/index.ts', 'android/build.gradle'],
  };

  it('blocks unsafe target paths', () => {
    const result = buildDirectPatchPlan({
      repoContext,
      instruction: 'Update src/index.ts',
      baseContent: 'const x = 1;',
      githubAccessReady: true,
    });

    expect('capability' in result || ('result' in result && !result.result.ok)).toBe(true);
  });

  it('blocks Android files', () => {
    const result = checkDirectPatchCapability({
      repoContext,
      instruction: 'Update android/build.gradle',
      githubAccessReady: true,
    });

    expect(result.available).toBe(false);
  });

  it('requires GitHub access', () => {
    const result = checkDirectPatchCapability({
      repoContext,
      instruction: 'Update README',
      githubAccessReady: false,
    });

    expect(result.available).toBe(false);
    expect(result.blocker).toBe('github_access_missing');
  });

  it('requires repo context', () => {
    const result = checkDirectPatchCapability({
      repoContext: null,
      instruction: 'Update README',
      githubAccessReady: true,
    });

    expect(result.available).toBe(false);
    expect(result.blocker).toBe('repo_missing');
  });

  it('does not produce a patch suggestion without real README content', () => {
    const result = buildDirectPatchPlan({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      baseContent: '',
      githubAccessReady: true,
    });

    expect('capability' in result).toBe(true);
    if ('capability' in result) {
      expect(result.capability.blocker).toBe('content_load_failed');
      expect(result.capability.reason).toContain('konnte nicht geladen');
    }
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
      token: 'test-token-value',
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
        json: async () => ({
          content: 'IyBEb2NzCg==',
          encoding: 'base64',
          sha: 'docs123',
          type: 'file',
        }),
      };
    };

    const result = await loadGitHubFileContent({
      owner: 'test owner',
      repo: 'test repo',
      branch: 'feature/docs',
      filePath: 'docs/guide file.md',
      token: 'test-token-value',
      fetcher: mockFetcher as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(calledUrl).toContain('/contents/docs/guide%20file.md?');
    expect(calledUrl).not.toContain('docs%2Fguide%20file.md');
  });

  it('handles API failure gracefully', async () => {
    const mockFetcher = async () => ({ ok: false, status: 404 });

    const result = await loadGitHubFileContent({
      owner: 'test-owner',
      repo: 'test-repo',
      branch: 'main',
      filePath: 'README.md',
      token: 'test-token-value',
      fetcher: mockFetcher as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('404');
  });

  it('handles network errors gracefully', async () => {
    const mockFetcher = async () => {
      throw new Error('Network error');
    };

    const result = await loadGitHubFileContent({
      owner: 'test-owner',
      repo: 'test-repo',
      branch: 'main',
      filePath: 'README.md',
      token: 'test-token-value',
      fetcher: mockFetcher as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('Network error');
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
    const mockFetcher = async () => ({
      ok: true,
      json: async () => ({
        content: 'IyBNeSBQcm9qZWN0Cg==',
        encoding: 'base64',
        sha: 'abc123',
        type: 'file',
      }),
    });

    const result = await buildDirectPatchPlanWithContentLoad({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      githubAccessReady: true,
      token: 'test-token-value',
      fetcher: mockFetcher as unknown as typeof fetch,
    });

    expect('result' in result).toBe(true);
    if ('result' in result) {
      const success = expectPatchSuccess(result.result);
      expect(success.proposedContent).toContain('🐥');
    }
  });

  it('blocks honestly when content loading fails', async () => {
    const mockFetcher = async () => ({ ok: false, status: 404 });

    const result = await buildDirectPatchPlanWithContentLoad({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      githubAccessReady: true,
      token: 'test-token-value',
      fetcher: mockFetcher as unknown as typeof fetch,
    });

    expect('capability' in result).toBe(true);
    if ('capability' in result) {
      expect(result.capability.available).toBe(false);
      expect(result.capability.blocker).toBe('content_load_failed');
    }
  });
});
