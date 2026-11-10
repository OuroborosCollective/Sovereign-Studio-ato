import React, { useEffect, useMemo, useState } from 'react';
import type { DevChatRepoSnapshot } from '../runtime/devChatWorkerBridge';
import { buildRepoTree, summarizeRepoTreeSnapshot, type RepoTreeNode } from '../runtime/repoTreeExplorerRuntime';

export type RepoTreeExplorerVariant = 'dialog' | 'split';

export interface RepoTreeExplorerProps {
  readonly snapshot: DevChatRepoSnapshot | null;
  readonly onClose?: () => void;
  readonly onFileClick: (path: string) => void;
  readonly variant?: RepoTreeExplorerVariant;
}

const TreeNodeRow = React.memo(function TreeNodeRow({
  node,
  level,
  onFileClick,
}: {
  readonly node: RepoTreeNode;
  readonly level: number;
  readonly onFileClick: (path: string) => void;
}) {
  const [open, setOpen] = useState(level < 1);
  const folder = node.type === 'folder';
  const ariaLabel = folder
    ? `${open ? 'Ordner schließen' : 'Ordner öffnen'}: ${node.name}`
    : `Datei öffnen: ${node.name}`;

  return (
    <li role="treeitem" aria-expanded={folder ? open : undefined}>
      <button
        type="button"
        onClick={() => folder ? setOpen((value) => !value) : onFileClick(node.path)}
        aria-expanded={folder ? open : undefined}
        aria-label={ariaLabel}
        title={ariaLabel}
        className="focus-visible:ring-2 focus-visible:ring-[#00d9b1] focus-visible:outline-none transition-opacity hover:opacity-85"
        style={{ marginLeft: level * 12 }}
      >
        <span aria-hidden="true">{folder ? (open ? '▾' : '▸') : '•'}</span>{' '}
        <span>{node.name}</span>
      </button>
      {folder && open && node.children.length > 0 ? (
        <ul role="group">
          {node.children.map((child) => <TreeNodeRow key={child.path} node={child} level={level + 1} onFileClick={onFileClick} />)}
        </ul>
      ) : null}
    </li>
  );
});

export const RepoTreeExplorer = React.memo(function RepoTreeExplorer({
  snapshot,
  onClose,
  onFileClick,
  variant = 'dialog',
}: RepoTreeExplorerProps) {
  const tree = useMemo(() => buildRepoTree(snapshot?.files ?? []), [snapshot]);
  const isDialog = variant === 'dialog';
  const label = isDialog ? 'Repo Inspector' : 'Repo Baum Split Inspector';

  useEffect(() => {
    if (!isDialog || !onClose) return undefined;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isDialog, onClose]);

  return (
    <section
      role={isDialog ? 'dialog' : 'navigation'}
      aria-modal={isDialog ? true : undefined}
      aria-label={label}
      data-testid={isDialog ? 'repo-tree-explorer' : 'repo-split-inspector'}
    >
      <header>
        <strong>{isDialog ? 'Repo Inspector' : 'Repo-Baum'}</strong>
        <p>{summarizeRepoTreeSnapshot(snapshot)}</p>
        {isDialog && onClose ? (
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            title="Schließen"
            className="focus-visible:ring-2 focus-visible:ring-[#00d9b1] focus-visible:outline-none transition-opacity hover:opacity-85"
          >
            Schließen
          </button>
        ) : null}
      </header>
      {!snapshot ? <p>Kein Repo-Snapshot geladen.</p> : null}
      {snapshot?.truncated ? <p>Snapshot truncated.</p> : null}
      {snapshot && tree.length === 0 ? <p>Keine Dateien im Snapshot.</p> : null}
      <ul role="tree" aria-label="Dateibaum">
        {tree.map((node) => <TreeNodeRow key={node.path} node={node} level={0} onFileClick={onFileClick} />)}
      </ul>
    </section>
  );
});

export default RepoTreeExplorer;