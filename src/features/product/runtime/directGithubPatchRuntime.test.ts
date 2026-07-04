/**
 * Direct GitHub Patch Runtime Tests
 */

import { describe, expect, it } from 'vitest';
import {
  isDirectPatchIntent,
  detectDirectPatchTarget,
  checkDirectPatchCapability,
  generateDirectPatchContent,
  executeDirectPatchRuntime,
  buildDirectPatchPlan,
} from './directGithubPatchRuntime';
import {
  isDirectPatchAllowedPath,
  isDirectPatchForbiddenPath,
} from './directGithubPatchTypes';

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

  it('allows doc/*.md files', () => {
    expect(isDirectPatchAllowedPath('doc/guide.md')).toBe(true);
  });

  it('allows documentation/*.md files', () => {
    expect(isDirectPatchAllowedPath('documentation/readme.md')).toBe(true);
  });

  it('rejects src/*.ts files', () => {
    expect(isDirectPatchAllowedPath('src/index.ts')).toBe(false);
    expect(isDirectPatchAllowedPath('src/App.tsx')).toBe(false);
  });

  it('rejects android files', () => {
    expect(isDirectPatchAllowedPath('android/app/build.gradle')).toBe(false);
  });

  it('rejects scripts files', () => {
    expect(isDirectPatchAllowedPath('scripts/deploy.sh')).toBe(false);
  });

  it('rejects workflow files', () => {
    expect(isDirectPatchAllowedPath('.github/workflows/ci.yml')).toBe(false);
  });

  it('rejects package.json', () => {
    expect(isDirectPatchAllowedPath('package.json')).toBe(false);
  });
});

describe('isDirectPatchForbiddenPath', () => {
  it('marks src files as forbidden', () => {
    expect(isDirectPatchForbiddenPath('src/index.ts')).toBe(true);
    expect(isDirectPatchForbiddenPath('src/components/App.tsx')).toBe(true);
  });

  it('marks android files as forbidden', () => {
    expect(isDirectPatchForbiddenPath('android/build.gradle')).toBe(true);
  });

  it('marks scripts as forbidden', () => {
    expect(isDirectPatchForbiddenPath('scripts/test.sh')).toBe(true);
  });

  it('marks workflow files as forbidden', () => {
    expect(isDirectPatchForbiddenPath('.github/workflows/build.yml')).toBe(true);
  });

  it('marks README.md as NOT forbidden', () => {
    expect(isDirectPatchForbiddenPath('README.md')).toBe(false);
  });
});

describe('isDirectPatchIntent', () => {
  it('detects README change intent', () => {
    expect(isDirectPatchIntent('Passe README an und füge 🐥 in den Titel ein')).toBe(true);
    expect(isDirectPatchIntent('Update the README title')).toBe(true);
  });

  it('detects docs change intent', () => {
    expect(isDirectPatchIntent('Aktualisiere die Dokumentation')).toBe(true);
    expect(isDirectPatchIntent('Update the docs')).toBe(true);
  });

  it('detects changelog intent', () => {
    expect(isDirectPatchIntent('Füge einen Changelog-Eintrag hinzu')).toBe(true);
  });

  it('detects content addition intent', () => {
    expect(isDirectPatchIntent('Füge einen Hinweis am Ende hinzu')).toBe(true);
  });

  it('does NOT flag complex code tasks', () => {
    expect(isDirectPatchIntent('Implementiere eine neue API')).toBe(false);
    expect(isDirectPatchIntent('Baue die Komponente')).toBe(false);
    expect(isDirectPatchIntent('Schreibe Tests für die Funktion')).toBe(false);
  });

  it('does NOT flag refactoring tasks', () => {
    expect(isDirectPatchIntent('Refaktoriere den Code')).toBe(false);
  });
});

describe('detectDirectPatchTarget', () => {
  const repoFiles = [
    'README.md',
    'docs/intro.md',
    'docs/api.md',
    'src/index.ts',
    'package.json',
  ];

  it('detects README.md for readme instructions', () => {
    expect(detectDirectPatchTarget('Update the README', repoFiles)).toBe('README.md');
  });

  it('detects docs file for docs instructions', () => {
    const target = detectDirectPatchTarget('Update the docs', repoFiles);
    expect(target).toMatch(/^docs\/.*\.md$/);
  });

  it('returns null when no matching file found', () => {
    expect(detectDirectPatchTarget('Update some file', ['src/index.ts'])).toBe(null);
  });

  it('returns null when repo has no matching files', () => {
    expect(detectDirectPatchTarget('Update the README', ['src/index.ts'])).toBe(null);
  });
});

describe('checkDirectPatchCapability', () => {
  const repoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    files: ['README.md', 'docs/intro.md'],
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
});

describe('generateDirectPatchContent', () => {
  const baseReadme = `# Project Title

This is the project description.

## Installation

Instructions here.
`;

  it('generates patch for title emoji addition', () => {
    const result = generateDirectPatchContent(
      baseReadme,
      'Füge 🐥 in den Titel ein',
    );
    expect(result).not.toBeNull();
    expect(result?.content).toContain('🐥');
    expect(result?.summary).toContain('Added');
  });

  it('generates patch for title update', () => {
    const result = generateDirectPatchContent(
      baseReadme,
      'Update title to New Project Name',
    );
    expect(result).not.toBeNull();
    expect(result?.content).toContain('New Project Name');
    expect(result?.content).not.toContain('Project Title');
  });

  it('returns null for unsupported instructions', () => {
    const result = generateDirectPatchContent(
      baseReadme,
      'Implementiere eine API',
    );
    expect(result).toBeNull();
  });

  it('adds content at end', () => {
    const result = generateDirectPatchContent(
      baseReadme,
      'Füge "More info" am Ende hinzu',
    );
    expect(result).not.toBeNull();
    expect(result?.content).toContain('More info');
  });
});

describe('executeDirectPatchRuntime', () => {
  const repoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    files: ['README.md'],
  };

  it('returns success for valid README patch', () => {
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Füge 🐥 in den Titel ein',
      baseContent: '# My Project\n\nDescription.',
      targetPath: 'README.md',
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.nextAction).toBe('preview_diff');
      expect(result.targetPath).toBe('README.md');
      expect(result.proposedContent).toContain('🐥');
    }
  });

  it('returns failure for forbidden path', () => {
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Update the file',
      baseContent: 'const x = 1;',
      targetPath: 'src/index.ts',
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.blocker).toBe('unsafe_target');
    }
  });

  it('returns failure for empty patch', () => {
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Keep everything the same',
      baseContent: '# Title',
      targetPath: 'README.md',
    });
    expect(result.ok).toBe(false);
  });

  it('rejects patch with secrets', () => {
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Add this token: ghp_abcdefghijklmnopqrstuvwxyz1234567890abcd',
      baseContent: '# Token',
      targetPath: 'README.md',
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.blocker).toBe('unsafe_target');
    }
  });
});

describe('buildDirectPatchPlan', () => {
  const repoContext = {
    owner: 'test',
    name: 'repo',
    branch: 'main',
    files: ['README.md'],
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
      expect(result.result.ok).toBe(true);
    }
  });
});
