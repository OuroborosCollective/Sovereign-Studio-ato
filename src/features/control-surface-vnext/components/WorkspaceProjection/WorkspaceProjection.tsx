import React, { useState } from 'react';
import { Check, Copy, Diff, FileCode2, FolderGit2, GitCommit } from 'lucide-react';
import type { WorkspaceState } from '../../types/domain';

interface Props { workspace: WorkspaceState | undefined; }

export function WorkspaceProjection({ workspace }: Props) {
  const [copiedRev, setCopiedRev] = useState(false);
  const copyRevision = () => {
    if (!workspace?.currentRevision) return;
    void navigator.clipboard.writeText(workspace.currentRevision);
    setCopiedRev(true);
    window.setTimeout(() => setCopiedRev(false), 1800);
  };
  const modifiedFiles = workspace?.modifiedFiles || [];
  const diffStats = workspace?.diffStats;
  return (
    <div className="flex flex-col h-full bg-[var(--carbon-deep)] p-3 border-b border-white/5 overflow-hidden" data-testid="vnext-workspace-projection">
      <div className="flex items-center justify-between border-b border-white/5 pb-2 mb-2">
        <div className="flex items-center gap-1.5 font-mono text-[11px] font-bold text-white uppercase tracking-wider"><FolderGit2 size={13} className="text-[var(--red-laser)]" /><span>WORKSPACE PROJECTION</span></div>
        {workspace?.currentRevision ? <button onClick={copyRevision} className="flex items-center gap-1 font-mono text-[9px] px-1.5 py-0.5 rounded bg-[var(--carbon-surface)] border border-white/5 text-[var(--text-muted)] hover:text-white" title="Copy evidence-bound repository revision"><GitCommit size={10} className="text-[var(--red-laser)]" /><span className="font-bold">{workspace.currentRevision.slice(0, 8)}</span>{copiedRev ? <Check size={10} className="text-[var(--emerald-seal)]" /> : <Copy size={10} />}</button> : <span className="text-[8.5px] text-[var(--red-alert)]">REVISION UNVERIFIED</span>}
      </div>
      {diffStats && <div className="flex items-center gap-2 font-mono text-[9.5px] mb-2 p-1.5 rounded bg-[var(--carbon-surface)] border border-white/5"><Diff size={12} className="text-[var(--text-dim)]" /><span className="text-[var(--text-dim)]">FILES</span><span className="text-white font-bold">{diffStats.filesChanged || modifiedFiles.length}</span>{(diffStats.additions > 0 || diffStats.deletions > 0) && <><span className="text-[var(--emerald-seal)] font-bold">+{diffStats.additions}</span><span className="text-[var(--red-laser)] font-bold">-{diffStats.deletions}</span></>}</div>}
      <div className="flex-1 overflow-y-auto font-mono text-[10.5px] space-y-1.5 pr-1">
        {modifiedFiles.map((file) => <div key={file} className="flex items-center justify-between p-1.5 rounded bg-[var(--carbon-surface)] border border-white/5 hover:border-[rgba(255,30,56,0.2)] text-[var(--text-main)]"><div className="flex items-center gap-1.5 truncate"><FileCode2 size={12} className="text-[var(--red-laser)] shrink-0" /><span className="truncate">{file}</span></div><span className="text-[8.5px] px-1 py-0.2 rounded bg-[rgba(255,30,56,0.1)] text-[var(--red-laser)] font-bold">CHANGED</span></div>)}
        {modifiedFiles.length === 0 && <div className="flex flex-col items-center justify-center h-28 text-center text-[var(--text-dim)] font-mono text-[10px] italic"><FolderGit2 size={18} className="mb-1.5 opacity-40 text-[var(--red-pulse)]" /><span>No changed-file readback.</span><span className="text-[9px] opacity-60">This does not claim the repository is globally clean.</span></div>}
      </div>
    </div>
  );
}
