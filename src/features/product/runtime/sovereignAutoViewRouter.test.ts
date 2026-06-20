import { describe, expect, it } from 'vitest';
import { decideSovereignAutoView, validateSovereignAutoViewInput } from './sovereignAutoViewRouter';

describe('sovereignAutoViewRouter', () => {
  it('does not force auto mode into builder when no runtime step is active', () => {
    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'repo',
      hasPackage: false,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    })).toMatchObject({ shouldSwitch: false, tab: 'repo' });
  });

  it('keeps runtime-owned views visible while work is active', () => {
    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: 'package-build',
      activeTab: 'repo',
      hasPackage: false,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    })).toMatchObject({ shouldSwitch: true, tab: 'builder' });

    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: 'draft-pr-publish',
      activeTab: 'builder',
      hasPackage: true,
      isPublishing: true,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    })).toMatchObject({ shouldSwitch: true, tab: 'workflow' });

    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: 'workflow-watch',
      activeTab: 'workflow',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: true,
      workflowStatus: 'pending',
    })).toMatchObject({ shouldSwitch: false, tab: 'workflow' });
  });

  it('returns to files after successful workflow when a package exists', () => {
    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'workflow',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'green',
    })).toMatchObject({ shouldSwitch: true, tab: 'files' });
  });

  it('keeps the user-selected builder workspace visible even when a package already exists', () => {
    const decision = decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'builder',
      repoReady: true,
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
      hasActiveTelemetry: true,
    });

    expect(decision).toMatchObject({ shouldSwitch: false, tab: 'builder' });
    expect(decision.reason).toContain('Builder');
  });

  it('routes failed workflow checks into repair instead of leaving the old editor visible', () => {
    const decision = decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'files',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'red',
    });

    expect(decision).toMatchObject({ shouldSwitch: true, tab: 'repair' });
    expect(decision.reason).toContain('repair');
  });

  it('keeps user-selected side tabs available in guarded auto mode', () => {
    const input = {
      mode: 'full-auto-draft-pr' as const,
      activeStep: null,
      activeTab: 'memory' as const,
      hasPackage: false,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle' as const,
    };

    expect(validateSovereignAutoViewInput(input)).toEqual([]);
    expect(decideSovereignAutoView(input)).toMatchObject({ shouldSwitch: false, tab: 'memory' });
  });

  it('keeps manual mode from hijacking an intentional user tab when nothing is running', () => {
    expect(decideSovereignAutoView({
      mode: 'manual',
      activeStep: null,
      activeTab: 'memory',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    })).toMatchObject({ shouldSwitch: false, tab: 'memory' });
  });
});
