import { describe, expect, it } from 'vitest';

import { renderKeepAChangelog } from './changelogRuntime';
import { compareContractSurfaces } from './contractDriftSentinelRuntime';
import { buildImpactReport, findImporters } from './dependencyImpactRuntime';
import { buildEvidenceLineage } from './evidenceLineageRuntime';
import { buildMergeBlastRadiusGate } from './mergeBlastRadiusGateRuntime';
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

  it('builds evidence lineage in deterministic time order', () => {
    const lineages = buildEvidenceLineage([
      { id: 'b', source: 'runtime', scope: 'draft-pr', message: 'prepared', at: 20 },
      { id: 'a', source: 'api', scope: 'draft-pr', message: 'requested', at: 10 },
    ]);
    expect(lineages[0].nodes.map((node) => node.id)).toEqual(['a', 'b']);
    expect(lineages[0].nodes[1].parentId).toBe('a');
  });

  it('detects contract drift against the authoritative surface', () => {
    const report = compareContractSurfaces(
      { name: 'backend', fields: [{ name: 'ok', type: 'boolean', required: true }] },
      [{ name: 'frontend', fields: [{ name: 'ok', type: 'string', required: true }] }],
    );
    expect(report.aligned).toBe(false);
    expect(report.findings[0].kind).toBe('type-mismatch');
  });

  it('raises blast radius for critical high-impact changes', () => {
    const result = buildMergeBlastRadiusGate({
      changedPaths: ['backend/auth/routes.py', '.github/workflows/release.yml'],
      totalAddedLines: 900,
      totalRemovedLines: 200,
      dependencyImpact: [{ path: 'backend/auth/routes.py', importers: Array.from({ length: 12 }, (_, index) => `src/${index}.ts`), importerCount: 12, risk: 'high' }],
      testEvidenceReady: false,
      securityEvidenceReady: false,
      releaseEvidenceReady: false,
    });
    expect(['high', 'critical']).toContain(result.level);
    expect(result.requiresAdditionalEvidence).toBe(true);
  });
});
