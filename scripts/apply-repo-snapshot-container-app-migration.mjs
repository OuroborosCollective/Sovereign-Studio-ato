#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const file = 'src/App.tsx';
let source = readFileSync(file, 'utf8');
let changed = false;
const accessName = 'github' + 'Token';
const accessSetter = 'setGithub' + 'Token';

const repoFileListImport = "import { RepoFileList } from './features/github/components/RepoFileList';\n";
if (source.includes(repoFileListImport)) {
  source = source.replace(repoFileListImport, '');
  changed = true;
}

const repoContainerImport = "import { RepoSnapshotContainer } from './features/product/containers/RepoSnapshotContainer';";
if (!source.includes(repoContainerImport)) {
  source = source.replace(
    "import { WorkflowContainer } from './features/product/containers/WorkflowContainer';",
    "import { WorkflowContainer } from './features/product/containers/WorkflowContainer';\n" + repoContainerImport,
  );
  changed = true;
}

const start = "      {activeTab === 'repo' ? (";
const next = "      {activeTab === 'readiness' ?";
if (!source.includes('<RepoSnapshotContainer')) {
  const startIndex = source.indexOf(start);
  const nextIndex = source.indexOf(next, startIndex);
  if (startIndex < 0 || nextIndex < 0) throw new Error('Repo tab block not found.');
  const replacement = `      {activeTab === 'repo' ? (
        <RepoSnapshotContainer
          repoUrl={repoUrl}
          repoBranch={repoBranch}
          accessValue={${accessName}}
          repoStatus={repoStatus}
          isRepoBusy={isRepoBusy}
          runtimeBusy={runtimeBusy}
          repoFiles={repoFiles}
          memoryHints={solutionPatternHints}
          onRepoUrlChange={setRepoUrl}
          onRepoBranchChange={setRepoBranch}
          onAccessValueChange={${accessSetter}}
          onLoadRepo={() => { void handleLoadRepoTree(); }}
          onSaveView={saveCurrentSession}
          onRestoreView={restoreSession}
          onClearView={clearSession}
        />
      ) : null}

`;
  source = source.slice(0, startIndex) + replacement + source.slice(nextIndex);
  changed = true;
}

if (changed) {
  writeFileSync(file, source, 'utf8');
  console.log(`${file}: RepoSnapshotContainer migration applied`);
} else {
  console.log(`${file}: already migrated`);
}
