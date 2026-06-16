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

export function detectFailureCode(error: unknown): LlmFailureCode {
  const anyError = error as { status?: number; name?: string; message?: string };
  const message = String(anyError?.message ?? '').toLowerCase();
  const status = Number(anyError?.status ?? 0);

  if (status === 429 || message.includes('rate limit') || message.includes('too many requests')) return 'rate_limit';
  if (status === 401 || status === 403 || message.includes('unauthorized') || message.includes('forbidden')) return 'unauthorized';
  if (anyError?.name === 'AbortError' || message.includes('timeout')) return 'timeout';
  if (message.includes('network') || message.includes('fetch failed')) return 'network';
  if (message.includes('contract') || message.includes('invalid')) return 'invalid_contract';
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

export function assertPushableBrain(providerId: LlmProviderId, mission: string, brain: SovereignBrainResult): void {
  assertSovereignBrainResult(brain);

  if (brain.execution.patches.length === 0) {
    throw new Error(`Provider ${providerId} returned no execution patches.`);
  }

  for (const patch of brain.execution.patches) {
    const normalized = patch.file.toLowerCase();
    if (FORBIDDEN_PATCH_PATHS.some((path) => normalized === path || normalized.startsWith(path))) {
      throw new Error(`Provider ${providerId} tried to patch forbidden path: ${patch.file}`);
    }
  }

  const lower = mission.toLowerCase();
  const wantsDocs = lower.includes('readme') || lower.includes('documentation') || lower.includes('dokumentation') || lower.includes('update history');
  if (!wantsDocs) return;

  const touchedDocs = brain.execution.patches.some((patch) => {
    const file = patch.file.toLowerCase();
    return file === 'readme.md' || file.startsWith('docs/');
  });

  if (!touchedDocs) {
    throw new Error('Documentation request did not produce README.md or docs/* patches.');
  }
}
