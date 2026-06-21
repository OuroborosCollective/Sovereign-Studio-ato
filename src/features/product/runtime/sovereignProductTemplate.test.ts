import { describe, expect, it } from 'vitest';

import {
  SOVEREIGN_PRODUCT_TEMPLATE,
  assertSovereignProductTemplateValid,
  canSovereignProductTemplateAutoOpen,
  getSovereignProductTemplateTab,
  isSovereignProductTemplatePrimaryTab,
  validateSovereignProductTemplate,
  type SovereignProductTemplateContract,
} from './sovereignProductTemplate';

function cloneTemplate(): SovereignProductTemplateContract {
  return {
    ...SOVEREIGN_PRODUCT_TEMPLATE,
    primaryFlow: [...SOVEREIGN_PRODUCT_TEMPLATE.primaryFlow],
    sideTabs: [...SOVEREIGN_PRODUCT_TEMPLATE.sideTabs],
    diagnosticTabs: [...SOVEREIGN_PRODUCT_TEMPLATE.diagnosticTabs],
    autoNavigationAllowlist: [...SOVEREIGN_PRODUCT_TEMPLATE.autoNavigationAllowlist],
    invariants: [...SOVEREIGN_PRODUCT_TEMPLATE.invariants],
    tabs: SOVEREIGN_PRODUCT_TEMPLATE.tabs.map((tab) => ({ ...tab })),
  };
}

describe('sovereign product template contract', () => {
  it('keeps the bundled product template valid', () => {
    const report = validateSovereignProductTemplate();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
    expect(() => assertSovereignProductTemplateValid()).not.toThrow();
  });

  it('locks the main product flow to repo -> builder -> files -> diff -> workflow', () => {
    expect(SOVEREIGN_PRODUCT_TEMPLATE.startTab).toBe('repo');
    expect(SOVEREIGN_PRODUCT_TEMPLATE.primaryFlow).toEqual([
      'repo',
      'builder',
      'files',
      'diff',
      'workflow',
    ]);

    for (const [index, tab] of SOVEREIGN_PRODUCT_TEMPLATE.primaryFlow.entries()) {
      const definition = getSovereignProductTemplateTab(tab);
      expect(definition.group).toBe('primary');
      expect(definition.mainFlowIndex).toBe(index);
      expect(isSovereignProductTemplatePrimaryTab(tab)).toBe(true);
    }
  });

  it('keeps operator and diagnostics out of the main flow', () => {
    const sideAndDiagnostic = [
      ...SOVEREIGN_PRODUCT_TEMPLATE.sideTabs,
      ...SOVEREIGN_PRODUCT_TEMPLATE.diagnosticTabs,
    ];

    for (const tab of sideAndDiagnostic) {
      const definition = getSovereignProductTemplateTab(tab);
      expect(definition.mainFlowIndex).toBeNull();
      expect(isSovereignProductTemplatePrimaryTab(tab)).toBe(false);
    }
  });

  it('allows auto navigation only for active work and red stoppers', () => {
    expect(canSovereignProductTemplateAutoOpen('active-work')).toBe(true);
    expect(canSovereignProductTemplateAutoOpen('red-stopper')).toBe(true);
    expect(canSovereignProductTemplateAutoOpen('passive-review')).toBe(false);
    expect(canSovereignProductTemplateAutoOpen('awaiting-intent')).toBe(false);
    expect(canSovereignProductTemplateAutoOpen('side-channel')).toBe(false);
    expect(canSovereignProductTemplateAutoOpen('manual')).toBe(false);
  });

  it('rejects template drift away from repo-first startup', () => {
    const broken = cloneTemplate();
    broken.startTab = 'builder';

    const report = validateSovereignProductTemplate(broken);

    expect(report.valid).toBe(false);
    expect(report.errors.join(' | ')).toContain('Template must start in repo tab');
  });

  it('rejects template drift away from the locked main flow order', () => {
    const broken = cloneTemplate();
    broken.primaryFlow = ['repo', 'files', 'builder', 'diff', 'workflow'];

    const report = validateSovereignProductTemplate(broken);

    expect(report.valid).toBe(false);
    expect(report.errors.join(' | ')).toContain('Primary flow must be repo > builder > files > diff > workflow');
  });

  it('rejects passive auto-navigation as a product-template violation', () => {
    const broken = cloneTemplate();
    broken.autoNavigationAllowlist = [
      ...broken.autoNavigationAllowlist,
      'passive-review',
      'awaiting-intent',
    ];

    const report = validateSovereignProductTemplate(broken);

    expect(report.valid).toBe(false);
    expect(report.errors.join(' | ')).toContain('passive-review must not be allowed to auto-open views');
    expect(report.errors.join(' | ')).toContain('awaiting-intent must not be allowed to auto-open views');
  });

  it('rejects primary tabs that are not declared as primary group members', () => {
    const broken = cloneTemplate();
    broken.tabs = broken.tabs.map((tab) =>
      tab.id === 'builder'
        ? { ...tab, group: 'side' }
        : tab,
    );

    const report = validateSovereignProductTemplate(broken);

    expect(report.valid).toBe(false);
    expect(report.errors.join(' | ')).toContain('Primary flow tab builder must be group primary');
  });
});
