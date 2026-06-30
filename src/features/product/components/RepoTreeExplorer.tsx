/**
 * RepoTreeExplorer - Collapsible file tree from DevChatRepoSnapshot
 * 
 * Displays already loaded repo snapshot as calm inspector surface.
 * Tapping a file fills composer with conscious prompt.
 * Works with 500-item snapshot without lag on mobile.
 */

import React, { useState, useCallback, useMemo } from 'react';
import type { DevChatRepoSnapshot } from '../runtime/devChatWorkerBridge';

export interface RepoTreeExplorerProps {
  repoSnapshot: DevChatRepoSnapshot;
  onFileSelect: (filePath: string) => void;
  onClose: () => void;
}

interface FileNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children?: FileNode[];
}

const C = {
  bg:        '#0e1116',
  surface:   '#161c24',
  border:    '#232d3a',
  accent:    '#00d9b1',
  text:      '#cdd9e5',
  textSub:   '#768390',
  textMuted: '#3d4f61',
};

// Build tree structure from flat file paths
function buildFileTree(files: string[]): FileNode[] {
  const root: FileNode[] = [];
  const dirs = new Map<string, FileNode>();

  // Sort files for consistent display
  const sortedFiles = [...files].sort();

  for (const filePath of sortedFiles) {
    const parts = filePath.split('/');
    let currentLevel = root;
    let currentPath = '';

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      currentPath = currentPath ? `${currentPath}/${part}` : part;

      if (isLast && !part.includes('.')) {
        // Directory without extension
        if (!dirs.has(currentPath)) {
          const node: FileNode = { name: part, path: currentPath, isDirectory: true, children: [] };
          dirs.set(currentPath, node);
          currentLevel.push(node);
        }
        currentLevel = dirs.get(currentPath)!.children!;
      } else if (isLast) {
        // File
        currentLevel.push({ name: part, path: currentPath, isDirectory: false });
      } else {
        // Directory
        if (!dirs.has(currentPath)) {
          const node: FileNode = { name: part, path: currentPath, isDirectory: true, children: [] };
          dirs.set(currentPath, node);
          currentLevel.push(node);
        }
        currentLevel = dirs.get(currentPath)!.children!;
      }
    }
  }

  return root;
}

// Single tree node component
function TreeNode({
  node,
  depth,
  onSelect,
}: {
  node: FileNode;
  depth: number;
  onSelect: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.isDirectory && node.children && node.children.length > 0;

  const handleClick = useCallback(() => {
    if (node.isDirectory) {
      setExpanded(v => !v);
    } else {
      onSelect(node.path);
    }
  }, [node.isDirectory, node.path, onSelect]);

  const getFileIcon = (name: string, isDir: boolean) => {
    if (isDir) return '📁';
    const ext = name.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'ts': case 'tsx': return '🔷';
      case 'js': case 'jsx': case 'mjs': return '🟨';
      case 'json': return '📋';
      case 'md': return '📝';
      case 'css': case 'scss': case 'less': return '🎨';
      case 'html': return '🌐';
      case 'png': case 'jpg': case 'gif': case 'svg': return '🖼️';
      case 'py': return '🐍';
      case 'go': return '🔵';
      case 'rs': return '🦀';
      case 'java': case 'kt': return '☕';
      default: return '📄';
    }
  };

  return (
    <div>
      <div
        onClick={handleClick}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 8px',
          paddingLeft: depth * 16 + 8,
          cursor: 'pointer',
          borderRadius: 4,
          transition: 'background 0.1s',
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = C.border}
        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        role={node.isDirectory ? 'button' : 'option'}
        aria-expanded={node.isDirectory ? expanded : undefined}
        aria-selected={!node.isDirectory}
      >
        {hasChildren && (
          <span style={{ 
            fontSize: 10, 
            color: C.textSub, 
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s',
            width: 12,
          }}>
            ▶
          </span>
        )}
        {!hasChildren && node.isDirectory && <span style={{ width: 12 }} />}
        <span style={{ fontSize: 13 }}>
          {getFileIcon(node.name, node.isDirectory)}
        </span>
        <span style={{ 
          fontSize: 13, 
          color: C.text,
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {node.name}
        </span>
        {node.isDirectory && (
          <span style={{ fontSize: 11, color: C.textMuted }}>
            {node.children?.length}
          </span>
        )}
      </div>
      
      {expanded && hasChildren && (
        <div role="group">
          {node.children!.map((child, idx) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * RepoTreeExplorer - main component
 */
export const RepoTreeExplorer: React.FC<RepoTreeExplorerProps> = ({
  repoSnapshot,
  onFileSelect,
  onClose,
}) => {
  // Build tree from snapshot files
  const fileTree = useMemo(() => {
    const files: string[] = (repoSnapshot.files || []).map(f => 
      typeof f === 'string' ? f : f.path
    );
    return buildFileTree(files);
  }, [repoSnapshot.files]);

  const handleFileSelect = useCallback((path: string) => {
    // Fill composer with conscious prompt
    const prompt = `Erkläre mir ${path}`;
    onFileSelect(prompt);
  }, [onFileSelect]);

  return (
    <div
      role="dialog"
      aria-label="Repository Dateien"
      data-testid="repo-tree-explorer"
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        maxHeight: '70vh',
        background: C.surface,
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        border: `1px solid ${C.border}`,
        display: 'flex',
        flexDirection: 'column',
        zIndex: 100,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '16px',
          borderBottom: `1px solid ${C.border}`,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <div style={{ fontWeight: 600, color: C.text, fontSize: 15 }}>
            {repoSnapshot.name}
          </div>
          <div style={{ fontSize: 12, color: C.textSub, marginTop: 2 }}>
            {repoSnapshot.files?.length || 0} Dateien
            {repoSnapshot.truncated && ' ⚠️ (gekürzt)'}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Schließen"
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: C.border,
            border: 'none',
            color: C.textSub,
            cursor: 'pointer',
            fontSize: 16,
          }}
        >
          ✕
        </button>
      </div>

      {/* File tree */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '8px 0',
        }}
        role="listbox"
        aria-label="Dateien"
      >
        {fileTree.length === 0 ? (
          <div
            style={{
              padding: 24,
              textAlign: 'center',
              color: C.textSub,
              fontSize: 13,
            }}
          >
            Keine Dateien vorhanden
          </div>
        ) : (
          fileTree.map((node) => (
            <TreeNode
              key={node.path}
              node={node}
              depth={0}
              onSelect={handleFileSelect}
            />
          ))
        )}
      </div>

      {/* Footer hint */}
      <div
        style={{
          padding: '12px 16px',
          borderTop: `1px solid ${C.border}`,
          fontSize: 11,
          color: C.textMuted,
          textAlign: 'center',
        }}
      >
        Tippe auf eine Datei, um sie im Composer zu erklären
      </div>
    </div>
  );
};

export default RepoTreeExplorer;
