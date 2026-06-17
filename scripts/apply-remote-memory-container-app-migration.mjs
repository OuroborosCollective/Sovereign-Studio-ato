#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const file = 'src/App.tsx';
let source = readFileSync(file, 'utf8');
let changed = false;

function replaceOnce(from, to) {
  if (source.includes(to)) return;
  if (!source.includes(from)) throw new Error(`Expected block not found in ${file}: ${from.slice(0, 90)}`);
  source = source.replace(from, to);
  changed = true;
}

function removeOnce(block) {
  if (!source.includes(block)) return;
  source = source.replace(block, '');
  changed = true;
}

replaceOnce(
  "import { RemoteMemoryPanel } from './features/product/components/RemoteMemoryPanel';",
  "import { RemoteMemoryContainer } from './features/product/containers/RemoteMemoryContainer';",
);

removeOnce(`import {
  buildExternalMemorySyncPayload,
  checkExternalMemoryHealth,
  createExternalMemorySyncConfig,
  pullExternalMemoryUpdates,
  searchExternalMemory,
  syncExternalMemory,
  type ExternalMemoryHealthResult,
  type ExternalMemorySyncConfig,
  type ExternalMemoryPullUpdatesResult,
  type ExternalMemorySearchResult,
  type ExternalMemorySyncResult,
} from './features/product/runtime/externalMemorySync';
`);

replaceOnce(
  "import {\n  createSolutionPatternStore,\n  type SolutionPatternStore,\n} from './features/product/runtime/solutionPatternMemory';",
  "import {\n  createExternalMemorySyncConfig,\n  type ExternalMemorySyncConfig,\n} from './features/product/runtime/externalMemorySync';\nimport {\n  createSolutionPatternStore,\n  type SolutionPatternStore,\n} from './features/product/runtime/solutionPatternMemory';",
);

removeOnce(`import {
  fetchExternalMemoryMonitoring,
  type ExternalMemoryMonitoringResult,
} from './features/product/runtime/externalMemoryMonitoring';
`);
removeOnce("import { pullRemoteUpdatesIntoSolutionMemory } from './features/product/runtime/remoteMemoryGatewayBridge';\n");
removeOnce("import type { RemoteMemoryUpdateIntakeResult } from './features/product/runtime/remoteMemoryUpdateIntake';\n");

removeOnce(`  const [remoteMemoryHealth, setRemoteMemoryHealth] = useState<ExternalMemoryHealthResult | null>(null);
  const [remoteMemoryMonitoring, setRemoteMemoryMonitoring] = useState<ExternalMemoryMonitoringResult | null>(null);
  const [remoteMemorySync, setRemoteMemorySync] = useState<ExternalMemorySyncResult | null>(null);
  const [remoteMemorySearch, setRemoteMemorySearch] = useState<ExternalMemorySearchResult | null>(null);
  const [remoteMemoryUpdates, setRemoteMemoryUpdates] = useState<ExternalMemoryPullUpdatesResult | null>(null);
  const [remoteMemoryIntake, setRemoteMemoryIntake] = useState<RemoteMemoryUpdateIntakeResult | null>(null);
  const [isRemoteMemoryBusy, setIsRemoteMemoryBusy] = useState(false);
`);

removeOnce(`  const withRemoteMemoryBusy = async <T,>(task: () => Promise<T>): Promise<T | null> => {
    setIsRemoteMemoryBusy(true);
    try {
      return await task();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Remote memory action failed.';
      pushTelemetry('memory', 'error', 'remote-memory:failed', stripTokenFromText(message, githubToken));
      return null;
    } finally {
      setIsRemoteMemoryBusy(false);
    }
  };

  const handleRemoteMemoryHealth = () => {
    void withRemoteMemoryBusy(async () => {
      const result = await checkExternalMemoryHealth({ config: remoteMemoryConfig });
      setRemoteMemoryHealth(result);
      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:health', result.summary);
      return result;
    });
  };

  const handleRemoteMemoryMonitoring = () => {
    void withRemoteMemoryBusy(async () => {
      const result = await fetchExternalMemoryMonitoring({ config: remoteMemoryConfig });
      setRemoteMemoryMonitoring(result);
      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:monitoring', result.summary, {
        milvusConnected: result.monitoring?.milvusConnected ?? false,
      });
      return result;
    });
  };

  const handleRemoteMemorySync = () => {
    void withRemoteMemoryBusy(async () => {
      const payload = buildExternalMemorySyncPayload({ config: remoteMemoryConfig, scanRegistry, solutionStore: solutionPatternStore });
      const result = await syncExternalMemory({ config: remoteMemoryConfig, payload });
      setRemoteMemorySync(result);
      pushTelemetry('memory', result.accepted ? 'success' : 'warning', 'remote-memory:sync', result.summary, { items: payload.items.length });
      return result;
    });
  };

  const handleRemoteMemorySearch = () => {
    void withRemoteMemoryBusy(async () => {
      const result = await searchExternalMemory({ config: remoteMemoryConfig, query: mission.trim() || summarizeScanFindingRegistry(scanRegistry), limit: 8 });
      setRemoteMemorySearch(result);
      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:search', result.summary, { items: result.items.length });
      return result;
    });
  };

  const handleRemoteMemoryPullUpdates = () => {
    void withRemoteMemoryBusy(async () => {
      const bridge = await pullRemoteUpdatesIntoSolutionMemory({
        config: remoteMemoryConfig,
        store: solutionPatternStore,
      });
      setRemoteMemoryUpdates(bridge.updates);
      setRemoteMemoryIntake(bridge.intake);
      setSolutionPatternStore(bridge.store);
      pushTelemetry('memory', bridge.updates.ok ? 'success' : 'warning', 'remote-memory:pull-updates', bridge.updates.summary, { items: bridge.updates.items.length });
      pushTelemetry('memory', bridge.intake.accepted > 0 ? 'success' : bridge.intake.rejected > 0 ? 'warning' : 'info', 'remote-memory:intake', bridge.intake.summary, { accepted: bridge.intake.accepted, rejected: bridge.intake.rejected });
      return bridge;
    });
  };

`);

replaceOnce(
  `      {activeTab === 'remote' ? (
        <RemoteMemoryPanel
          config={remoteMemoryConfig}
          syncResult={remoteMemorySync}
          healthResult={remoteMemoryHealth}
          monitoringResult={remoteMemoryMonitoring}
          searchResult={remoteMemorySearch}
          updatesResult={remoteMemoryUpdates}
          intakeResult={remoteMemoryIntake}
          isBusy={isRemoteMemoryBusy}
          onChange={setRemoteMemoryConfig}
          onHealth={handleRemoteMemoryHealth}
          onMonitoring={handleRemoteMemoryMonitoring}
          onSync={handleRemoteMemorySync}
          onSearch={handleRemoteMemorySearch}
          onPullUpdates={handleRemoteMemoryPullUpdates}
        />
      ) : null}`,
  `      {activeTab === 'remote' ? (
        <RemoteMemoryContainer
          config={remoteMemoryConfig}
          onConfigChange={setRemoteMemoryConfig}
          scanRegistry={scanRegistry}
          solutionPatternStore={solutionPatternStore}
          onSolutionPatternStoreChange={setSolutionPatternStore}
          mission={mission}
          onTelemetry={pushTelemetry}
        />
      ) : null}`,
);

if (changed) {
  writeFileSync(file, source, 'utf8');
  console.log(`${file}: RemoteMemoryContainer migration applied`);
} else {
  console.log(`${file}: already migrated`);
}
