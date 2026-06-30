import React, { useMemo, useState } from 'react';
import type { DevChatRepoSnapshot } from '../runtime/devChatWorkerBridge';
import { buildRepoTree, summarizeRepoTreeSnapshot, type RepoTreeNode } from '../runtime/repoTreeExplorerRuntime';

export interface RepoTreeExplorerProps {
  readonly snapshot: DevChatRepoSnapshot | null;
  readonly onClose: () => void;
  readonly onFileClick: (path: string) => void;
}

function TreeNodeRow({ node, level, onFileClick }: { readonly node: RepoTreeNode; readonly level: number; readonly onFileClick: (path: string) => void }) {
  const [open, setOpen] = useState(level < 1);
  const folder = node.type === 'folder';
  return (
    <li>
      <button
        type="button"
        onClick={() => folder ? setOpen((value) => !value) : onFileClick(node.path)}
        aria-expanded={folder ? open : undefined}
        style={{ marginLeft: level * 12 }}
      >
        {folder ? (open ? '▾' : '▸') : '•'} {node.name}
      </button>
      {folder && open && node.children.length > 0 ? (
        <ul>
          {node.children.map((child) => <TreeNodeRow key={child.path} node={child} level={level + 1} onFileClick={onFileClick} />)}
        </ul>
      ) : null}
    </li>
  );
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
        {tree.map((node) => <TreeNodeRow key={node.path} node={node} level={0} onFileClick={onFileClick} />)}
      </ul>
    </section>
  );
}

export default RepoTreeExplorer;
