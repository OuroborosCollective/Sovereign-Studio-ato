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

/**
 * Recursively sorts tree nodes first by type (folders first) and then lexicographically.
 * Optimized by replacing slow localeCompare with native lexicographical string comparison operators.
 * This completely avoids V8's slow internationalization/collation overhead.
 */
function sortNodes(nodes: MutableRepoTreeNode[]): RepoTreeNode[] {
  return nodes
    .sort((a, b) => {
      if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
      if (a.name < b.name) return -1;
      if (a.name > b.name) return 1;
      return 0;
    })
    .map((node) => ({
      name: node.name,
      path: node.path,
      type: node.type,
      size: node.size,
      children: sortNodes(node.children),
    }));
}

/**
 * Builds a folder/file hierarchy tree from a flat list of files.
 * Highly optimized by using native string methods (lastIndexOf, substring) for path decomposition
 * and local map/regex-less fast normalization instead of repeated split(), filter(), slice(), and join().
 */
export function buildRepoTree(files: readonly DevChatRepoTreeFile[]): readonly RepoTreeNode[] {
  const roots: MutableRepoTreeNode[] = [];
  const folders = new Map<string, MutableRepoTreeNode>();

  function ensureFolder(path: string): MutableRepoTreeNode {
    const existing = folders.get(path);
    if (existing) return existing;

    const lastSlash = path.lastIndexOf('/');
    const name = lastSlash === -1 ? path : path.substring(lastSlash + 1);
    const parentPath = lastSlash === -1 ? '' : path.substring(0, lastSlash);

    const folder: MutableRepoTreeNode = { name, path, type: 'folder', children: [] };
    folders.set(path, folder);

    if (parentPath) ensureFolder(parentPath).children.push(folder);
    else roots.push(folder);

    return folder;
  }

  for (const file of files) {
    let cleanPath = file.path.trim();
    if (!cleanPath) continue;

    // Fast path normalization: strip leading and trailing slashes
    while (cleanPath.startsWith('/')) {
      cleanPath = cleanPath.slice(1);
    }
    while (cleanPath.endsWith('/')) {
      cleanPath = cleanPath.slice(0, -1);
    }
    // Clean up internal consecutive slashes (e.g. "src//features") if present
    if (cleanPath.includes('//')) {
      cleanPath = cleanPath.replace(/\/+/g, '/');
    }
    if (!cleanPath) continue;

    if (file.type === 'tree') {
      ensureFolder(cleanPath);
      continue;
    }

    const lastSlash = cleanPath.lastIndexOf('/');
    const fileName = lastSlash === -1 ? cleanPath : cleanPath.substring(lastSlash + 1);
    const parentPath = lastSlash === -1 ? '' : cleanPath.substring(0, lastSlash);

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
