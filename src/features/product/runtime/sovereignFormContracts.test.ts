import { describe, expect, it } from 'vitest';

import {
  SOVEREIGN_FORM_CONTRACTS,
  SOVEREIGN_FORM_PRIVATE_ACCESS,
  SOVEREIGN_FORM_REPO_URL,
  assertSovereignFormContractsValid,
  getSovereignFormContract,
  validateSovereignFormContracts,
} from './sovereignFormContracts';

describe('sovereign form contracts', () => {
  it('validates the shipped list', () => {
    const report = validateSovereignFormContracts();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
    expect(() => assertSovereignFormContractsValid()).not.toThrow();
  });

  it('has unique ids, dataRoles, and testIds', () => {
    const ids = SOVEREIGN_FORM_CONTRACTS.map((contract) => contract.id);
    const dataRoles = SOVEREIGN_FORM_CONTRACTS.map((contract) => contract.dataRole);
    const testIds = SOVEREIGN_FORM_CONTRACTS.map((contract) => contract.testId);

    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(dataRoles).size).toBe(dataRoles.length);
    expect(new Set(testIds).size).toBe(testIds.length);
  });

  it('includes required form fields', () => {
    expect(getSovereignFormContract('repo-url')).toBeDefined();
    expect(getSovereignFormContract('repo-branch')).toBeDefined();
    expect(getSovereignFormContract('private-access')).toBeDefined();
    expect(getSovereignFormContract('mission')).toBeDefined();
    expect(getSovereignFormContract('automation-mode')).toBeDefined();
  });

  it('has non-empty labels and aria labels', () => {
    for (const contract of SOVEREIGN_FORM_CONTRACTS) {
      expect(contract.label.length).toBeGreaterThan(0);
      expect(contract.ariaLabel.length).toBeGreaterThan(0);
    }
  });

  it('has valid input types', () => {
    const validInputTypes = ['text', 'url', 'password', 'email', 'number', 'textarea', 'select'];

    for (const contract of SOVEREIGN_FORM_CONTRACTS) {
      expect(validInputTypes).toContain(contract.inputType);
    }
  });
});

describe('sovereign form contracts: private access safety', () => {
  it('marks private access as sensitive', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.sensitive).toBe(true);
  });

  it('enforces password input type for sensitive fields', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.inputType).toBe('password');
  });

  it('enforces autocomplete="off" for sensitive fields', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.autoComplete).toBe('off');
  });

  it('does not mark non-sensitive fields as sensitive', () => {
    for (const contract of SOVEREIGN_FORM_CONTRACTS) {
      if (contract.id !== 'private-access') {
        expect(contract.sensitive).toBe(false);
      }
    }
  });

  it('has correct testId pattern for repo-url', () => {
    expect(SOVEREIGN_FORM_REPO_URL.testId).toBe('repo-url__input');
  });

  it('has correct testId pattern for private-access', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.testId).toBe('private-access__input');
  });

  it('has correct dataRole for repo-url', () => {
    expect(SOVEREIGN_FORM_REPO_URL.dataRole).toBe('input-repo-url');
  });

  it('has correct dataRole for private-access', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.dataRole).toBe('input-private-access');
  });
});

describe('sovereign form contracts: repo-url contract', () => {
  it('has correct id', () => {
    expect(SOVEREIGN_FORM_REPO_URL.id).toBe('repo-url');
  });

  it('has correct inputType', () => {
    expect(SOVEREIGN_FORM_REPO_URL.inputType).toBe('url');
  });

  it('has correct autoComplete', () => {
    expect(SOVEREIGN_FORM_REPO_URL.autoComplete).toBe('url');
  });

  it('is required', () => {
    expect(SOVEREIGN_FORM_REPO_URL.required).toBe(true);
  });

  it('is not sensitive', () => {
    expect(SOVEREIGN_FORM_REPO_URL.sensitive).toBe(false);
  });
});

describe('sovereign form contracts: private-access contract', () => {
  it('has correct id', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.id).toBe('private-access');
  });

  it('has correct inputType', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.inputType).toBe('password');
  });

  it('has correct autoComplete', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.autoComplete).toBe('off');
  });

  it('is not required', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.required).toBe(false);
  });

  it('is sensitive', () => {
    expect(SOVEREIGN_FORM_PRIVATE_ACCESS.sensitive).toBe(true);
  });
});
