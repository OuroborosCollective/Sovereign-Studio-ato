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

  it('does not use telemetry as an early planning auto-switch trigger', () => {
    const decision = decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'repo',
      repoReady: true,
      hasPackage: false,
      hasActiveTelemetry: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    });

    expect(decision).toMatchObject({ shouldSwitch: false, tab: 'repo' });
    expect(decision.reason).toContain('No auto view change');
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

  it('routes package-ready auto-review flow from builder to workflow instead of diff loader', () => {
    const decision = decideSovereignAutoView({
      mode: 'auto-review',
      activeStep: null,
      activeTab: 'builder',
      hasPackage: true,
      hasDiffSources: false,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    });

    expect(decision).toMatchObject({ shouldSwitch: true, tab: 'workflow' });
    expect(decision.reason).toContain('diff is internal');
  });

  it('does not let planningConfirmed=false send package-ready review back to diff', () => {
    const decision = decideSovereignAutoView({
      mode: 'auto-review',
      activeStep: null,
      activeTab: 'builder',
      hasPackage: true,
      hasDiffSources: false,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
      planningConfirmed: false,
    });

    expect(decision).toMatchObject({ shouldSwitch: true, tab: 'workflow' });
  });

  it('routes package-ready auto flow from files to workflow once source snapshots exist', () => {
    const decision = decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'files',
      hasPackage: true,
      hasDiffSources: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    });

    expect(decision).toMatchObject({ shouldSwitch: true, tab: 'workflow' });
    expect(decision.reason).toContain('source snapshots');
  });

  it('keeps workflow visible after successful workflow instead of returning to diff', () => {
    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'workflow',
      hasPackage: true,
      hasDiffSources: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'green',
    })).toMatchObject({ shouldSwitch: false, tab: 'workflow' });
  });

  it('does not bounce the manual planning workspace without a guide or auto mode', () => {
    const decision = decideSovereignAutoView({
      mode: 'manual',
      activeStep: null,
      activeTab: 'builder',
      hasPackage: true,
      hasActiveTelemetry: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'green',
    });

    expect(decision).toMatchObject({ shouldSwitch: false, tab: 'builder' });
    expect(decision.reason).toContain('planning workspace');
  });

  it('keeps the user-selected builder workspace visible in manual mode with the product App input shape', () => {
    const decision = decideSovereignAutoView({
      mode: 'manual',
      activeStep: null,
      activeTab: 'builder',
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



  it('does not trap manual navigation on workflow while checks are pending', () => {
    const decision = decideSovereignAutoView({
      mode: 'manual',
      activeStep: null,
      activeTab: 'builder',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'pending',
    });

    expect(decision).toMatchObject({ shouldSwitch: false, tab: 'builder' });
    expect(decision.reason).toContain('Manual mode keeps user navigation free');
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

  it('escapes an already visible diff tab back into workflow', () => {
    expect(decideSovereignAutoView({
      mode: 'manual',
      activeStep: null,
      activeTab: 'diff',
      hasPackage: true,
      hasDiffSources: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    })).toMatchObject({ shouldSwitch: true, tab: 'workflow' });
  });
});
