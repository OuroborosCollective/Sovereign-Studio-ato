import { describe, expect, it } from 'vitest';

import {
  SOVEREIGN_ACTION_CONTRACTS,
  SOVEREIGN_ACTION_DRAFT_PR,
  SOVEREIGN_ACTION_LOAD_REPO,
  SOVEREIGN_ACTION_REPAIR_LOG,
  assertSovereignActionContractsValid,
  getSovereignActionContract,
  validateSovereignActionContracts,
} from './sovereignActionContracts';

describe('sovereign action contracts', () => {
  it('validates the shipped list', () => {
    const report = validateSovereignActionContracts();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
    expect(() => assertSovereignActionContractsValid()).not.toThrow();
  });

  it('has unique ids, dataRoles, and testIds', () => {
    const ids = SOVEREIGN_ACTION_CONTRACTS.map((contract) => contract.id);
    const dataRoles = SOVEREIGN_ACTION_CONTRACTS.map((contract) => contract.dataRole);
    const testIds = SOVEREIGN_ACTION_CONTRACTS.map((contract) => contract.testId);

    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(dataRoles).size).toBe(dataRoles.length);
    expect(new Set(testIds).size).toBe(testIds.length);
  });

  it('includes all required actions', () => {
    expect(getSovereignActionContract('load-repo')).toBeDefined();
    expect(getSovereignActionContract('save-session')).toBeDefined();
    expect(getSovereignActionContract('restore-session')).toBeDefined();
    expect(getSovereignActionContract('clear-view')).toBeDefined();
    expect(getSovereignActionContract('analyze-mission')).toBeDefined();
    expect(getSovereignActionContract('start-task')).toBeDefined();
    expect(getSovereignActionContract('repair-log')).toBeDefined();
    expect(getSovereignActionContract('draft-pr')).toBeDefined();
    expect(getSovereignActionContract('monitor-toggle')).toBeDefined();
  });

  it('has non-empty labels and aria labels', () => {
    for (const contract of SOVEREIGN_ACTION_CONTRACTS) {
      expect(contract.label.length).toBeGreaterThan(0);
      expect(contract.ariaLabel.length).toBeGreaterThan(0);
    }
  });

  it('has valid action kinds', () => {
    const validKinds = ['primary', 'secondary', 'destructive', 'diagnostic', 'navigation'];

    for (const contract of SOVEREIGN_ACTION_CONTRACTS) {
      expect(validKinds).toContain(contract.kind);
    }
  });
});

describe('sovereign action contracts: load-repo', () => {
  it('has correct id', () => {
    expect(SOVEREIGN_ACTION_LOAD_REPO.id).toBe('load-repo');
  });

  it('has correct testId', () => {
    expect(SOVEREIGN_ACTION_LOAD_REPO.testId).toBe('repo-snapshot__load-repo');
  });

  it('has correct dataRole', () => {
    expect(SOVEREIGN_ACTION_LOAD_REPO.dataRole).toBe('action-load-repo');
  });

  it('is primary kind', () => {
    expect(SOVEREIGN_ACTION_LOAD_REPO.kind).toBe('primary');
  });

  it('does not require repo', () => {
    expect(SOVEREIGN_ACTION_LOAD_REPO.requiresRepo).toBe(false);
  });

  it('can be busy', () => {
    expect(SOVEREIGN_ACTION_LOAD_REPO.canBeBusy).toBe(true);
  });
});

describe('sovereign action contracts: draft-pr', () => {
  it('has correct id', () => {
    expect(SOVEREIGN_ACTION_DRAFT_PR.id).toBe('draft-pr');
  });

  it('has correct testId', () => {
    expect(SOVEREIGN_ACTION_DRAFT_PR.testId).toBe('builder__draft-pr');
  });

  it('has correct dataRole', () => {
    expect(SOVEREIGN_ACTION_DRAFT_PR.dataRole).toBe('action-draft-pr');
  });

  it('is primary kind', () => {
    expect(SOVEREIGN_ACTION_DRAFT_PR.kind).toBe('primary');
  });

  it('requires repo', () => {
    expect(SOVEREIGN_ACTION_DRAFT_PR.requiresRepo).toBe(true);
  });

  it('can be busy', () => {
    expect(SOVEREIGN_ACTION_DRAFT_PR.canBeBusy).toBe(true);
  });
});

describe('sovereign action contracts: repair-log', () => {
  it('has correct id', () => {
    expect(SOVEREIGN_ACTION_REPAIR_LOG.id).toBe('repair-log');
  });

  it('has correct testId', () => {
    expect(SOVEREIGN_ACTION_REPAIR_LOG.testId).toBe('builder__repair-log');
  });

  it('has correct dataRole', () => {
    expect(SOVEREIGN_ACTION_REPAIR_LOG.dataRole).toBe('action-repair-log');
  });

  it('is destructive kind', () => {
    expect(SOVEREIGN_ACTION_REPAIR_LOG.kind).toBe('destructive');
  });

  it('requires repo', () => {
    expect(SOVEREIGN_ACTION_REPAIR_LOG.requiresRepo).toBe(true);
  });

  it('can be busy', () => {
    expect(SOVEREIGN_ACTION_REPAIR_LOG.canBeBusy).toBe(true);
  });
});

describe('sovereign action contracts: repository-dependent actions', () => {
  it('marks save-session as requiring repo', () => {
    const contract = getSovereignActionContract('save-session');
    expect(contract?.requiresRepo).toBe(true);
  });

  it('marks analyze-mission as requiring repo', () => {
    const contract = getSovereignActionContract('analyze-mission');
    expect(contract?.requiresRepo).toBe(true);
  });

  it('marks start-task as requiring repo', () => {
    const contract = getSovereignActionContract('start-task');
    expect(contract?.requiresRepo).toBe(true);
  });
});

describe('sovereign action contracts: navigation and secondary actions', () => {
  it('marks monitor-toggle as navigation kind', () => {
    const contract = getSovereignActionContract('monitor-toggle');
    expect(contract?.kind).toBe('navigation');
  });

  it('marks restore-session as secondary kind', () => {
    const contract = getSovereignActionContract('restore-session');
    expect(contract?.kind).toBe('secondary');
  });

  it('marks clear-view as secondary kind', () => {
    const contract = getSovereignActionContract('clear-view');
    expect(contract?.kind).toBe('secondary');
  });

  it('monitor-toggle does not require repo', () => {
    const contract = getSovereignActionContract('monitor-toggle');
    expect(contract?.requiresRepo).toBe(false);
  });
});
