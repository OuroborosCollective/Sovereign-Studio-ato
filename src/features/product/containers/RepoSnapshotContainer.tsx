import React from 'react';
import { RepoFileList } from '../../github/components/RepoFileList';
import type { RepoFile } from '../../github/types';
import { buildRepoSnapshotSummary, getRepoSnapshotStatus } from '../runtime/sovereignFunctionalGuards';

export interface RepoSnapshotContainerProps {
  repoUrl: string;
  repoBranch: string;
  accessValue: string;
  repoStatus: string;
  isRepoBusy: boolean;
  runtimeBusy: boolean;
  repoFiles: RepoFile[];
  memoryHints: string;
  onRepoUrlChange: (value: string) => void;
  onRepoBranchChange: (value: string) => void;
  onAccessValueChange: (value: string) => void;
  onLoadRepo: () => void;
  onSaveView: () => void;
  onRestoreView: () => void;
  onClearView: () => void;
}

export function RepoSnapshotContainer({
  repoUrl,
  repoBranch,
  accessValue,
  repoStatus,
  isRepoBusy,
  runtimeBusy,
  repoFiles,
  memoryHints,
  onRepoUrlChange,
  onRepoBranchChange,
  onAccessValueChange,
  onLoadRepo,
  onSaveView,
  onRestoreView,
  onClearView,
}: RepoSnapshotContainerProps) {
  const status = getRepoSnapshotStatus(repoFiles);
  const busy = isRepoBusy || runtimeBusy;
  const canLoad = !busy && repoUrl.trim().length > 0;
  const canSave = !busy && status.ready;
  const summary = repoFiles.length ? buildRepoSnapshotSummary(repoFiles) : repoStatus;

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200" data-testid="repo-snapshot-container">
      <h2 className="font-bold">Repository Snapshot</h2>
      <div className="mt-3 grid gap-2 md:grid-cols-3">
        <input value={repoUrl} onChange={(event) => onRepoUrlChange(event.target.value)} placeholder="Repository URL" aria-label="Repository URL" />
        <input value={repoBranch} onChange={(event) => onRepoBranchChange(event.target.value)} placeholder="Branch leer = Default" aria-label="Repository branch" />
        <input value={accessValue} onChange={(event) => onAccessValueChange(event.target.value)} placeholder="Private access value" aria-label="Private access value" type="password" />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button onClick={onLoadRepo} disabled={!canLoad} type="button">Load Repo</button>
        <button onClick={onSaveView} disabled={!canSave} type="button">Save Session</button>
        <button onClick={onRestoreView} disabled={busy} type="button">Restore Session</button>
        <button onClick={onClearView} disabled={busy} type="button">Clear View</button>
      </div>

      <p className="mt-3 text-xs text-slate-400">{summary}</p>
      <p className="mt-1 text-xs text-slate-400">{status.reason}</p>
      {memoryHints ? <pre className="mt-2 whitespace-pre-wrap rounded bg-slate-900/70 p-3 text-xs text-emerald-200">{memoryHints}</pre> : null}
      <RepoFileList files={repoFiles} />
    </section>
  );
}
