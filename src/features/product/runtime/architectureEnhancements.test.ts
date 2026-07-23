import { describe, expect, it } from 'vitest';

import { renderKeepAChangelog } from './changelogRuntime';
import { buildImpactReport, findImporters } from './dependencyImpactRuntime';
import { validateMissionLocally } from './preflightMissionRuntime';
import { buildDeterministicNarrations } from './semanticDiffNarratorRuntime';

describe('architecture enhancement runtimes', () => {
  it('finds deterministic relative importers and risk radius', () => {
    const files = [
      { path: 'src/auth.ts', content: 'export const auth = true;' },
      { path: 'src/a.ts', content: "import { auth } from './auth';" },
      { path: 'src/b.ts', content: "const auth = require('./auth');" },
    ];
    expect(findImporters('src/auth.ts', files)).toEqual(['src/a.ts', 'src/b.ts']);
    expect(buildImpactReport(['src/auth.ts'], files)[0]).toMatchObject({ importerCount: 2, risk: 'low' });
  });

  it('warns for unbounded missions without evidence', () => {
    const result = validateMissionLocally('refactor the whole codebase');
    expect(result.confidence).toBeLessThan(40);
    expect(result.canStart).toBe(false);
    expect(result.questions.length).toBeGreaterThan(0);
  });

  it('renders evidence-bound changelog groups', () => {
    const output = renderKeepAChangelog('1.2.3', '2026-07-23', [
      { sha: 'abcdef1234567890', message: 'feat: add mission validator' },
      { sha: '123456abcdef7890', message: 'fix: repair route fallback' },
    ]);
    expect(output).toContain('### Added');
    expect(output).toContain('### Fixed');
    expect(output).toContain('abcdef123456');
  });

  it('uses deterministic narration without claiming model evidence', () => {
    const narrations = buildDeterministicNarrations([{
      path: 'src/new.ts',
      kind: 'created',
      oldLineCount: 0,
      newLineCount: 12,
      addedLines: 12,
      removedLines: 0,
      changed: true,
      summary: 'created',
      preview: '+content',
    }]);
    expect(narrations).toEqual([{ path: 'src/new.ts', sentence: 'Creates src/new.ts with 12 lines.', source: 'deterministic' }]);
  });
});
