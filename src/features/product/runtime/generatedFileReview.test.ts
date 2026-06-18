import { describe, expect, it } from 'vitest';
import {
  assertGeneratedFileReviewSafe,
  reviewGeneratedFile,
  reviewGeneratedFiles,
} from './generatedFileReview';

describe('generatedFileReview', () => {
  it('reviews generated file size and preview metadata', () => {
    const item = reviewGeneratedFile({ path: 'README.md', content: '# Hello\nWorld', reason: 'docs' });
    expect(item.lineCount).toBe(2);
    expect(item.charCount).toBeGreaterThan(0);
    expect(item.risk).toBe('low');
  });

  it('marks secret-looking generated content as high risk', () => {
    const report = reviewGeneratedFiles([
      { path: 'docs/SETUP.md', content: 'API_KEY=abc', reason: 'bad docs' },
    ]);
    expect(report.highRiskCount).toBe(1);
    expect(() => assertGeneratedFileReviewSafe(report)).toThrow('high-risk');
  });

  it('marks workflow or config files as medium risk', () => {
    const report = reviewGeneratedFiles([
      { path: '.github/workflows/ci.yml', content: 'name: ci', reason: 'workflow' },
    ]);
    expect(report.mediumRiskCount).toBe(1);
    expect(report.actionableFileCount).toBe(1);
    expect(() => assertGeneratedFileReviewSafe(report)).not.toThrow();
  });

  it('rejects plan-only packages before draft PR publishing', () => {
    const report = reviewGeneratedFiles([
      { path: 'docs/SOVEREIGN_PLAN.md', content: '# Sovereign Plan', reason: 'visible plan' },
      { path: 'generated/sovereign-product/workflow.ts', content: 'export const audit = true;', reason: 'audit marker' },
    ]);

    expect(report.planOnlyCount).toBe(2);
    expect(report.actionableFileCount).toBe(0);
    expect(() => assertGeneratedFileReviewSafe(report)).toThrow('plan-only');
  });

  it('allows plan files only when paired with actionable product changes', () => {
    const report = reviewGeneratedFiles([
      { path: 'docs/SOVEREIGN_PLAN.md', content: '# Sovereign Plan', reason: 'visible plan' },
      { path: 'src/mobile-operator-coach.ts', content: 'export const ok = true;', reason: 'real product change' },
      { path: 'src/mobile-workflow-guidance.test.ts', content: 'export const testOk = true;', reason: 'guard test' },
    ]);

    expect(report.planOnlyCount).toBe(1);
    expect(report.actionableFileCount).toBe(2);
    expect(() => assertGeneratedFileReviewSafe(report)).not.toThrow();
  });
});
