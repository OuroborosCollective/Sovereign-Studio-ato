import React, { useState } from 'react';
import { RemoteMemoryPanel } from '../components/RemoteMemoryPanel';
import type { ScanFindingRegistry } from '../runtime/scanFindingRegistry';
import { summarizeScanFindingRegistry } from '../runtime/scanFindingRegistry';
import {
  buildExternalMemorySyncPayload,
  checkExternalMemoryHealth,
  searchExternalMemory,
  syncExternalMemory,
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

export function RemoteMemoryContainer({
  config,
  onConfigChange,
  scanRegistry,
  solutionPatternStore,
  onSolutionPatternStoreChange,
  mission,
  onTelemetry,
}: RemoteMemoryContainerProps) {
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<ExternalMemoryHealthResult | null>(null);
  const [monitoring, setMonitoring] = useState<ExternalMemoryMonitoringResult | null>(null);
  const [preview, setPreview] = useState<ExternalMemorySyncPreview | null>(null);
  const [syncResult, setSyncResult] = useState<ExternalMemorySyncResult | null>(null);
  const [searchResult, setSearchResult] = useState<ExternalMemorySearchResult | null>(null);
  const [updates, setUpdates] = useState<ExternalMemoryPullUpdatesResult | null>(null);
  const [intake, setIntake] = useState<RemoteMemoryUpdateIntakeResult | null>(null);

  const withBusy = async <T,>(task: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    try {
      return await task();
    } catch (error) {
      onTelemetry('memory', 'error', 'remote-memory:failed', remoteMemoryErrorMessage(error));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = () => {
    const result = buildExternalMemorySyncPreview({ config, scanRegistry, solutionStore: solutionPatternStore });
    setPreview(result);
    onTelemetry('memory', result.valid ? 'success' : 'warning', 'remote-memory:preview', result.summary, { items: result.itemCount });
  };

  const handleHealth = () => {
    void withBusy(async () => {
      const result = await checkExternalMemoryHealth({ config });
      setHealth(result);
      onTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:health', result.summary);
      return result;
    });
  };

  const handleMonitoring = () => {
    void withBusy(async () => {
      const result = await fetchExternalMemoryMonitoring({ config });
      setMonitoring(result);
      onTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:monitoring', result.summary, {
        milvusConnected: result.monitoring?.milvusConnected ?? false,
      });
      return result;
    });
  };

  const handleSync = () => {
    void withBusy(async () => {
      const payload = buildExternalMemorySyncPayload({ config, scanRegistry, solutionStore: solutionPatternStore });
      const result = await syncExternalMemory({ config, payload });
      setSyncResult(result);
      onTelemetry('memory', result.accepted ? 'success' : 'warning', 'remote-memory:sync', result.summary, { items: payload.items.length });
      return result;
    });
  };

  const handleSearch = () => {
    void withBusy(async () => {
      const query = mission.trim() || summarizeScanFindingRegistry(scanRegistry);
      const result = await searchExternalMemory({ config, query, limit: 8 });
      setSearchResult(result);
      onTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:search', result.summary, { items: result.items.length });
      return result;
    });
  };

  const handlePullUpdates = () => {
    void withBusy(async () => {
      const bridge = await pullRemoteUpdatesIntoSolutionMemory({ config, store: solutionPatternStore });
      setUpdates(bridge.updates);
      setIntake(bridge.intake);
      onSolutionPatternStoreChange(bridge.store);
      onTelemetry('memory', bridge.updates.ok ? 'success' : 'warning', 'remote-memory:pull-updates', bridge.updates.summary, { items: bridge.updates.items.length });
      onTelemetry('memory', bridge.intake.accepted > 0 ? 'success' : bridge.intake.rejected > 0 ? 'warning' : 'info', 'remote-memory:intake', bridge.intake.summary, { accepted: bridge.intake.accepted, rejected: bridge.intake.rejected });
      return bridge;
    });
  };

  return (
    <RemoteMemoryPanel
      config={config}
      syncResult={syncResult}
      healthResult={health}
      monitoringResult={monitoring}
      previewResult={preview}
      searchResult={searchResult}
      updatesResult={updates}
      intakeResult={intake}
      isBusy={busy}
      onChange={onConfigChange}
      onHealth={handleHealth}
      onMonitoring={handleMonitoring}
      onPreview={handlePreview}
      onSync={handleSync}
      onSearch={handleSearch}
      onPullUpdates={handlePullUpdates}
    />
  );
}
