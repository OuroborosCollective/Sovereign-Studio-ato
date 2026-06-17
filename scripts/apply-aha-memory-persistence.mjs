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
  "import {\n  createSolutionPatternStore,\n  type SolutionPatternStore,\n} from './features/product/runtime/solutionPatternMemory';\n",
  "import {\n  createSolutionPatternStore,\n  type SolutionPatternStore,\n} from './features/product/runtime/solutionPatternMemory';\nimport {\n  loadSolutionPatternStore,\n  saveSolutionPatternStore,\n} from './features/product/runtime/solutionPatternPersistence';\n",
);

once(
  "  const [solutionPatternStore, setSolutionPatternStore] = useState(() => createSolutionPatternStore());\n",
  "  const [solutionPatternStore, setSolutionPatternStore] = useState(() => {\n    if (typeof window === 'undefined') return createSolutionPatternStore();\n    return loadSolutionPatternStore(window.localStorage).store;\n  });\n",
);

once(
  "  const pushTelemetry = (\n    stage: Parameters<typeof createTelemetryEvent>[0],\n    level: Parameters<typeof createTelemetryEvent>[1],\n    label: string,\n    message: string,\n    details?: Parameters<typeof createTelemetryEvent>[4],\n  ) => {\n    setTelemetry((state) => appendTelemetryEvent(state, createTelemetryEvent(stage, level, label, message, details)));\n  };\n",
  "  const pushTelemetry = (\n    stage: Parameters<typeof createTelemetryEvent>[0],\n    level: Parameters<typeof createTelemetryEvent>[1],\n    label: string,\n    message: string,\n    details?: Parameters<typeof createTelemetryEvent>[4],\n  ) => {\n    setTelemetry((state) => appendTelemetryEvent(state, createTelemetryEvent(stage, level, label, message, details)));\n  };\n\n  useEffect(() => {\n    if (typeof window === 'undefined') return;\n    const result = saveSolutionPatternStore(window.localStorage, solutionPatternStore);\n    if (!result.ok) pushTelemetry('memory', 'warning', 'aha-memory:persist-failed', result.summary);\n    // Store persistence follows solutionPatternStore changes only.\n    // eslint-disable-next-line react-hooks/exhaustive-deps\n  }, [solutionPatternStore]);\n",
);

if (changed) {
  writeFileSync(file, source);
  console.log(`${file}: aha memory persistence patched`);
} else {
  console.log(`${file}: already patched`);
}
