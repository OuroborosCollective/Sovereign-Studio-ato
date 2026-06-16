import { describe, expect, it } from 'vitest';
import {
  analyzeRepoFileIntegrity,
  analyzeRepoFileIntegrityList,
  summarizeFileIntegrity,
} from './repoFileIntegrity';

describe('repoFileIntegrity', () => {
  it('marks forbidden-looking paths as high risk without claiming content scan', () => {
    const result = analyzeRepoFileIntegrity({ path: '.env.local', type: 'blob', size: 20 });
    expect(result.riskLevel).toBe('high');
    expect(result.confidence).toBe('path-only');
    expect(result.flags).toContain('high-risk-path');
  });

  it('marks test code as low risk with path-only confidence', () => {
    const result = analyzeRepoFileIntegrity({ path: 'src/features/product/runtime/repoFileIntegrity.test.ts', type: 'blob', size: 1000 });
    expect(result.riskLevel).toBe('low');
    expect(result.flags).toContain('code');
    expect(result.flags).toContain('test');
  });

  it('sorts higher risk files first and summarizes counts', () => {
    const results = analyzeRepoFileIntegrityList([
      { path: 'README.md', type: 'blob' },
      { path: '.env', type: 'blob' },
      { path: 'src/mockService.ts', type: 'blob' },
    ]);

    expect(results[0].path).toBe('.env');
    expect(summarizeFileIntegrity(results)).toContain('3 entries analyzed');
  });
});
