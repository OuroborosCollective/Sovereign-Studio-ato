/**
 * VpsFileTree — Lazy-Loading Dateibaum für den VPS Connector.
 *
 * Lädt Verzeichnisinhalte on-demand via getTree().
 * Klick auf Datei → onSelectFile() Callback.
 *
 * Issue #454
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Folder, FolderOpen, File, ChevronRight, ChevronDown, Loader2 } from 'lucide-react';
import type { DirEntry } from './useVpsConnection';

const C = {
  surface: '#161c24',
  border:  '#232d3a',
  accent:  '#00d9b1',
  text:    '#cdd9e5',
  textSub: '#768390',
} as const;

interface TreeNode {
  path: string;
  entry: DirEntry;
  children?: TreeNode[];
  loading?: boolean;
  expanded?: boolean;
}

interface Props {
  getTree: (path: string) => Promise<DirEntry[]>;
  onSelectFile: (path: string) => void;
}

export function VpsFileTree({ getTree, onSelectFile }: Props) {
  const [nodes, setNodes] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getTree('/').then((entries) => {
      setNodes(entries.map((e) => ({ path: `/${e.name}`, entry: e })));
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [getTree]);

  const toggleDir = useCallback(async (node: TreeNode) => {
    if (node.entry.type !== 'directory') return;

    setNodes((prev) => updateNode(prev, node.path, (n) => ({ ...n, loading: true })));

    if (!node.expanded) {
      const entries = await getTree(node.path);
      setNodes((prev) => updateNode(prev, node.path, (n) => ({
        ...n,
        expanded: true,
        loading: false,
        children: entries.map((e) => ({
          path: `${node.path}/${e.name}`,
          entry: e,
        })),
      })));
    } else {
      setNodes((prev) => updateNode(prev, node.path, (n) => ({
        ...n,
        expanded: false,
        loading: false,
      })));
    }
  }, [getTree]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 8 }}>
        <Loader2 size={14} color={C.textSub} className="animate-spin" />
        <span style={{ fontSize: 11, color: C.textSub }}>Lade Verzeichnis…</span>
      </div>
    );
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '8px 0' }}>
      {nodes.map((node) => (
        <TreeNodeRow
          key={node.path}
          node={node}
          depth={0}
          onToggle={toggleDir}
          onSelectFile={onSelectFile}
        />
      ))}
    </div>
  );
}

function TreeNodeRow({
  node, depth, onToggle, onSelectFile,
}: {
  node: TreeNode;
  depth: number;
  onToggle: (n: TreeNode) => void;
  onSelectFile: (path: string) => void;
}) {
  const isDir = node.entry.type === 'directory';

  return (
    <>
      <button
        type="button"
        onClick={() => isDir ? onToggle(node) : onSelectFile(node.path)}
        style={{
          display: 'flex', alignItems: 'center', gap: 5,
          width: '100%', padding: `4px 10px 4px ${10 + depth * 14}px`,
          background: 'transparent', border: 'none', cursor: 'pointer',
          textAlign: 'left', transition: 'background 0.1s',
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
      >
        {/* Expand chevron */}
        <span style={{ width: 12, flexShrink: 0, color: C.textSub }}>
          {isDir && (node.expanded
            ? <ChevronDown size={11} />
            : <ChevronRight size={11} />
          )}
        </span>
        {/* Icon */}
        <span style={{ color: isDir ? '#fbbf24' : C.textSub, flexShrink: 0 }}>
          {node.loading
            ? <Loader2 size={13} className="animate-spin" />
            : isDir
              ? (node.expanded ? <FolderOpen size={13} /> : <Folder size={13} />)
              : <File size={13} />
          }
        </span>
        {/* Name */}
        <span style={{ fontSize: 11, color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {node.entry.name}
        </span>
      </button>
      {/* Children */}
      {node.expanded && node.children?.map((child) => (
        <TreeNodeRow
          key={child.path}
          node={child}
          depth={depth + 1}
          onToggle={onToggle}
          onSelectFile={onSelectFile}
        />
      ))}
    </>
  );
}

// ── Hilfsfunktion: Node im Baum updaten ──────────────────────────────────────

function updateNode(nodes: TreeNode[], path: string, updater: (n: TreeNode) => TreeNode): TreeNode[] {
  return nodes.map((n) => {
    if (n.path === path) return updater(n);
    if (n.children) return { ...n, children: updateNode(n.children, path, updater) };
    return n;
  });
}
