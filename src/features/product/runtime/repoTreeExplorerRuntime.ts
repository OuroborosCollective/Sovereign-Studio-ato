import type { DevChatRepoSnapshot, DevChatRepoTreeFile } from './devChatWorkerBridge';

export interface RepoTreeNode {
  readonly name: string;
  readonly path: string;
  readonly type: 'file' | 'folder';
  readonly children: readonly RepoTreeNode[];
  readonly size?: number;
}

interface MutableRepoTreeNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children: MutableRepoTreeNode[];
  size?: number;
}

function sortNodes(nodes: MutableRepoTreeNode[]): RepoTreeNode[] {
  return nodes
    .sort((a, b) => {
      if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
      return a.name.localeCompare(b.name);
    })
    .map((node) => ({
      name: node.name,
      path: node.path,
      type: node.type,
      size: node.size,
      children: sortNodes(node.children),
    }));
}

export function buildRepoTree(files: readonly DevChatRepoTreeFile[]): readonly RepoTreeNode[] {
  const roots: MutableRepoTreeNode[] = [];
  const folders = new Map<string, MutableRepoTreeNode>();

  function ensureFolder(path: string): MutableRepoTreeNode {
    const existing = folders.get(path);
    if (existing) return existing;

    const parts = path.split('/').filter(Boolean);
    const name = parts[parts.length - 1] || path;
    const parentPath = parts.slice(0, -1).join('/');
    const folder: MutableRepoTreeNode = { name, path, type: 'folder', children: [] };
    folders.set(path, folder);

    if (parentPath) ensureFolder(parentPath).children.push(folder);
    else roots.push(folder);

    return folder;
  }

  for (const file of files) {
    const cleanPath = file.path.trim();
    if (!cleanPath) continue;
    const parts = cleanPath.split('/').filter(Boolean);
    if (!parts.length) continue;

    if (file.type === 'tree') {
      ensureFolder(cleanPath);
      continue;
    }

    const fileName = parts[parts.length - 1];
    const parentPath = parts.slice(0, -1).join('/');
    const node: MutableRepoTreeNode = {
      name: fileName,
      path: cleanPath,
      type: 'file',
      size: file.size,
      children: [],
    };

    if (parentPath) ensureFolder(parentPath).children.push(node);
    else roots.push(node);
  }

  return sortNodes(roots);
}

export function createRepoFilePrompt(path: string): string {
  return `Erkläre mir ${path} und nenne den nächsten sicheren Änderungsschritt.`;
}

export function summarizeRepoTreeSnapshot(snapshot: DevChatRepoSnapshot | null): string {
  if (!snapshot) return 'Repo-Snapshot fehlt.';
  const trunc = snapshot.truncated ? ' · truncated' : '';
  return `${snapshot.owner}/${snapshot.repo} · ${snapshot.branch} · ${snapshot.fileCount} Einträge${trunc}`;
}

export function hasRepoTreeEntries(snapshot: DevChatRepoSnapshot | null): boolean {
  return Boolean(snapshot && snapshot.files.length > 0);
}
