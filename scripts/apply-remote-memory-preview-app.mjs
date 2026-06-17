#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const file = 'src/App.tsx';
let source = readFileSync(file, 'utf8');
let changed = false;

function once(from, to) {
  if (source.includes(to)) return;
  if (!source.includes(from)) throw new Error(`Expected block not found in ${file}`);
  source = source.replace(from, to);
  changed = true;
}

once(
  "import { pullRemoteUpdatesIntoSolutionMemory } from './features/product/runtime/remoteMemoryGatewayBridge';\n",
  "import { pullRemoteUpdatesIntoSolutionMemory } from './features/product/runtime/remoteMemoryGatewayBridge';\nimport {\n  buildExternalMemorySyncPreview,\n  type ExternalMemorySyncPreview,\n} from './features/product/runtime/externalMemorySyncPreview';\n",
);

once(
  "  const [remoteMemoryMonitoring, setRemoteMemoryMonitoring] = useState<ExternalMemoryMonitoringResult | null>(null);\n",
  "  const [remoteMemoryMonitoring, setRemoteMemoryMonitoring] = useState<ExternalMemoryMonitoringResult | null>(null);\n  const [remoteMemoryPreview, setRemoteMemoryPreview] = useState<ExternalMemorySyncPreview | null>(null);\n",
);

once(
  "  const handleRemoteMemorySync = () => {\n",
  "  const handleRemoteMemoryPreview = () => {\n    void withRemoteMemoryBusy(async () => {\n      const preview = buildExternalMemorySyncPreview({ config: remoteMemoryConfig, scanRegistry, solutionStore: solutionPatternStore });\n      setRemoteMemoryPreview(preview);\n      pushTelemetry('memory', preview.valid ? 'success' : 'warning', 'remote-memory:preview', preview.summary, { items: preview.itemCount });\n      return preview;\n    });\n  };\n\n  const handleRemoteMemorySync = () => {\n",
);

once(
  "          monitoringResult={remoteMemoryMonitoring}\n",
  "          monitoringResult={remoteMemoryMonitoring}\n          previewResult={remoteMemoryPreview}\n",
);

once(
  "          onMonitoring={handleRemoteMemoryMonitoring}\n",
  "          onMonitoring={handleRemoteMemoryMonitoring}\n          onPreview={handleRemoteMemoryPreview}\n",
);

if (changed) writeFileSync(file, source);
console.log(`${file}: ${changed ? 'preview app bridge patched' : 'already patched'}`);
