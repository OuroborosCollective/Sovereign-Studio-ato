import { describe, expect, it } from 'vitest';
import {
  executeDirectPatchRuntime,
  generateDirectPatchContent,
} from './directGithubPatchRuntime';
import type { DirectPatchRepoContext } from './directGithubPatchTypes';

const repoContext: DirectPatchRepoContext = {
  owner: 'test-owner',
  name: 'test-repo',
  branch: 'main',
  filePaths: ['README.md'],
};

describe('Direct GitHub Patch README title operations', () => {
  it('adds the requested emoji to the first README H1 instead of appending content', () => {
    const result = generateDirectPatchContent(
      '# Sovereign Studio\n\nBeschreibung.\n',
      'Ok bearbeite mein readme füge dem Titel ein küken 🐥 hinzu!',
    );

    expect(result).not.toBeNull();
    expect(result?.content).toContain('# Sovereign Studio 🐥');
    expect(result?.content).not.toContain('\n\nein küken 🐥\n');
    expect(result?.summary).toContain('README title');
    expect(result?.summary).not.toBe('Added content at the end.');
  });

  it('does not alter subheadings when a title marker is requested', () => {
    const result = generateDirectPatchContent(
      'Intro only\n\n## Sovereign Studio\n',
      'Füge 🐥 in den Titel ein',
    );

    expect(result).toBeNull();
  });

  it('returns a reviewable direct patch result for the video README title request', () => {
    const result = executeDirectPatchRuntime({
      repoContext,
      instruction: 'Ok bearbeite mein readme füge dem Titel ein küken 🐥 hinzu!',
      baseContent: '# Sovereign Studio\n\nBeschreibung.',
      targetPath: 'README.md',
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.targetPath).toBe('README.md');
      expect(result.nextAction).toBe('preview_diff');
      expect(result.proposedContent).toContain('# Sovereign Studio 🐥');
      expect(result.patchSummary).toContain('README title');
    }
  });
});
