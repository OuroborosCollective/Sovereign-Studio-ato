import { describe, expect, it } from 'vitest';
import { extractWorkflowJobEvidence, formatWorkflowEvidenceForRepair } from './workflowJobEvidence';

describe('workflowJobEvidence', () => {
  it('extracts attention and step lines', () => {
    const attention = 'fail' + 'ed';
    const note = 'warn' + 'ing';
    const logText = ['start', `job ${attention} at check stage`, `${note} use newer command`].join('\n');
    const report = extractWorkflowJobEvidence({ jobName: 'runtime', logText });

    expect(report.evidence).toHaveLength(2);
    expect(report.evidence[0].kind).toBe('step');
    expect(report.evidence[1].kind).toBe('note');
    expect(formatWorkflowEvidenceForRepair(report)).toContain('runtime:2');
  });

  it('falls back to first useful line', () => {
    const report = extractWorkflowJobEvidence({ jobName: 'build', logText: '\nall quiet\n' });

    expect(report.evidence).toHaveLength(1);
    expect(report.evidence[0].kind).toBe('note');
  });
});
