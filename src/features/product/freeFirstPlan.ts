export const freeFirstProviderRoute = ['mlvoca', 'pollinations', 'optional-user-keys'] as const;

export const sovereignWorkflowGuarantees = [
  'boot-visible',
  'visible-code-review',
  'review-before-push',
  'auto-fix-loop',
  'android-webview-fallback',
] as const;

export function describeFreeFirstPlan() {
  return {
    route: [...freeFirstProviderRoute],
    guarantees: [...sovereignWorkflowGuarantees],
    keyRequiredAtBoot: false,
    githubPatPurpose: 'repository-read-write-only',
  };
}
