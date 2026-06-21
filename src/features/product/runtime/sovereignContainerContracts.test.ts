import { describe, expect, it } from 'vitest';

import {
  SOVEREIGN_CONTAINER_CONTRACTS,
  assertSovereignContainerContractsValid,
  getSovereignContainerContract,
  validateSovereignContainerContracts,
} from './sovereignContainerContracts';

describe('sovereign container contract list', () => {
  it('validates the shipped list', () => {
    const report = validateSovereignContainerContracts();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
    expect(() => assertSovereignContainerContractsValid()).not.toThrow();
  });

  it('maps the main workspace areas', () => {
    expect(getSovereignContainerContract('repo-snapshot').testId).toBe('repo-snapshot-container');
    expect(getSovereignContainerContract('builder').testId).toBe('builder-container');
    expect(getSovereignContainerContract('global-runtime-monitor').testId).toBe('global-runtime-monitor');
  });

  it('keeps roles and test ids unique', () => {
    const dataRoles = SOVEREIGN_CONTAINER_CONTRACTS.map((contract) => contract.dataRole);
    const testIds = SOVEREIGN_CONTAINER_CONTRACTS.map((contract) => contract.testId);

    expect(new Set(dataRoles).size).toBe(dataRoles.length);
    expect(new Set(testIds).size).toBe(testIds.length);
  });

  it('keeps class and aria metadata available', () => {
    for (const contract of SOVEREIGN_CONTAINER_CONTRACTS) {
      expect(contract.rootClass).toContain('sovereign-container');
      expect(contract.rootClass).toContain('sovereign-');
      expect(contract.dataRole).toMatch(/^sovereign-container-/);
      expect(contract.ariaLabel.length).toBeGreaterThan(0);
    }
  });
});
