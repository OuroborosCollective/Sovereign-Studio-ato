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

/** How long (ms) a provider stays in cooldown after a rate-limit / timeout / network failure. */
const COOLDOWN_MS = 5 * 60 * 1000; // 5 minutes

/** Failure codes that trigger a cooldown instead of an immediate skip. */
const COOLDOWN_CODES = new Set(['rate_limit', 'timeout', 'network']);

function orderedAdapters(adapters: LlmAdapter[]): LlmAdapter[] {
  return [...adapters].filter((adapter) => adapter.enabled).sort((a, b) => a.priority - b.priority);
}

function nextIndex(index: number, length: number): number {
  return length === 0 ? 0 : (index + 1) % length;
}

function startIndex(active: LlmAdapter[], memory: LlmRevolverMemory): number {
  const hostedBridgeIndex = active.findIndex((adapter) => adapter.id === 'optional-user-keys');
  if (hostedBridgeIndex >= 0) return hostedBridgeIndex;
  return Math.max(0, Math.min(memory.nextIndex, active.length - 1));
}

function assertRealProvider(adapter: LlmAdapter): void {
  if (adapter.kind !== 'local-safe') return;
  throw new Error('VALIDATION_FAILED_LLM_REQUIRED: local-safe is analysis-only and cannot be the source of a publishable Draft PR. The authenticated Sovereign Backend must produce the package.');
}

function emit(options: LlmRevolverOptions, attempts: LlmRevolverEvent[], event: LlmRevolverEvent): void {
  attempts.push(event);
  options.onEvent?.(event);
}

/**
 * Returns true if the provider is currently in cooldown and should be skipped.
 * Cooling adapters are automatically re-eligible once their TTL expires.
 */
function isCooling(adapterId: string, memory: LlmRevolverMemory, nowMs: number): boolean {
  const until = memory.coolingUntil[adapterId];
  return until !== undefined && nowMs < until;
}

/**
 * Returns a new memory snapshot with the given provider put into cooldown.
 */
function withCooldown(memory: LlmRevolverMemory, adapterId: string, nowMs: number): LlmRevolverMemory {
  return {
    ...memory,
    coolingUntil: {
      ...memory.coolingUntil,
      [adapterId]: nowMs + COOLDOWN_MS,
    },
  };
}

export async function resolveWithLlmRevolver(
  adapters: LlmAdapter[],
  context: LlmAdapterContext,
  options: LlmRevolverOptions = {},
): Promise<LlmRevolverResult> {
  const active = orderedAdapters(adapters);
  const attempts: LlmRevolverEvent[] = [];
  const now = options.now ?? Date.now;
  let memory: LlmRevolverMemory = options.memory ?? createInitialRevolverMemory();
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
  let noKeyRoutesBlocked = false;

  for (let shot = 0; shot < maxShots; shot++) {
    const adapter = active[cursor];
    const attempt = shot + 1;
    const nowMs = now();

    // ── Consent gate: no-key routes ──────────────────────────────────────────
    if (adapter.kind === 'no-key' && !context.allowExternalNoKey) {
      noKeyRoutesBlocked = true;
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

    // ── Consent gate: opt-in routes ───────────────────────────────────────────
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

    // ── Cooldown gate: skip adapters in active cooldown ──────────────────────
    if (isCooling(adapter.id, memory, nowMs)) {
      const remainingMs = memory.coolingUntil[adapter.id]! - nowMs;
      const remainingSec = Math.ceil(remainingMs / 1000);
      emit(options, attempts, {
        type: 'provider:cooling',
        providerId: adapter.id,
        message: `${adapter.id} is cooling down for ${remainingSec}s after a recent failure — loading reserve.`,
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
      emit(options, attempts, {
        type: 'provider:success',
        providerId: adapter.id,
        message: `${adapter.id} succeeded.`,
        attempt,
      });
      return { ok: true, result, memory, attempts };
    } catch (error: unknown) {
      const failure = createLlmFailure(adapter.id, error instanceof Error ? error : new Error(String(error)));
      lastFailure = failure;

      // Put rate-limited / timed-out / network-failed adapters into cooldown.
      // They become reserve ammunition: eligible again after COOLDOWN_MS.
      if (COOLDOWN_CODES.has(failure.code)) {
        memory = withCooldown(memory, adapter.id, now());
      }

      emit(options, attempts, {
        type: 'provider:failed',
        providerId: adapter.id,
        message: failure.message,
        code: failure.code,
        attempt,
      });
    }

    cursor = nextIndex(cursor, active.length);
  }

  // All shots exhausted ──────────────────────────────────────────────────────
  emit(options, attempts, {
    type: 'revolver:exhausted',
    providerId: lastFailure.providerId,
    message: `All ${maxShots} providers exhausted.`,
    code: lastFailure.code,
    attempt: maxShots,
  });

  // Signal consent-required when no-key routes were the only remaining option.
  if (noKeyRoutesBlocked) {
    return {
      ok: false,
      consentRequired: true,
      reason: 'no_key_routes_blocked',
      memory,
      attempts,
    };
  }

  return { ok: false, failure: lastFailure, memory, attempts } satisfies LlmRevolverFailure;
}
