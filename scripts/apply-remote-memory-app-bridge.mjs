#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const appPath = 'src/App.tsx';
let source = readFileSync(appPath, 'utf8');
let next = source;

function insertAfterOnce(text, anchor, insert, marker) {
  if (text.includes(marker)) return text;
  if (!text.includes(anchor)) throw new Error(`Anchor not found: ${anchor.slice(0, 80)}`);
  return text.replace(anchor, anchor + insert);
}

function replaceOnce(text, before, after) {
  if (text.includes(after)) return text;
  if (!text.includes(before)) throw new Error(`Replacement target not found: ${before.slice(0, 80)}`);
  return text.replace(before, after);
}

next = insertAfterOnce(
  next,
  `} from './features/product/runtime/externalMemorySync';\n`,
  `import {\n  fetchExternalMemoryMonitoring,\n  type ExternalMemoryMonitoringResult,\n} from './features/product/runtime/externalMemoryMonitoring';\nimport { pullRemoteUpdatesIntoSolutionMemory } from './features/product/runtime/remoteMemoryGatewayBridge';\nimport {\n  createSolutionPatternStore,\n  type SolutionPatternStore,\n} from './features/product/runtime/solutionPatternMemory';\nimport type { RemoteMemoryUpdateIntakeResult } from './features/product/runtime/remoteMemoryUpdateIntake';\n`,
  'remoteMemoryGatewayBridge',
);

next = insertAfterOnce(
  next,
  `function encodeGitHubContentPath(path: string): string {\n  return path.split('/').map((part) => encodeURIComponent(part)).join('/');\n}\n\n`,
  `function formatSolutionPatternHints(store: SolutionPatternStore): string {\n  const patterns = store.patterns\n    .filter((pattern) => pattern.status === 'active')\n    .sort((a, b) => b.successfulUses - a.successfulUses || b.updatedAt - a.updatedAt)\n    .slice(0, 5);\n\n  if (!patterns.length) return '';\n\n  return [\n    'Remote Aha Memory:',\n    ...patterns.map((pattern) => \`- \${pattern.category} \${pattern.fileExtension}: \${pattern.solutionSummary}\`),\n  ].join('\\n');\n}\n\n`,
  'formatSolutionPatternHints',
);

next = insertAfterOnce(
  next,
  `  const [scanRegistry, setScanRegistry] = useState(() => createScanFindingRegistry());\n`,
  `  const [solutionPatternStore, setSolutionPatternStore] = useState(() => createSolutionPatternStore());\n`,
  'solutionPatternStore',
);

if (!next.includes(`contributorId: 'sovereign-local-install'`)) {
  next = replaceOnce(
    next,
    `    collectionName: 'sovereign_logic_patterns',\n    allowSelfHostedHttp: true,\n`,
    `    collectionName: 'sovereign_logic_patterns',\n    contributorId: 'sovereign-local-install',\n    allowSelfHostedHttp: true,\n`,
  );
}

next = insertAfterOnce(
  next,
  `  const [remoteMemoryHealth, setRemoteMemoryHealth] = useState<ExternalMemoryHealthResult | null>(null);\n`,
  `  const [remoteMemoryMonitoring, setRemoteMemoryMonitoring] = useState<ExternalMemoryMonitoringResult | null>(null);\n`,
  'remoteMemoryMonitoring',
);

next = insertAfterOnce(
  next,
  `  const [remoteMemoryUpdates, setRemoteMemoryUpdates] = useState<ExternalMemoryPullUpdatesResult | null>(null);\n`,
  `  const [remoteMemoryIntake, setRemoteMemoryIntake] = useState<RemoteMemoryUpdateIntakeResult | null>(null);\n`,
  'remoteMemoryIntake',
);

next = insertAfterOnce(
  next,
  `  const coverageReport = buildRuntimeValidationCoverageReport();\n`,
  `  const solutionPatternHints = formatSolutionPatternHints(solutionPatternStore);\n`,
  'solutionPatternHints',
);

next = insertAfterOnce(
  next,
  `  const handleRemoteMemoryHealth = () => {\n    void withRemoteMemoryBusy(async () => {\n      const result = await checkExternalMemoryHealth({ config: remoteMemoryConfig });\n      setRemoteMemoryHealth(result);\n      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:health', result.summary);\n      return result;\n    });\n  };\n\n`,
  `  const handleRemoteMemoryMonitoring = () => {\n    void withRemoteMemoryBusy(async () => {\n      const result = await fetchExternalMemoryMonitoring({ config: remoteMemoryConfig });\n      setRemoteMemoryMonitoring(result);\n      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:monitoring', result.summary, {\n        milvusConnected: result.monitoring?.milvusConnected ?? false,\n      });\n      return result;\n    });\n  };\n\n`,
  'handleRemoteMemoryMonitoring',
);

next = replaceOnce(
  next,
  `      const payload = buildExternalMemorySyncPayload({ config: remoteMemoryConfig, scanRegistry });`,
  `      const payload = buildExternalMemorySyncPayload({ config: remoteMemoryConfig, scanRegistry, solutionStore: solutionPatternStore });`,
);

next = replaceOnce(
  next,
  `  const handleRemoteMemoryPullUpdates = () => {\n    void withRemoteMemoryBusy(async () => {\n      const result = await pullExternalMemoryUpdates({ config: remoteMemoryConfig });\n      setRemoteMemoryUpdates(result);\n      pushTelemetry('memory', result.ok ? 'success' : 'warning', 'remote-memory:pull-updates', result.summary, { items: result.items.length });\n      return result;\n    });\n  };`,
  `  const handleRemoteMemoryPullUpdates = () => {\n    void withRemoteMemoryBusy(async () => {\n      const bridge = await pullRemoteUpdatesIntoSolutionMemory({\n        config: remoteMemoryConfig,\n        store: solutionPatternStore,\n      });\n      setRemoteMemoryUpdates(bridge.updates);\n      setRemoteMemoryIntake(bridge.intake);\n      setSolutionPatternStore(bridge.store);\n      pushTelemetry('memory', bridge.updates.ok ? 'success' : 'warning', 'remote-memory:pull-updates', bridge.updates.summary, { items: bridge.updates.items.length });\n      pushTelemetry('memory', bridge.intake.accepted > 0 ? 'success' : bridge.intake.rejected > 0 ? 'warning' : 'info', 'remote-memory:intake', bridge.intake.summary, { accepted: bridge.intake.accepted, rejected: bridge.intake.rejected });\n      return bridge;\n    });\n  };`,
);

next = replaceOnce(
  next,
  `      const pkg = buildSovereignPackageFromRepoFiles({\n        mission: nextMission,`,
  `      const missionWithAha = solutionPatternHints ? \`${'${nextMission}'}\\n\\n${'${solutionPatternHints}'}\` : nextMission;\n      const pkg = buildSovereignPackageFromRepoFiles({\n        mission: missionWithAha,`,
);

next = replaceOnce(
  next,
  `      setSovereignSummary(\`${'${summarizeSovereignPackage(pkg, repoFiles)}'}\\n${'${review.summary}'}\`);`,
  `      setSovereignSummary(\`${'${summarizeSovereignPackage(pkg, repoFiles)}'}\\n${'${review.summary}'}${'${solutionPatternHints ? `\\n${solutionPatternHints}` : ``}'}\`);`,
);

next = replaceOnce(
  next,
  `        fileReview: review,\n        suggestions: pkg.suggestions,`,
  `        fileReview: review,\n        remoteAhaMemory: solutionPatternHints,\n        suggestions: pkg.suggestions,`,
);

next = insertAfterOnce(
  next,
  `            summarizeScanFindingRegistry(scanRegistry),\n            '',\n`,
  `            'Remote Aha Memory:',\n            solutionPatternHints || 'none',\n            '',\n`,
  `'Remote Aha Memory:'`,
);

next = insertAfterOnce(
  next,
  `          <p className="mt-1 text-xs text-slate-400">{repoSnapshotStatus.reason}</p>\n`,
  `          {solutionPatternHints ? <pre className="mt-2 whitespace-pre-wrap rounded bg-slate-900/70 p-3 text-xs text-emerald-200">{solutionPatternHints}</pre> : null}\n`,
  '{solutionPatternHints ? <pre',
);

next = insertAfterOnce(
  next,
  `          healthResult={remoteMemoryHealth}\n`,
  `          monitoringResult={remoteMemoryMonitoring}\n`,
  'monitoringResult={remoteMemoryMonitoring}',
);

next = insertAfterOnce(
  next,
  `          updatesResult={remoteMemoryUpdates}\n`,
  `          intakeResult={remoteMemoryIntake}\n`,
  'intakeResult={remoteMemoryIntake}',
);

next = insertAfterOnce(
  next,
  `          onHealth={handleRemoteMemoryHealth}\n`,
  `          onMonitoring={handleRemoteMemoryMonitoring}\n`,
  'onMonitoring={handleRemoteMemoryMonitoring}',
);

if (next === source) {
  console.log('App.tsx already has the remote memory app bridge integration.');
} else {
  writeFileSync(appPath, next, 'utf8');
  console.log('App.tsx remote memory app bridge integration applied.');
}
