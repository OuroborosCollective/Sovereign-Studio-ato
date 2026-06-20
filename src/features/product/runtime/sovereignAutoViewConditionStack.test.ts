import { describe, expect, it } from 'vitest';
import {
  decideSovereignAutoView,
  evaluateSovereignAutoViewConditions,
  isSovereignAutoViewManualOverrideActive,
} from './sovereignAutoViewRouter';

describe('sovereignAutoViewRouter condition stack', () => {
  it('pauses suggestion-only switches during a manual override window', () => {
    const decision = decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'repo',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'green',
      nowMs: 5_000,
      lastUserInteractionAt: 4_500,
      manualOverrideUntil: 10_000,
    });

    expect(isSovereignAutoViewManualOverrideActive({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'repo',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'green',
      nowMs: 5_000,
      manualOverrideUntil: 10_000,
    })).toBe(true);
    expect(decision).toMatchObject({ shouldSwitch: false, tab: 'repo' });
    expect(decision.reason).toContain('paused');
  });

  it('allows suggestion switches after inactivity', () => {
    expect(decideSovereignAutoView({
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'repo',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'green',
      nowMs: 9_000,
      lastUserInteractionAt: 1_000,
      autoSwitchInactivityMs: 3_000,
    })).toMatchObject({ shouldSwitch: true, tab: 'files' });
  });

  it('evaluates signal, completed tab, inactivity and clear override conditions', () => {
    expect(evaluateSovereignAutoViewConditions([
      { type: 'SIGNAL_ACTIVE', signal: 'package-ready' },
      { type: 'TAB_COMPLETED', tab: 'builder' },
      { type: 'USER_INACTIVE', thresholdMs: 3_000 },
      { type: 'MANUAL_OVERRIDE_CLEAR' },
    ], {
      mode: 'full-auto-draft-pr',
      activeStep: null,
      activeTab: 'builder',
      hasPackage: true,
      isPublishing: false,
      isWatchingWorkflow: false,
      workflowStatus: 'idle',
      completedTabs: ['builder'],
      nowMs: 8_000,
      lastUserInteractionAt: 1_000,
    })).toBe(true);
  });
});
