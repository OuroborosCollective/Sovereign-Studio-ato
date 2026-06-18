import { describe, expect, it } from 'vitest';
import { assertGeneratedFileReviewSafe, reviewGeneratedFile, reviewGeneratedFiles } from './generatedFileReview';

describe('generated file self review', () => {
  it('keeps normal generated metadata', () => {
    const item = reviewGeneratedFile({ path: 'README.md', content: '# Hello\nWorld', reason: 'docs' });
    expect(item.lineCount).toBe(2);
    expect(item.risk).toBe('low');
  });

  it('accepts actionable workflow files', () => {
    const report = reviewGeneratedFiles([{ path: '.github/workflows/ci.yml', content: 'name: ci', reason: 'workflow' }]);
    expect(report.actionableFileCount).toBe(1);
    expect(report.selfReview.accepted).toBe(true);
    expect(() => assertGeneratedFileReviewSafe(report)).not.toThrow();
  });

  it('rejects plan only output and asks for rewrite', () => {
    const report = reviewGeneratedFiles([
      { path: 'docs/SOVEREIGN_PLAN.md', content: '# Sovereign Plan', reason: 'plan' },
      { path: 'generated/sovereign-product/workflow.ts', content: 'export const audit = true;', reason: 'audit' },
    ]);
    expect(report.planOnlyCount).toBe(2);
    expect(report.actionableFileCount).toBe(0);
    expect(report.selfReview.learningSignal).toBe('plan-only-output-rejected');
    expect(report.selfReview.rewriteRequired).toBe(true);
    expect(() => assertGeneratedFileReviewSafe(report)).toThrow('actionable implementation');
  });

  it('accepts a plan only when real implementation files are included too', () => {
    const report = reviewGeneratedFiles([
      { path: 'docs/SOVEREIGN_PLAN.md', content: '# Sovereign Plan', reason: 'plan' },
      { path: 'src/mobile-operator-coach.ts', content: 'export const ok = true;', reason: 'implementation' },
      { path: 'src/mobile-workflow-guidance.test.ts', content: 'export const testOk = true;', reason: 'test' },
    ]);
    expect(report.planOnlyCount).toBe(1);
    expect(report.actionableFileCount).toBe(2);
    expect(report.selfReview.accepted).toBe(true);
    expect(() => assertGeneratedFileReviewSafe(report)).not.toThrow();
  });
});
