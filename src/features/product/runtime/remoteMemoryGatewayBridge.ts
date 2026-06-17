import type { ExternalMemorySyncConfig } from './externalMemorySync';
import { pullExternalMemoryUpdates } from './externalMemorySync';
import { fetchExternalMemoryMonitoring, type ExternalMemoryMonitoringResult } from './externalMemoryMonitoring';
import { intakeRemoteMemoryUpdates, type RemoteMemoryUpdateIntakeResult } from './remoteMemoryUpdateIntake';
import { validateSolutionPatternStore, type SolutionPatternStore } from './solutionPatternMemory';

export interface RemoteMemoryGatewayBridgeResult {
  monitoring: ExternalMemoryMonitoringResult;
  updates: Awaited<ReturnType<typeof pullExternalMemoryUpdates>>;
  intake: RemoteMemoryUpdateIntakeResult;
  store: SolutionPatternStore;
  ok: boolean;
  summary: string;
}

export interface RemoteMemoryPullBridgeResult {
  updates: Awaited<ReturnType<typeof pullExternalMemoryUpdates>>;
  intake: RemoteMemoryUpdateIntakeResult;
  store: SolutionPatternStore;
  ok: boolean;
  summary: string;
}

export async function pullRemoteUpdatesIntoSolutionMemory(input: {
  config: ExternalMemorySyncConfig;
  store: SolutionPatternStore;
  now?: number;
  fetcher?: typeof fetch;
}): Promise<RemoteMemoryPullBridgeResult> {
  const storeValidation = validateSolutionPatternStore(input.store);
  if (!storeValidation.valid) {
    const intake = {
      accepted: 0,
      rejected: 0,
      store: input.store,
      rejections: storeValidation.errors,
      validation: storeValidation,
      summary: `Remote update intake blocked because local store is invalid: ${storeValidation.summary}`,
    };
    return {
      updates: {
        status: 'soft-failed',
        ok: false,
        items: [],
        validation: storeValidation,
        summary: storeValidation.summary,
      },
      intake,
      store: input.store,
      ok: false,
      summary: intake.summary,
    };
  }

  const updates = await pullExternalMemoryUpdates({ config: input.config, fetcher: input.fetcher });
  const intake = intakeRemoteMemoryUpdates(input.store, updates.items, input.now ?? Date.now());
  return {
    updates,
    intake,
    store: intake.store,
    ok: updates.ok && intake.validation.valid,
    summary: `Gateway updates: ${updates.summary} Intake: ${intake.summary}`,
  };
}

export async function monitorAndPullRemoteUpdatesIntoSolutionMemory(input: {
  config: ExternalMemorySyncConfig;
  store: SolutionPatternStore;
  now?: number;
  fetcher?: typeof fetch;
}): Promise<RemoteMemoryGatewayBridgeResult> {
  const monitoring = await fetchExternalMemoryMonitoring({ config: input.config, fetcher: input.fetcher });
  const pull = await pullRemoteUpdatesIntoSolutionMemory(input);
  return {
    monitoring,
    updates: pull.updates,
    intake: pull.intake,
    store: pull.store,
    ok: monitoring.ok && pull.ok,
    summary: `Monitoring: ${monitoring.summary} ${pull.summary}`,
  };
}
