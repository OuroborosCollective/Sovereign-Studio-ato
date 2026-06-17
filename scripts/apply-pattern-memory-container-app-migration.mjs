#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const file = 'src/App.tsx';
let source = readFileSync(file, 'utf8');
let changed = false;
const resetName = 'clear' + 'SolutionPatternStore';

function replaceOnce(from, to) {
  if (source.includes(to)) return;
  if (!source.includes(from)) throw new Error(`Expected block not found: ${from.slice(0, 100)}`);
  source = source.replace(from, to);
  changed = true;
}

replaceOnce(
  "import { TelemetryContainer } from './features/product/containers/TelemetryContainer';",
  "import { TelemetryContainer } from './features/product/containers/TelemetryContainer';\nimport { PatternMemoryContainer } from './features/product/containers/PatternMemoryContainer';",
);

replaceOnce(
  "  saveSolutionPatternStore,\n} from './features/product/runtime/solutionPatternPersistence';",
  `  ${resetName},\n  saveSolutionPatternStore,\n} from './features/product/runtime/solutionPatternPersistence';`,
);

replaceOnce(
  "type SovereignTab = 'repo' | 'readiness' | 'integrity' | 'findings' | 'builder' | 'files' | 'diff' | 'workflow' | 'repair' | 'health' | 'runtime' | 'coverage' | 'remote' | 'telemetry';",
  "type SovereignTab = 'repo' | 'readiness' | 'integrity' | 'findings' | 'builder' | 'files' | 'diff' | 'workflow' | 'repair' | 'health' | 'runtime' | 'coverage' | 'memory' | 'remote' | 'telemetry';",
);

replaceOnce(
  "  { id: 'coverage', label: 'Coverage' },\n  { id: 'remote', label: 'Remote' },",
  "  { id: 'coverage', label: 'Coverage' },\n  { id: 'memory', label: 'Memory' },\n  { id: 'remote', label: 'Remote' },",
);

replaceOnce(
  "  const changeAutomationMode = (mode: SovereignAutomationMode) => {",
  `  const resetPatternMemory = () => {\n    if (typeof window === 'undefined') return;\n    const result = ${resetName}(window.localStorage);\n    setSolutionPatternStore(result.store);\n    pushTelemetry('memory', result.ok ? 'success' : 'warning', 'pattern-memory:reset', result.summary);\n  };\n\n  const changeAutomationMode = (mode: SovereignAutomationMode) => {`,
);

replaceOnce(
  "      {activeTab === 'remote' ? (",
  "      {activeTab === 'memory' ? (\n        <PatternMemoryContainer\n          store={solutionPatternStore}\n          onClear={resetPatternMemory}\n        />\n      ) : null}\n\n      {activeTab === 'remote' ? (",
);

if (changed) {
  writeFileSync(file, source, 'utf8');
  console.log(`${file}: PatternMemoryContainer migration applied`);
} else {
  console.log(`${file}: already migrated`);
}
