import React, { useEffect, useMemo, useState } from 'react';
import { RemoteMemoryPanel } from '../components/RemoteMemoryPanel';
import type { ScanFindingRegistry } from '../runtime/scanFindingRegistry';
import { summarizeScanFindingRegistry } from '../runtime/scanFindingRegistry';
import {
  buildExternalMemoryDeleteRequest,
  buildExternalMemorySyncPayload,
  checkExternalMemoryHealth,
  deleteExternalMemoryData,
  searchExternalMemory,
  syncExternalMemory,
  type ExternalMemoryDeleteResult,
  type ExternalMemoryHealthResult,
  type ExternalMemoryPullUpdatesResult,
  type ExternalMemorySearchResult,
  type ExternalMemorySyncConfig,
  type ExternalMemorySyncResult,
} from '../runtime/externalMemorySync';
import {
  fetchExternalMemoryMonitoring,
  type ExternalMemoryMonitoringResult,
} from '../runtime/externalMemoryMonitoring';
import { buildExternalMemorySyncPreview, type ExternalMemorySyncPreview } from '../runtime/externalMemorySyncPreview';
import { pullRemoteUpdatesIntoSolutionMemory } from '../runtime/remoteMemoryGatewayBridge';
import type { RemoteMemoryUpdateIntakeResult } from '../runtime/remoteMemoryUpdateIntake';
import type { SolutionPatternStore } from '../runtime/solutionPatternMemory';
import type { SovereignTelemetryEvent, SovereignTelemetryLevel, SovereignTelemetryStage } from '../runtime/sovereignTelemetry';
import { remoteMemoryErrorMessage } from '../runtime/remoteMemoryContainerRuntime';
import {
  createSovereignDependencyLifecycleState,
  recordSovereignDependencyFailure,
  recordSovereignDependencySuccess,
  startSovereignDependencyCheck,
  type SovereignDependencyLifecycleState,
} from '../runtime/sovereignDependencyLifecycle';
import { publishSovereignDependencyCoachSignal } from '../runtime/sovereignDependencyCoachBridge';

export type RemoteMemoryContainerTelemetry = (
  stage: SovereignTelemetryStage,
  level: SovereignTelemetryLevel,
  label: string,
  message: string,
  details?: SovereignTelemetryEvent['details'],
) => void;

export interface RemoteMemoryContainerProps {
  config: ExternalMemorySyncConfig;
  onConfigChange: (config: ExternalMemorySyncConfig) => void;
  scanRegistry: ScanFindingRegistry;
  solutionPatternStore: SolutionPatternStore;
  onSolutionPatternStoreChange: (store: SolutionPatternStore) => void;
  mission: string;
  onTelemetry: RemoteMemoryContainerTelemetry;
}

const LEGACY_BUNDLED_REMOTE_MEMORY_HOST = '46.202.154.25';
const LEGACY_BUNDLED_REMOTE_MEMORY_PORT = '8088';

function isLegacyBundledRemoteMemoryGateway(config: ExternalMemorySyncConfig): boolean {
  try {
    const gateway = new URL(config.gatewayUrl.trim());
    return gateway.protocol === 'http:'
      && gateway.hostname === LEGACY_BUNDLED_REMOTE_MEMORY_HOST
      && gateway.port === LEGACY_BUNDLED_REMOTE_MEMORY_PORT;
  } catch {
    return false;
  }
}

function normalizeRemoteMemoryRuntimeConfig(config: ExternalMemorySyncConfig): ExternalMemorySyncConfig {
  if (!isLegacyBundledRemoteMemoryGateway(config)) return config;

  return {
    ...config,
    enabled: false,
    consentAccepted: false,
    gatewayUrl: '',
    workspaceId: 'local-workspace',
    contributorId: 'local-contributor',
    allowSelfHostedHttp: false,
  };
}

function sameRemoteMemoryRuntimeConfig(a: ExternalMemorySyncConfig, b: ExternalMemorySyncConfig): boolean {
  return a.enabled === b.enabled
    && a.consentAccepted === b.consentAccepted
    && a.gatewayUrl === b.gatewayUrl
    && a.workspaceId === b.workspaceId
    && a.collectionName === b.collectionName
    && a.contributorId === b.contributorId
    && a.mode === b.mode
    && a.clientAccessKey === b.clientAccessKey
    && a.allowSelfHostedHttp === b.allowSelfHostedHttp
    && a.includeScanFindings === b.includeScanFindings
    && a.includeLearningPatterns === b.includeLearningPatterns
    && a.includeSolutionPatterns === b.includeSolutionPatterns;
}

function createRemoteMemoryDependency(): SovereignDependencyLifecycleState {
  return createSovereignDependencyLifecycleState(
    'remote-memory-gateway',
    'remote-memory',
    'Remote Memory has not been checked yet.',
  );
}

export function RemoteMemoryContainer({
  config,
  onConfigChange,
  scanRegistry,
  solutionPatternStore,
  onSolutionPatternStoreChange,
  mission,
  onTelemetry,
}: RemoteMemoryContainerProps) {
  const effectiveConfig = useMemo(() => normalizeRemoteMemoryRuntimeConfig(config), [config]);
  const legacyGatewayWasNeutralized = effectiveConfig !== config;
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<ExternalMemoryHealthResult | null>(null);
  const [monitoring, setMonitoring] = useState<ExternalMemoryMonitoringResult | null>(null);
  const [preview, setPreview] = useState<ExternalMemorySyncPreview | null>(null);
  const [cleanupResult, setCleanupResult] = useState<ExternalMemoryDeleteResult | null>(null);
  const [cleanupConfirmationText, setCleanupConfirmationText] = useState('');
  const [cleanupScopeConfirmed, setCleanupScopeConfirmed] = useState(false);
  const [syncResult, setSyncResult] = useState<ExternalMemorySyncResult | null>(null);
  const [searchResult, setSearchResult] = useState<ExternalMemorySearchResult | null>(null);
  const [updates, setUpdates] = useState<ExternalMemoryPullUpdatesResult | null>(null);
  const [intake, setIntake] = useState<RemoteMemoryUpdateIntakeResult | null>(null);
  const [remoteMemoryDependency, setRemoteMemoryDependency] = useState(createRemoteMemoryDependency);

  useEffect(() => {
    if (!sameRemoteMemoryRuntimeConfig(config, effectiveConfig)) {
      onConfigChange(effectiveConfig);
      onTelemetry('memory', 'warning', 'remote-memory:unsafe-default-neutralized', 'Bundled non-local HTTP Remote Memory gateway was disabled for release safety. Configure an HTTPS gateway or explicit local testing endpoint before enabling Remote Memory.');
    }
  }, [config, effectiveConfig, onConfigChange, onTelemetry]);

  const publishRemoteDependency = (next: SovereignDependencyLifecycleState) => {
    setRemoteMemoryDependency(next);
    publishSovereignDependencyCoachSignal(next);
  };

  const withBusy = async <T,>(task: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    const started = startSovereignDependencyCheck(remoteMemoryDependency).state;
    publishRemoteDependency(started);
    try {
      const result = await task();
      publishRemoteDependency(recordSovereignDependencySuccess(started, 'Remote Memory operation completed.').state);
      return result;
    } catch (error) {
      const message = remoteMemoryErrorMessage(error);
      publishRemoteDependency(recordSovereignDependencyFailure(started, {}, message).state);
      onTelemetry('memory', 'error', 'remote-memory:failed', message);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = () => {
    const result = buildExternalMemorySyncPreview({ config: effectiveConfig, scanRegistry, solutionStore: solutionPatternStore });
    setPreview(result);
    onTelemetry('memory', result.valid ? 'success' : 'warning', 'remote-memory:preview', result.summary, { items: result.itemCount });
  };

  const handleHealth = () => {
    void withBusy(async () => {
      const result = await checkExternalMemoryHealth({ config: effectiveConfig });
      setHealth(result);
      onTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:health', result.summary);
      return result;
    });
  };

  const handleMonitoring = () => {
    void withBusy(async () => {
      const result = await fetchExternalMemoryMonitoring({ config: effectiveConfig });
      setMonitoring(result);
      onTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:monitoring', result.summary, {
        milvusConnected: result.monitoring?.milvusConnected ?? false,
      });
      return result;
    });
  };

  const handleSync = () => {
    void withBusy(async () => {
      const payload = buildExternalMemorySyncPayload({ config: effectiveConfig, scanRegistry, solutionStore: solutionPatternStore });
      const result = await syncExternalMemory({ config: effectiveConfig, payload });
      setSyncResult(result);
      onTelemetry('memory', result.accepted ? 'success' : 'warning', 'remote-memory:sync', result.summary, { items: payload.items.length });
      return result;
    });
  };

  const handleSearch = () => {
    void withBusy(async () => {
      const query = mission.trim() || summarizeScanFindingRegistry(scanRegistry);
      const result = await searchExternalMemory({ config: effectiveConfig, query, limit: 8 });
      setSearchResult(result);
      onTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:search', result.summary, { items: result.items.length });
      return result;
    });
  };

  const handlePullUpdates = () => {
    void withBusy(async () => {
      const bridge = await pullRemoteUpdatesIntoSolutionMemory({ config: effectiveConfig, store: solutionPatternStore });
      setUpdates(bridge.updates);
      setIntake(bridge.intake);
      onSolutionPatternStoreChange(bridge.store);
      onTelemetry('memory', bridge.updates.ok ? 'success' : 'warning', 'remote-memory:pull-updates', bridge.updates.summary, { items: bridge.updates.items.length });
      onTelemetry('memory', bridge.intake.accepted > 0 ? 'success' : bridge.intake.rejected > 0 ? 'warning' : 'info', 'remote-memory:intake', bridge.intake.summary, { accepted: bridge.intake.accepted, rejected: bridge.intake.rejected });
      return bridge;
    });
  };

  const handleCleanupContributor = () => {
    void withBusy(async () => {
      if (!cleanupScopeConfirmed) throw new Error('Contributor cleanup scope is not confirmed.');
      const request = buildExternalMemoryDeleteRequest(effectiveConfig);
      const result = await deleteExternalMemoryData({ config: effectiveConfig, request });
      setCleanupResult(result);
      onTelemetry('memory', result.deleted ? 'success' : 'warning', 'remote-memory:cleanup-contributor', result.summary, {
        deleted: result.response?.deletedItems ?? 0,
        retainedShared: result.response?.retainedSharedItems ?? 0,
      });
      if (result.deleted) {
        setCleanupConfirmationText('');
        setCleanupScopeConfirmed(false);
      }
      return result;
    });
  };

  return (
    <RemoteMemoryPanel
      config={effectiveConfig}
      syncResult={syncResult}
      healthResult={health}
      monitoringResult={monitoring}
      previewResult={preview}
      cleanupResult={cleanupResult}
      searchResult={searchResult}
      updatesResult={updates}
      intakeResult={intake}
      isBusy={busy}
      cleanupConfirmationText={cleanupConfirmationText}
      cleanupScopeConfirmed={cleanupScopeConfirmed}
      onChange={onConfigChange}
      onCleanupConfirmationTextChange={setCleanupConfirmationText}
      onCleanupScopeConfirmedChange={setCleanupScopeConfirmed}
      onHealth={handleHealth}
      onMonitoring={handleMonitoring}
      onPreview={handlePreview}
      onSync={handleSync}
      onSearch={handleSearch}
      onPullUpdates={handlePullUpdates}
      onCleanupContributor={handleCleanupContributor}
      safetyNotice={legacyGatewayWasNeutralized ? 'Release safety: the bundled non-local HTTP Remote Memory gateway was disabled. Use HTTPS or explicit local testing before enabling Remote Memory.' : undefined}
    />
  );
}
