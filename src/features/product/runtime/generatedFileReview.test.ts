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
    expect(() => assertGeneratedFileReviewSafe(report)).not.toThrow();
  });
});
