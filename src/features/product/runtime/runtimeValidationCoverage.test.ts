import { describe, expect, it } from 'vitest';
import {
  RUNTIME_VALIDATION_TARGETS,
  assertRuntimeValidationCoverageHealthy,
  buildRuntimeValidationCoverageReport,
} from './runtimeValidationCoverage';

describe('runtimeValidationCoverage', () => {
  it('keeps every runtime target mapped to a test and integration point', () => {
    const report = buildRuntimeValidationCoverageReport();
    expect(report.healthy).toBe(true);
    expect(report.missing).toBe(0);
    expect(report.covered).toBe(RUNTIME_VALIDATION_TARGETS.length);
    expect(() => assertRuntimeValidationCoverageHealthy(report)).not.toThrow();

    for (const target of report.targets) {
      expect(target.runtimePath).toMatch(/\.ts$/);
      expect(target.testPath).toMatch(/\.test\.ts$/);
      expect(target.integrationPoint.length).toBeGreaterThan(0);
    }
  });
});
