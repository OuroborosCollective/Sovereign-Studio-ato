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

  it('allows security code that mentions secret concepts without embedding a secret value', () => {
    const report = reviewGeneratedFiles([{
      path: 'src/security/tokenPolicy.ts',
      content: "export const token = process.env.TOOLCHAIN_API_KEY;\nexport const passwordPolicy = 'required';",
      reason: 'security implementation',
    }]);
    expect(report.highRiskCount).toBe(0);
    expect(report.files[0]?.flags).not.toContain('secret-value-in-content');
    expect(report.selfReview.accepted).toBe(true);
  });

  it('rejects an actual embedded secret value', () => {
    const report = reviewGeneratedFiles([{
      path: 'src/config.ts',
      content: "export const api_key = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef';",
      reason: 'unsafe implementation',
    }]);
    expect(report.highRiskCount).toBe(1);
    expect(report.files[0]?.flags).toContain('secret-value-in-content');
    expect(report.selfReview.accepted).toBe(false);
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

  it('correctly calculates line counts for empty, single-line, and multi-line content', () => {
    expect(reviewGeneratedFile({ path: 'src/empty.ts', content: '', reason: 'test' }).lineCount).toBe(0);
    expect(reviewGeneratedFile({ path: 'src/single.ts', content: 'hello world', reason: 'test' }).lineCount).toBe(1);
    expect(reviewGeneratedFile({ path: 'src/multi.ts', content: 'line1\nline2\r\nline3', reason: 'test' }).lineCount).toBe(3);
  });

  it('correctly calculates consolidated report summaries across multiple files in a single pass', () => {
    const report = reviewGeneratedFiles([
      { path: 'src/index.ts', content: 'console.log("hello");\nconsole.log("world");', reason: 'entry' },
      { path: '.env.local', content: 'SECRET=123', reason: 'env' },
    ]);
    expect(report.totalFiles).toBe(2);
    expect(report.totalLines).toBe(3); // 2 + 1
    expect(report.totalChars).toBe(53); // 43 + 10
    expect(report.highRiskCount).toBe(1); // .env.local is high risk
    expect(report.actionableFileCount).toBe(1); // src/index.ts is actionable
  });
});
