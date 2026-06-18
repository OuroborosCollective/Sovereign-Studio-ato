import { assertSovereignBrainResult, type SovereignBrainResult } from '../brain/sovereignBrainContract';
import type { LlmAdapterFailure, LlmFailureCode, LlmProviderId } from './llmAdapter';

const FORBIDDEN_PATCH_PATHS = [
  '.env',
  '.env.local',
  '.env.production',
  'node_modules/',
  'dist/',
  'build/',
];

const PLAN_ONLY_PATCH_PATHS = new Set(['docs/sovereign_plan.md', 'generated/sovereign-product/workflow.ts']);
const ACTIONABLE_PATCH_PATHS = [/^src\//i, /^tests?\//i, /\.test\.[tj]sx?$/i, /\.spec\.[tj]sx?$/i, /^android\//i, /^scripts\//i, /^\.github\//i, /^package\.json$/i, /^vite\.config/i, /^tsconfig/i, /^readme\.md$/i, /^docs\/update_history\.md$/i, /^docs\//i];

function normalizePatchPath(path: string): string {
  return path.trim().replace(/^\/+/, '').toLowerCase();
}

function isActionablePatchPath(path: string): boolean {
  return ACTIONABLE_PATCH_PATHS.some((pattern) => pattern.test(path));
}

export function detectFailureCode(error: unknown): LlmFailureCode {
  const anyError = error as { status?: number; name?: string; message?: string };
  const message = String(anyError?.message ?? '').toLowerCase();
  const status = Number(anyError?.status ?? 0);

  if (status === 429 || message.includes('rate limit') || message.includes('too many requests')) return 'rate_limit';
  if (status === 401 || status === 403 || message.includes('unauthorized') || message.includes('forbidden')) return 'unauthorized';
  if (anyError?.name === 'AbortError' || message.includes('timeout')) return 'timeout';
  if (message.includes('network') || message.includes('fetch failed')) return 'network';
  if (message.includes('contract') || message.includes('invalid') || message.includes('documentation request') || message.includes('no execution patches') || message.includes('validation_failed') || message.includes('plan-only')) return 'invalid_contract';
  if (message.includes('empty')) return 'empty_output';
  return 'unknown';
}

export function createLlmFailure(providerId: LlmProviderId, error: unknown): LlmAdapterFailure {
  const code = detectFailureCode(error);
  const status = Number((error as { status?: number })?.status ?? 0) || undefined;
  return {
    providerId,
    code,
    status,
    retryable: code !== 'unauthorized' && code !== 'disabled',
    message: error instanceof Error ? error.message : String(error),
  };
}

export function assertActionableCode(providerId: LlmProviderId, brain: SovereignBrainResult): void {
  assertSovereignBrainResult(brain);

  if (brain.execution.patches.length === 0) {
    throw new Error(`VALIDATION_FAILED_NO_CODE: Provider ${providerId} returned a valid plan but no execution patches.`);
  }

  const emptyPatch = brain.execution.patches.find((patch) => patch.type !== 'delete' && patch.code.trim().length < 10);
  if (emptyPatch) {
    throw new Error(`VALIDATION_FAILED_EMPTY_PATCH: Provider ${providerId} returned an empty patch for ${emptyPatch.file}.`);
  }

  const normalizedPaths = brain.execution.patches.map((patch) => normalizePatchPath(patch.file));
  const hasActionablePatch = normalizedPaths.some(isActionablePatchPath);
  const hasOnlyPlanArtifacts = normalizedPaths.length > 0 && normalizedPaths.every((path) => PLAN_ONLY_PATCH_PATHS.has(path));

  if (hasOnlyPlanArtifacts || !hasActionablePatch) {
    throw new Error(`VALIDATION_FAILED_PLAN_ONLY: Provider ${providerId} returned plan/audit-only output. Rewrite with real source, runtime, test, workflow, Android, docs update history, or script patches before Draft PR.`);
  }
}

export function assertPushableBrain(providerId: LlmProviderId, mission: string, brain: SovereignBrainResult): void {
  assertActionableCode(providerId, brain);

  for (const patch of brain.execution.patches) {
    const normalized = normalizePatchPath(patch.file);
    if (FORBIDDEN_PATCH_PATHS.some((path) => normalized === path || normalized.startsWith(path))) {
      throw new Error(`Provider ${providerId} tried to patch forbidden path: ${patch.file}`);
    }
  }

  const lower = mission.toLowerCase();
  const wantsDocs = lower.includes('readme') || lower.includes('documentation') || lower.includes('dokumentation') || lower.includes('update history');
  if (!wantsDocs) return;

  const touchedDocs = brain.execution.patches.some((patch) => {
    const file = normalizePatchPath(patch.file);
    return file === 'readme.md' || file.startsWith('docs/');
  });

  if (!touchedDocs) {
    throw new Error('Documentation request did not produce README.md or docs/* patches.');
  }
}
