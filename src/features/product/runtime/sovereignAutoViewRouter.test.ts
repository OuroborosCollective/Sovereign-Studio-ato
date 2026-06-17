import { describe, expect, it } from 'vitest';
import { decideSovereignAutoView, validateSovereignAutoViewInput } from './sovereignAutoViewRouter';

describe('sovereignAutoViewRouter', () => {
  it('walks auto mode through Auftrag, editor, log/workflow, and ready files views', () => {
    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'repo',
      hasPackage: false,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    })).toMatchObject({ shouldSwitch: true, tab: 'builder' });

    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: 'package-build',
      activeTab: 'builder',
      hasPackage: false,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
    })).toMatchObject({ shouldSwitch: false, tab: 'builder' });

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

  it('validates unsupported auto tabs so bad view state goes to telemetry', () => {
    const input = {
      mode: 'auto-review' as const,
      activeStep: null,
      activeTab: 'memory' as const,
      hasPackage: false,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle' as const,
    };

    expect(validateSovereignAutoViewInput(input)).toContain('Auto mode is on an unsupported active tab: memory');
    expect(decideSovereignAutoView(input)).toMatchObject({ shouldSwitch: true, tab: 'telemetry' });
  });
});
