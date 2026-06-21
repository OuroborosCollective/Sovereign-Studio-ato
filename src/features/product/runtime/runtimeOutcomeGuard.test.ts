import { describe, expect, it } from 'vitest';
import {
  evaluateRuntimeOutcome,
  isRuntimeFeedbackNoiseText,
} from './runtimeOutcomeGuard';

describe('runtimeOutcomeGuard', () => {
  it('marks complete delivered output as fulfilled and learnable', () => {
    const report = evaluateRuntimeOutcome(
      { required: ['package-build', 'completed'] },
      'package-build completed with generated files and review proof',
    );

    expect(report.status).toBe('fulfilled');
    expect(report.learnable).toBe(true);
    expect(report.score).toBe(1);
    expect(report.missing).toEqual([]);
  });

  it('marks incomplete delivered output as partial and not learnable', () => {
    const report = evaluateRuntimeOutcome(
      { required: ['draft-pr', 'commit-sha', 'workflow-watch'] },
      'draft-pr returned commit-sha',
    );

    expect(report.status).toBe('partial');
    expect(report.learnable).toBe(false);
    expect(report.missing).toEqual(['workflow-watch']);
  });

  it('marks declared blockers as blocked before learning', () => {
    const report = evaluateRuntimeOutcome(
      { required: ['draft-pr', 'completed'], blockers: ['guard-stopper'] },
      'draft-pr guard-stopper before completed output',
    );

    expect(report.status).toBe('blocked');
    expect(report.learnable).toBe(false);
    expect(report.blockers).toEqual(['guard-stopper']);
  });

  it('marks declared feedback-only output as noise', () => {
    const report = evaluateRuntimeOutcome(
      { required: ['workflow-green'], noise: ['feedback-only'] },
      'feedback-only',
    );

    expect(report.status).toBe('noise');
    expect(report.learnable).toBe(false);
    expect(report.noise).toEqual(['feedback-only']);
  });

  it('recognizes guarded-output feedback as runtime feedback noise', () => {
    expect(isRuntimeFeedbackNoiseText('runtime-health', 'prevents guarded output')).toBe(true);
    expect(isRuntimeFeedbackNoiseText('runtime-health', 'runtime needs attention because health is blocked')).toBe(true);
    expect(isRuntimeFeedbackNoiseText('workflow-watch', 'workflow finished green')).toBe(false);
  });
});
