import { describe, expect, it } from 'vitest';

import { compareContractSurfaces } from './contractDriftSentinelRuntime';
import { buildImpactReport, findImporters } from './dependencyImpactRuntime';
import { buildEvidenceLineage } from './evidenceLineageRuntime';
import { buildMergeBlastRadiusGate } from './mergeBlastRadiusGateRuntime';
import { validateMissionSpecificity } from './missionValidatorRuntime';
import { narrativeMap } from './semanticDiffNarratorRuntime';

describe('architecture enhancement runtimes', () => {
  it('finds deterministic importers and marks the source set as bounded', () => {
    const files = [
      { path: 'src/auth.ts', content: 'export const auth = true;' },
      { path: 'src/a.ts', content: "import { auth } from './auth';" },
      { path: 'src/b.ts', content: "const auth = require('./auth');" },
    ];
    expect(findImporters('src/auth.ts', files)).toEqual(['src/a.ts', 'src/b.ts']);
    const report = buildImpactReport(['src/auth.ts'], files, { complete: false });
    expect(report.byTarget['src/auth.ts']).toMatchObject({ importerCount: 2, risk: 'low', complete: false });
  });

  it('warns for an unbounded mission without verification evidence', () => {
    const result = validateMissionSpecificity('refactor the whole codebase');
    expect(result.score).toBeLessThan(40);
    expect(result.specificEnough).toBe(false);
    expect(result.questions.length).toBeGreaterThan(0);
  });

  it('maps only evidence-backed semantic narratives', () => {
    expect(narrativeMap({
      ok: true,
      status: 'ready',
      diffText: 'diff',
      narratives: [{ path: 'src/a.ts', narration: 'Updates authentication validation.' }],
    })).toEqual({ 'src/a.ts': 'Updates authentication validation.' });
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
      dependencyImpact: [{
        targetPath: 'backend/auth/routes.py',
        importerPaths: Array.from({ length: 12 }, (_, index) => `src/${index}.ts`),
        importerCount: 12,
        scannedFileCount: 12,
        complete: true,
        risk: 'high',
      }],
      testEvidenceReady: false,
      securityEvidenceReady: false,
      releaseEvidenceReady: false,
    });
    expect(['high', 'critical']).toContain(result.level);
    expect(result.requiresAdditionalEvidence).toBe(true);
  });
});
