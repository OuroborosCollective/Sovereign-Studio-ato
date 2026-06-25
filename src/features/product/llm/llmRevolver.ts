import type {
  LlmAdapter,
  LlmAdapterContext,
  LlmRevolverEvent,
  LlmRevolverFailure,
  LlmRevolverMemory,
  LlmRevolverOptions,
  LlmRevolverResult,
} from './llmAdapter';
import { createInitialRevolverMemory } from './llmAdapter';
import { assertPushableBrain, createLlmFailure } from './llmRuntimeChecks';

function orderedAdapters(adapters: LlmAdapter[]): LlmAdapter[] {
  return [...adapters].filter((adapter) => adapter.enabled).sort((a, b) => a.priority - b.priority);
}

function nextIndex(index: number, length: number): number {
  return length === 0 ? 0 : (index + 1) % length;
}

function startIndex(active: LlmAdapter[], memory: LlmRevolverMemory): number {
  const hostedBridgeIndex = active.findIndex((adapter) => adapter.id === 'optional-user-keys' && adapter.kind === 'user-key');
  if (hostedBridgeIndex >= 0) return hostedBridgeIndex;
  return Math.max(0, Math.min(memory.nextIndex, active.length - 1));
}

function assertRealProvider(adapter: LlmAdapter): void {
  if (adapter.kind !== 'local-safe') return;
  throw new Error('VALIDATION_FAILED_LLM_REQUIRED: local-safe is analysis-only and cannot be the source of a publishable Draft PR. A real hosted/user-key provider must produce the package.');
}

function emit(options: LlmRevolverOptions, attempts: LlmRevolverEvent[], event: LlmRevolverEvent): void {
  attempts.push(event);
  options.onEvent?.(event);
}

export async function resolveWithLlmRevolver(
  adapters: LlmAdapter[],
  context: LlmAdapterContext,
  options: LlmRevolverOptions = {},
): Promise<LlmRevolverResult> {
  const active = orderedAdapters(adapters);
  const attempts: LlmRevolverEvent[] = [];
  const now = options.now ?? Date.now;
  const memory: LlmRevolverMemory = options.memory ?? createInitialRevolverMemory();
  const maxShots = Math.min(options.maxShots ?? active.length, active.length);

  if (active.length === 0) {
    const failure = createLlmFailure('local-safe', new Error('No enabled LLM adapters.'));
    emit(options, attempts, {
      type: 'revolver:exhausted',
      providerId: 'local-safe',
      message: failure.message,
      code: failure.code,
      attempt: 0,
    });
    return { ok: false, failure, memory, attempts } satisfies LlmRevolverFailure;
  }

  let cursor = startIndex(active, memory);
  let lastFailure = createLlmFailure(active[cursor].id, new Error('No provider was fired.'));

  for (let shot = 0; shot < maxShots; shot++) {
    const adapter = active[cursor];
    const attempt = shot + 1;

    if (adapter.kind === 'no-key' && !context.allowExternalNoKey) {
      emit(options, attempts, {
        type: 'provider:skipped',
        providerId: adapter.id,
        message: `${adapter.id} skipped because external no-key routes are disabled.`,
        code: 'disabled',
        attempt,
      });
      cursor = nextIndex(cursor, active.length);
      continue;
    }

    if (adapter.kind === 'opt-in' && !context.allowOptInRoutes) {
      emit(options, attempts, {
        type: 'provider:skipped',
        providerId: adapter.id,
        message: `${adapter.id} skipped because opt-in routes are disabled.`,
        code: 'disabled',
        attempt,
      });
      cursor = nextIndex(cursor, active.length);
      continue;
    }

    emit(options, attempts, {
      type: 'provider:trying',
      providerId: adapter.id,
      message: `Firing ${adapter.id}.`,
      attempt,
    });

    try {
      const result = await adapter.run(context);
      assertPushableBrain(adapter.id, context.mission, result.brain);
      assertRealProvider(adapter);
      memory.nextIndex = nextIndex(cursor, active.length);
      memory.shots = [{ providerId: adapter.id, at: now() }, ...memory.shots].slice(0, 30);
      emit(options, attempts, {
        type: 'provider:success',
        providerId: adapter.id,
        message: `${adapter.id} returned a valid Sovereign brain result.`,
        attempt,
      });
      return { ok: true, result, memory, attempts };
    } catch (error) {
      lastFailure = createLlmFailure(adapter.id, error);
      memory.nextIndex = nextIndex(cursor, active.length);
      memory.shots = [{ providerId: adapter.id, code: lastFailure.code, at: now() }, ...memory.shots].slice(0, 30);
      emit(options, attempts, {
        type: 'provider:failed',
        providerId: adapter.id,
        message: lastFailure.message,
        code: lastFailure.code,
        attempt,
      });
      cursor = nextIndex(cursor, active.length);
    }
  }

  emit(options, attempts, {
    type: 'revolver:exhausted',
    providerId: lastFailure.providerId,
    message: 'All enabled LLM adapters failed or were skipped.',
    code: lastFailure.code,
    attempt: maxShots,
  });

  return { ok: false, failure: lastFailure, memory, attempts };
}
