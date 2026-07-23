export interface RepositoryTextFile {
  path: string;
  content: string;
}

export interface DependencyImpactEntry {
  path: string;
  importers: string[];
  importerCount: number;
  risk: 'low' | 'medium' | 'high';
}

function normalizePath(value: string): string {
  return value.replace(/\\/g, '/').replace(/^\.\//, '').replace(/\.(?:[cm]?[jt]sx?)$/, '');
}

function importSpecifiers(content: string): string[] {
  const matches: string[] = [];
  const patterns = [
    /\bimport\s+(?:type\s+)?(?:[^'";]+?\s+from\s+)?['"]([^'"]+)['"]/g,
    /\brequire\(\s*['"]([^'"]+)['"]\s*\)/g,
    /\bimport\(\s*['"]([^'"]+)['"]\s*\)/g,
  ];
  for (const pattern of patterns) {
    for (const match of content.matchAll(pattern)) matches.push(match[1]);
  }
  return matches;
}

function dirname(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  const index = normalized.lastIndexOf('/');
  return index < 0 ? '' : normalized.slice(0, index);
}

function resolveRelative(importerPath: string, specifier: string): string {
  if (!specifier.startsWith('.')) return normalizePath(specifier);
  const stack = `${dirname(importerPath)}/${specifier}`.split('/');
  const out: string[] = [];
  for (const segment of stack) {
    if (!segment || segment === '.') continue;
    if (segment === '..') out.pop();
    else out.push(segment);
  }
  return normalizePath(out.join('/'));
}

export function findImporters(targetPath: string, files: readonly RepositoryTextFile[]): string[] {
  const target = normalizePath(targetPath);
  return files
    .filter((file) => normalizePath(file.path) !== target)
    .filter((file) => importSpecifiers(file.content).some((specifier) => {
      const resolved = resolveRelative(file.path, specifier);
      return resolved === target || resolved === `${target}/index` || target.endsWith(`/${resolved}`);
    }))
    .map((file) => file.path)
    .sort((a, b) => a.localeCompare(b));
}

export function buildImpactReport(
  changedPaths: readonly string[],
  files: readonly RepositoryTextFile[],
): DependencyImpactEntry[] {
  return [...new Set(changedPaths)].sort().map((path) => {
    const importers = findImporters(path, files);
    const importerCount = importers.length;
    return {
      path,
      importers,
      importerCount,
      risk: importerCount > 10 ? 'high' : importerCount > 4 ? 'medium' : 'low',
    };
  });
}
