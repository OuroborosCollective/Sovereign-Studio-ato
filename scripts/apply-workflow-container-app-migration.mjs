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

replaceOnce(
  "import { BuilderContainer } from './features/product/containers/BuilderContainer';",
  "import { BuilderContainer } from './features/product/containers/BuilderContainer';\nimport { WorkflowContainer } from './features/product/containers/WorkflowContainer';",
);

removeOnce("import { WorkflowRepairPanel } from './features/product/components/WorkflowRepairPanel';\n");
removeOnce("import { WorkflowWatchPanel } from './features/product/components/WorkflowWatchPanel';\n");

replaceOnce(
  `      {activeTab === 'workflow' ? (
        <WorkflowWatchPanel
          report={workflowReport}
          isWatching={isWatchingWorkflow || runtimeBusy}
          onWatch={() => { void watchLatestWorkflow(); }}
        />
      ) : null}`,
  `      {activeTab === 'workflow' ? (
        <WorkflowContainer
          mode="watch"
          report={workflowReport}
          repairPlan={repairPlan}
          isWatching={isWatchingWorkflow}
          runtimeBusy={runtimeBusy}
          hasDraftCommit={Boolean(lastDraftCommitSha)}
          onWatch={() => { void watchLatestWorkflow(); }}
          onUseRepairMission={useRepairMission}
        />
      ) : null}`,
);

replaceOnce(
  `      {activeTab === 'repair' ? <WorkflowRepairPanel plan={repairPlan} onUseMission={useRepairMission} /> : null}`,
  `      {activeTab === 'repair' ? (
        <WorkflowContainer
          mode="repair"
          report={workflowReport}
          repairPlan={repairPlan}
          isWatching={isWatchingWorkflow}
          runtimeBusy={runtimeBusy}
          hasDraftCommit={Boolean(lastDraftCommitSha)}
          onWatch={() => { void watchLatestWorkflow(); }}
          onUseRepairMission={useRepairMission}
        />
      ) : null}`,
);

if (changed) {
  writeFileSync(file, source, 'utf8');
  console.log(`${file}: WorkflowContainer migration applied`);
} else {
  console.log(`${file}: already migrated`);
}
