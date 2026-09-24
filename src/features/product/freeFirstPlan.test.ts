import { describe, expect, it } from 'vitest';
import { describeFreeFirstPlan, freeFirstProviderRoute, sovereignWorkflowGuarantees } from './freeFirstPlan';

describe('freeFirstPlan', () => {
  it('keeps the authenticated backend as the only online route', () => {
    expect(freeFirstProviderRoute).toEqual(['optional-user-keys']);
  });

  it('provides sovereign workflow guarantees', () => {
    expect(sovereignWorkflowGuarantees).toContain('boot-visible');
    expect(sovereignWorkflowGuarantees).toContain('visible-code-review');
    expect(sovereignWorkflowGuarantees).toContain('review-before-push');
    expect(sovereignWorkflowGuarantees).toContain('auto-fix-loop');
    expect(sovereignWorkflowGuarantees).toContain('android-webview-fallback');
    expect(sovereignWorkflowGuarantees).toContain('backend-litellm-before-local-safe');
  });

  it('describeFreeFirstPlan returns correct configuration', () => {
    const plan = describeFreeFirstPlan();
    expect(plan.route).toEqual(['optional-user-keys']);
    expect(plan.guarantees.length).toBe(6);
    expect(plan.keyRequiredAtBoot).toBe(false);
    expect(plan.githubPatPurpose).toBe('repository-read-write-only');
  });

  it('does not require a key at boot', () => {
    expect(describeFreeFirstPlan().keyRequiredAtBoot).toBe(false);
  });
});
