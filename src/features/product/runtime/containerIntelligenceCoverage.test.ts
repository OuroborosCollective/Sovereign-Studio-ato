import { describe, expect, it } from 'vitest';
import {
  assertContainerIntelligenceCoverageValid,
  buildContainerIntelligenceCoverageReport,
  CONTAINER_INTELLIGENCE_COVERAGE,
  listContainerIntelligenceGaps,
} from './containerIntelligenceCoverage';

describe('containerIntelligenceCoverage', () => {
  it('keeps the bundled container intelligence registry valid', () => {
    expect(() => assertContainerIntelligenceCoverageValid()).not.toThrow();
    const report = buildContainerIntelligenceCoverageReport();
    expect(report.valid).toBe(true);
    expect(report.entries.length).toBeGreaterThan(5);
    expect(report.summary).toContain('partial');
  });

  it('does not claim every container is fully covered yet', () => {
    const gaps = listContainerIntelligenceGaps();
    expect(gaps.length).toBeGreaterThan(0);
    expect(gaps.some((entry) => entry.id === 'telemetry')).toBe(true);
    expect(gaps.some((entry) => entry.id === 'remote-memory')).toBe(true);
    expect(gaps.some((entry) => entry.id === 'mobile-coach')).toBe(true);
    expect(gaps.some((entry) => entry.id === 'sequential-runtime')).toBe(true);
  });

  it('keeps generated file review as the current reference pattern', () => {
    const generatedFiles = CONTAINER_INTELLIGENCE_COVERAGE.find((entry) => entry.id === 'generated-files');
    expect(generatedFiles?.status).toBe('covered');
    expect(generatedFiles?.missingAreas).toEqual([]);
  });

  it('keeps mobile-workbench as partial (needs telemetry and self-review)', () => {
    const mobileWorkbench = CONTAINER_INTELLIGENCE_COVERAGE.find((entry) => entry.id === 'mobile-workbench');
    expect(mobileWorkbench?.status).toBe('partial');
    expect(mobileWorkbench?.coveredAreas).toContain('pattern-rules');
    expect(mobileWorkbench?.coveredAreas).toContain('tests');
    expect(mobileWorkbench?.coveredAreas).toContain('runtime-checks');
    expect(mobileWorkbench?.coveredAreas).toContain('ui-guidance');
    expect(mobileWorkbench?.missingAreas).toContain('telemetry');
    expect(mobileWorkbench?.missingAreas).toContain('self-review');
  });

  it('rejects duplicate container ids', () => {
    const duplicate = [CONTAINER_INTELLIGENCE_COVERAGE[0], { ...CONTAINER_INTELLIGENCE_COVERAGE[1], id: CONTAINER_INTELLIGENCE_COVERAGE[0].id }];
    const report = buildContainerIntelligenceCoverageReport(duplicate);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('Duplicate container coverage id');
  });

  it('rejects an entry that claims covered while still missing areas', () => {
    const broken = [{
      ...CONTAINER_INTELLIGENCE_COVERAGE[0],
      status: 'covered' as const,
      missingAreas: ['pattern-rules' as const],
    }];
    const report = buildContainerIntelligenceCoverageReport(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('covered but still has missing areas');
  });

  it('rejects an entry marked covered that is missing any REQUIRED_AREAS', () => {
    // 'covered' means ALL REQUIRED_AREAS must be present
    const partialEntry = CONTAINER_INTELLIGENCE_COVERAGE.find((e) => e.status === 'partial');
    if (!partialEntry) return; // Skip if no partial entries exist
    const broken = [{
      ...partialEntry,
      status: 'covered' as const,
      coveredAreas: partialEntry.coveredAreas,
      missingAreas: [],
    }];
    const report = buildContainerIntelligenceCoverageReport(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain("is marked 'covered' but missing required areas");
  });

  it('rejects partial status without missing areas', () => {
    const broken = [{
      ...CONTAINER_INTELLIGENCE_COVERAGE[0],
      status: 'partial' as const,
      missingAreas: [],
    }];
    const report = buildContainerIntelligenceCoverageReport(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('not covered but has no missing areas');
  });

  it('rejects duplicate container paths', () => {
    const duplicate = [CONTAINER_INTELLIGENCE_COVERAGE[0], { ...CONTAINER_INTELLIGENCE_COVERAGE[1], containerPath: CONTAINER_INTELLIGENCE_COVERAGE[0].containerPath }];
    const report = buildContainerIntelligenceCoverageReport(duplicate);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('Duplicate container path');
  });

  it('rejects unknown areas in coveredAreas or missingAreas', () => {
    const broken: typeof CONTAINER_INTELLIGENCE_COVERAGE = [{
      ...CONTAINER_INTELLIGENCE_COVERAGE[0],
      coveredAreas: ['runtime-checks', 'unknown-area' as any],
      missingAreas: [],
    }];
    const report = buildContainerIntelligenceCoverageReport(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('unknown area');
  });

  it('rejects overlapping covered and missing areas', () => {
    const broken: typeof CONTAINER_INTELLIGENCE_COVERAGE = [{
      ...CONTAINER_INTELLIGENCE_COVERAGE[0],
      coveredAreas: ['runtime-checks', 'tests'] as any,
      missingAreas: ['runtime-checks', 'pattern-rules'] as any,
    }];
    const report = buildContainerIntelligenceCoverageReport(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('cannot be both covered and missing');
  });

  it('reports correct counts', () => {
    const report = buildContainerIntelligenceCoverageReport();
    const covered = report.entries.filter((e) => e.status === 'covered');
    const partial = report.entries.filter((e) => e.status === 'partial');
    const missing = report.entries.filter((e) => e.status === 'missing');
    expect(report.coveredCount).toBe(covered.length);
    expect(report.partialCount).toBe(partial.length);
    expect(report.missingCount).toBe(missing.length);
    expect(covered.length + partial.length + missing.length).toBe(report.entries.length);
  });

  it('contains all required containers', () => {
    const requiredIds = [
      'repo-snapshot',
      'builder',
      'generated-files',
      'diff-preview',
      'workflow',
      'remote-memory',
      'pattern-memory',
      'telemetry',
      'health',
      'runtime-coverage',
      'findings',
      'sequential-runtime',
      'mobile-workbench',
      'mobile-coach',
      'bridge-validation',
      'code-creation',
    ];
    const report = buildContainerIntelligenceCoverageReport();
    for (const id of requiredIds) {
      expect(report.entries.some((e) => e.id === id)).toBe(true);
    }
  });

  it('assertContainerIntelligenceCoverageValid throws for invalid registry', () => {
    const broken = [{
      ...CONTAINER_INTELLIGENCE_COVERAGE[0],
      status: 'covered' as const,
      missingAreas: ['pattern-rules' as const],
    }];
    expect(() => assertContainerIntelligenceCoverageValid(broken)).toThrow();
  });

  it('listContainerIntelligenceGaps throws for invalid registry', () => {
    const broken = [{
      ...CONTAINER_INTELLIGENCE_COVERAGE[0],
      id: '',
    }];
    expect(() => listContainerIntelligenceGaps(broken)).toThrow();
  });
});
