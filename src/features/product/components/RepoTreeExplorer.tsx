import React, { useMemo } from 'react';
import type { DevChatRepoSnapshot } from '../runtime/devChatWorkerBridge';
import { buildRepoTree, summarizeRepoTreeSnapshot } from '../runtime/repoTreeExplorerRuntime';

export interface RepoTreeExplorerProps {
  readonly snapshot: DevChatRepoSnapshot | null;
  readonly onClose: () => void;
  readonly onFileClick: (path: string) => void;
}

export function RepoTreeExplorer({ snapshot, onClose, onFileClick }: RepoTreeExplorerProps) {
  const tree = useMemo(() => buildRepoTree(snapshot?.files ?? []), [snapshot]);
  return (
    <section role="dialog" aria-modal="true" data-testid="repo-tree-explorer">
      <header>
        <strong>Repo Inspector</strong>
        <p>{summarizeRepoTreeSnapshot(snapshot)}</p>
        <button type="button" onClick={onClose}>Schließen</button>
      </header>
      {!snapshot ? <p>Kein Repo-Snapshot geladen.</p> : null}
      {snapshot?.truncated ? <p>Snapshot truncated.</p> : null}
      {snapshot && tree.length === 0 ? <p>Keine Dateien im Snapshot.</p> : null}
      <ul>
        {tree.map((node) => (
          <li key={node.path}>
            {node.type === 'folder' ? <strong>{node.name}</strong> : <button type="button" onClick={() => onFileClick(node.path)}>{node.name}</button>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default RepoTreeExplorer;
