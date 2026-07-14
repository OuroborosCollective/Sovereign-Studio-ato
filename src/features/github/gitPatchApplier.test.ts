import { describe, expect, it, vi } from 'vitest';
import { applyGitPatch, convertPatchResultToDiffReport, validateGitPatchRequest } from './gitPatchApplier';

describe('gitPatchApplier - validateGitPatchRequest', () => {
  const validRequest = {
    repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
    branch: 'feature-branch',
    filePath: 'src/test.ts',
    blocks: [{ search: 'old', replace: 'new' }],
    commitMessage: 'Update test.ts',
    token: 'fake-token',
  };

  it('validates a correct request', () => {
    const report = validateGitPatchRequest(validRequest);
    expect(report.valid).toBe(true);
    expect(report.errors).toHaveLength(0);
  });

  it('rejects repositories not in allowlist', () => {
    const report = validateGitPatchRequest({
      ...validRequest,
      repoUrl: 'https://github.com/other/repo',
    });
    expect(report.valid).toBe(false);
    expect(report.errors[0]).toContain('Repo not in allowlist');
  });

  it('rejects protected branches: main', () => {
    const report = validateGitPatchRequest({
      ...validRequest,
      branch: 'main',
    });
    expect(report.valid).toBe(false);
    expect(report.errors[0]).toContain('is protected');
  });

  it('rejects protected branches: master', () => {
    const report = validateGitPatchRequest({
      ...validRequest,
      branch: 'master',
    });
    expect(report.valid).toBe(false);
    expect(report.errors[0]).toContain('is protected');
  });

  it('rejects protected branches: production', () => {
    const report = validateGitPatchRequest({
      ...validRequest,
      branch: 'production',
    });
    expect(report.valid).toBe(false);
    expect(report.errors[0]).toContain('is protected');
  });

  it('rejects protected branches: release/*', () => {
    const report = validateGitPatchRequest({
      ...validRequest,
      branch: 'release/v1.0.0',
    });
    expect(report.valid).toBe(false);
    expect(report.errors[0]).toContain('is protected');
  });

  it('rejects invalid file paths', () => {
    const report = validateGitPatchRequest({
      ...validRequest,
      filePath: '../outside.ts',
    });
    expect(report.valid).toBe(false);
    expect(report.errors[0]).toContain('Invalid filePath');
  });

  it('rejects empty blocks', () => {
    const report = validateGitPatchRequest({
      ...validRequest,
      blocks: [],
    });
    expect(report.valid).toBe(false);
    expect(report.errors[0]).toContain('At least one patch block is required');
  });

  it('detects secret-like content in blocks', () => {
    const report = validateGitPatchRequest({
      ...validRequest,
      blocks: [{ search: 'old', replace: 'Authorization: Bearer secret-token' }],
    });
    expect(report.valid).toBe(false);
    expect(report.errors[0]).toContain('secret-like content detected');
  });
});

describe('gitPatchApplier - diff report contract', () => {
  it('uses the typed modified and unchanged diff kinds', () => {
    const modified = convertPatchResultToDiffReport('src/app.ts', 'old', {
      ok: true,
      dryRun: true,
      appliedBlocks: 1,
      newContent: 'new',
    });
    const unchanged = convertPatchResultToDiffReport('src/app.ts', 'same', {
      ok: true,
      dryRun: true,
      appliedBlocks: 1,
      newContent: 'same',
    });

    expect(modified.files[0].kind).toBe('modified');
    expect(modified.modified).toBe(1);
    expect(unchanged.files[0].kind).toBe('unchanged');
    expect(unchanged.unchanged).toBe(1);
  });
});

describe('gitPatchApplier - applyGitPatch', () => {
  const mockToken = 'ghp_mock_token';
  const mockRepo = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato';
  const mockBranch = 'feature-fix';
  const mockFilePath = 'src/app.ts';
  const mockContent = 'export const VERSION = "1.0.0";\nexport const APP_NAME = "Studio";';
  
  // Helper to create a mock fetch
  const createMockFetch = (responses: Record<string, { status: number, body: any }>) => {
    return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const response = responses[url] || responses[url.split('?')[0]];
      if (!response) return Promise.resolve({ ok: false, status: 404, text: () => Promise.resolve('Not Found') });
      
      return Promise.resolve({
        ok: response.status >= 200 && response.status < 300,
        status: response.status,
        json: () => Promise.resolve(response.body),
        text: () => Promise.resolve(JSON.stringify(response.body)),
      });
    });
  };

  it('successfully applies a patch in dryRun mode', async () => {
    const mockFetch = createMockFetch({
      'https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/contents/src/app.ts': {
        status: 200,
        body: {
          content: btoa(mockContent),
          sha: 'old-sha',
          encoding: 'base64',
        },
      },
    });

    const result = await applyGitPatch({
      repoUrl: mockRepo,
      branch: mockBranch,
      filePath: mockFilePath,
      blocks: [{ search: 'VERSION = "1.0.0"', replace: 'VERSION = "1.1.0"' }],
      commitMessage: 'Bump version',
      token: mockToken,
      dryRun: true,
      fetcher: mockFetch as any,
    });

    expect(result.ok).toBe(true);
    expect(result.dryRun).toBe(true);
    expect(result.appliedBlocks).toBe(1);
    expect(result.newContent).toContain('VERSION = "1.1.0"');
  });

  it('fails when SHA mismatch occurs', async () => {
    const mockFetch = createMockFetch({
      'https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/contents/src/app.ts': {
        status: 200,
        body: {
          content: btoa(mockContent),
          sha: 'actual-sha',
          encoding: 'base64',
        },
      },
    });

    const result = await applyGitPatch({
      repoUrl: mockRepo,
      branch: mockBranch,
      filePath: mockFilePath,
      blocks: [{ search: 'VERSION', replace: 'VER' }],
      commitMessage: 'Change',
      token: mockToken,
      expectedSha: 'expected-sha',
      fetcher: mockFetch as any,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('SHA mismatch');
  });

  it('fails when search string is not found', async () => {
    const mockFetch = createMockFetch({
      'https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/contents/src/app.ts': {
        status: 200,
        body: {
          content: btoa(mockContent),
          sha: 'sha',
          encoding: 'base64',
        },
      },
    });

    const result = await applyGitPatch({
      repoUrl: mockRepo,
      branch: mockBranch,
      filePath: mockFilePath,
      blocks: [{ search: 'NON_EXISTENT', replace: 'NEW' }],
      commitMessage: 'Change',
      token: mockToken,
      fetcher: mockFetch as any,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('search string found 0 times');
  });

  it('fails when search string matches multiple times', async () => {
    // Content where "const shared" appears 3 times
    const contentWithDuplicates = 'const shared = 1;\nconst shared = 2;\nconst shared = 3;';
    const mockFetch = createMockFetch({
      'https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/contents/src/app.ts': {
        status: 200,
        body: {
          content: btoa(contentWithDuplicates),
          sha: 'sha',
          encoding: 'base64',
        },
      },
    });

    const result = await applyGitPatch({
      repoUrl: mockRepo,
      branch: mockBranch,
      filePath: mockFilePath,
      blocks: [{ search: 'const shared', replace: 'const renamed' }],
      commitMessage: 'Change',
      token: mockToken,
      fetcher: mockFetch as any,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('found 3 times');
  });

  it('dryRun mode does not make PUT request', async () => {
    let putWasCalled = false;
    const mockFetch = createMockFetch({
      'https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/contents/src/app.ts': {
        status: 200,
        body: {
          content: btoa(mockContent),
          sha: 'old-sha',
          encoding: 'base64',
        },
      },
    });

    // Wrap the fetch to track PUT calls
    const trackingFetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        putWasCalled = true;
      }
      return mockFetch(url, init);
    });

    const result = await applyGitPatch({
      repoUrl: mockRepo,
      branch: mockBranch,
      filePath: mockFilePath,
      blocks: [{ search: 'VERSION = "1.0.0"', replace: 'VERSION = "1.1.0"' }],
      commitMessage: 'Bump version',
      token: mockToken,
      dryRun: true,
      fetcher: trackingFetch as any,
    });

    expect(result.ok).toBe(true);
    expect(result.dryRun).toBe(true);
    expect(result.newContent).toBeDefined();
    expect(result.commitSha).toBeUndefined();
    expect(putWasCalled).toBe(false);
  });

  it('masks GitHub tokens in error messages', async () => {
    const mockFetch = createMockFetch({
      'https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/contents/src/app.ts': {
        status: 403,
        body: {
          message: 'Bad credentials - ghp_secretToken123456789',
        },
      },
    });

    const result = await applyGitPatch({
      repoUrl: mockRepo,
      branch: mockBranch,
      filePath: mockFilePath,
      blocks: [{ search: 'old', replace: 'new' }],
      commitMessage: 'Change',
      token: mockToken,
      fetcher: mockFetch as any,
    });

    expect(result.ok).toBe(false);
    expect(result.error).not.toContain('ghp_secretToken123456789');
    expect(result.error).toContain('ghp_****');
  });
});
