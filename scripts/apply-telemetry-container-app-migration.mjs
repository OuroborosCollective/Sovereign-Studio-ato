#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const file = 'src/App.tsx';
let source = readFileSync(file, 'utf8');
let changed = false;

function replaceOnce(from, to) {
  if (source.includes(to)) return;
  if (!source.includes(from)) throw new Error(`Expected block not found in ${file}: ${from.slice(0, 120)}`);
  source = source.replace(from, to);
  changed = true;
}

function removeOnce(block) {
  if (!source.includes(block)) return;
  source = source.replace(block, '');
  changed = true;
}

removeOnce("import { SovereignTelemetryPanel } from './features/product/components/SovereignTelemetryPanel';\n");
replaceOnce(
  "import { RepoSnapshotContainer } from './features/product/containers/RepoSnapshotContainer';",
  "import { RepoSnapshotContainer } from './features/product/containers/RepoSnapshotContainer';\nimport { TelemetryContainer } from './features/product/containers/TelemetryContainer';",
);

replaceOnce(
  `      {activeTab === 'telemetry' ? (
        <SovereignTelemetryPanel
          state={telemetry}
          expanded={telemetryExpanded}
          onToggle={() => setTelemetryExpanded((value) => !value)}
        />
      ) : null}`,
  `      {activeTab === 'telemetry' ? (
        <TelemetryContainer
          state={telemetry}
          expanded={telemetryExpanded}
          onExpandedChange={setTelemetryExpanded}
        />
      ) : null}`,
);

if (changed) {
  writeFileSync(file, source, 'utf8');
  console.log(`${file}: TelemetryContainer migration applied`);
} else {
  console.log(`${file}: already migrated`);
}
