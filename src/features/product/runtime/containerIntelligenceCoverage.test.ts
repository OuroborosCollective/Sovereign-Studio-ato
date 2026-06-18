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
  });

  it('keeps generated file review as the current reference pattern', () => {
    const generatedFiles = CONTAINER_INTELLIGENCE_COVERAGE.find((entry) => entry.id === 'generated-files');
    expect(generatedFiles?.status).toBe('covered');
    expect(generatedFiles?.missingAreas).toEqual([]);
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
});
