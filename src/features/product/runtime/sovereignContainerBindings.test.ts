import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  getSovereignContainerContract,
  type SovereignContainerId,
  validateSovereignContainerContracts,
} from './sovereignContainerContracts';

function readSource(path: string): string {
  return readFileSync(join(process.cwd(), path), 'utf8');
}

function expectContractLookup(source: string, id: SovereignContainerId): void {
  expect(source).toMatch(new RegExp(`getSovereignContainerContract\\([\"']${id}[\"']\\)`));
}

describe('sovereign container source bindings', () => {
  it('keeps the container contract valid before checking source bindings', () => {
    const report = validateSovereignContainerContracts();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
  });

  it('binds BuilderContainer to the builder container contract', () => {
    const source = readSource('src/features/product/containers/BuilderContainer.tsx');
    const contract = getSovereignContainerContract('builder');

    expectContractLookup(source, 'builder');
    expect(source).toContain('builderContainerContract.rootClass');
    expect(source).toContain('builderContainerContract.dataRole');
    expect(source).toContain('builderContainerContract.testId');
    expect(source).toContain('builderContainerContract.ariaLabel');
    expect(contract.testId).toBe('builder-container');
  });

  it('binds the global runtime monitor to the monitor container contract', () => {
    const source = readSource('src/global-runtime-monitor.tsx');
    const contract = getSovereignContainerContract('global-runtime-monitor');

    expectContractLookup(source, 'global-runtime-monitor');
    expect(source).toContain('monitorContainerContract.rootClass');
    expect(source).toContain('monitorContainerContract.dataRole');
    expect(source).toContain('monitorContainerContract.testId');
    expect(source).toContain('monitorContainerContract.ariaLabel');
    expect(contract.testId).toBe('global-runtime-monitor');
  });

  it('keeps repo snapshot visible and testable while its access-field file remains guarded', () => {
    const source = readSource('src/features/product/containers/RepoSnapshotContainer.tsx');
    const contract = getSovereignContainerContract('repo-snapshot');

    expect(source).toContain('Repository Snapshot');
    expectContractLookup(source, 'repo-snapshot');
    expect(source).toContain('repoContainerContract.rootClass');
    expect(source).toContain('repoContainerContract.dataRole');
    expect(source).toContain('repoContainerContract.testId');
    expect(source).toContain('repoContainerContract.ariaLabel');
    expect(contract.testId).toBe('repo-snapshot-container');
  });
});
