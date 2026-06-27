import { createExternalMemorySyncConfig, type ExternalMemorySyncConfig } from './externalMemorySync';
import type { ExternalMemorySyncPreview } from './externalMemorySyncPreview';

export interface RemoteMemoryContainerStatus {
  enabled: boolean;
  canRun: boolean;
  label: string;
}

export function createRemoteMemoryContainerConfig(
  overrides: Partial<ExternalMemorySyncConfig> = {},
): ExternalMemorySyncConfig {
  return {
    ...createExternalMemorySyncConfig(),
    ...overrides,
  };
}

export function buildRemoteMemoryContainerStatus(config: ExternalMemorySyncConfig, isBusy: boolean): RemoteMemoryContainerStatus {
  const enabled = Boolean(config.enabled);
  const hasGateway = config.gatewayUrl.trim().length > 0;
  const hasContributor = config.contributorId.trim().length > 0;
  const canRun = enabled && hasGateway && hasContributor && !isBusy;

  if (isBusy) return { enabled, canRun: false, label: 'Remote Memory arbeitet.' };
  if (!enabled) return { enabled, canRun: false, label: 'Remote Memory ist aus.' };
  if (!hasGateway) return { enabled, canRun: false, label: 'Gateway URL fehlt.' };
  if (!hasContributor) return { enabled, canRun: false, label: 'Contributor ID fehlt.' };
  return { enabled, canRun, label: 'Remote Memory ist bereit.' };
}

export function summarizeRemoteMemoryPreview(preview: ExternalMemorySyncPreview | null): string {
  if (!preview) return 'Noch keine Sync Preview erzeugt.';
  return [
    preview.summary,
    `items=${preview.itemCount}`,
    `bytes=${preview.estimatedBytes}`,
    `scan=${preview.kindCounts['scan-finding']}`,
    `learning=${preview.kindCounts['learning-pattern']}`,
    `solution=${preview.kindCounts['solution-pattern']}`,
  ].join(' | ');
}

export function remoteMemoryErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  if (typeof error === 'string' && error.trim()) return error.trim();
  return 'Remote memory action failed.';
}
