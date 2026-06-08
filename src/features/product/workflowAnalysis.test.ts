import { describe, expect, it } from 'vitest';
import { analyzeWorkflow } from './workflowAnalysis';

describe('workflowAnalysis', () => {
  it('sends failed checks back to fix', () => {
    expect(analyzeWorkflow('failed').nextAction).toBe('fix');
  });

  it('requires confirmation when checks are green', () => {
    expect(analyzeWorkflow('green').nextAction).toBe('confirm');
  });
});
