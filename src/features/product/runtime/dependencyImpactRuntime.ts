export interface DependencySource {
  readonly path: string;
  readonly content: string;
}

export interface DependencyImpact {
  readonly targetPath: string;
  readonly importerPaths: readonly string[];
  readonly importerCount: number;
  readonly scannedFileCount: number;
  readonly complete: boolean;
  readonly risk: 'low' | 'medium' | 'high';
}

export interface DependencyImpactReport {
  readonly byTarget: Readonly<Record<string, DependencyImpact>>;
  readonly scannedFileCount: number;
  readonly complete: boolean;
}

function stripExtension(path: string): string {
  return path.replace(/\.(?:[cm]?[jt]sx?|json)$/i, '');
}

function basename(path: string): string {
  const clean = stripExtension(path);
  return clean.slice(clean.lastIndexOf('/') + 1);
}

function importSpecifiers(content: string): readonly string[] {
  const specs: string[] = [];
  const patterns = [
    /\b(?:import|export)\s+(?:[^'";]+?\s+from\s+)?['"]([^'"]+)['"]/g,
    /\brequire\(\s*['"]([^'"]+)['"]\s*\)/g,
    /\bimport\(\s*['"]([^'"]+)['"]\s*\)/g,
  ];
  for (const pattern of patterns) {
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(content)) !== null) specs.push(match[1]);
  }
  return specs;
}

function specifierMatchesTarget(specifier: string, targetPath: string): boolean {
  const target = stripExtension(targetPath).replace(/^\.\//, '');
  const spec = stripExtension(specifier).replace(/^\.\//, '');
  return spec === target
    || spec.endsWith(`/${basename(target)}`)
    || target.endsWith(`/${spec}`)
    || basename(spec) === basename(target);
}

export function findImporters(targetPath: string, sources: readonly DependencySource[]): readonly string[] {
  return sources
    .filter((source) => source.path !== targetPath)
    .filter((source) => importSpecifiers(source.content).some((specifier) => specifierMatchesTarget(specifier, targetPath)))
    .map((source) => source.path)
    .sort();
}

export function buildImpactReport(
  targetPaths: readonly string[],
  sources: readonly DependencySource[],
  options: { readonly complete?: boolean } = {},
): DependencyImpactReport {
  const complete = options.complete === true;
  const byTarget = Object.fromEntries(targetPaths.map((targetPath) => {
    const importerPaths = findImporters(targetPath, sources);
    const importerCount = importerPaths.length;
    const risk: DependencyImpact['risk'] = importerCount > 10 ? 'high' : importerCount > 4 ? 'medium' : 'low';
    return [targetPath, {
      targetPath,
      importerPaths,
      importerCount,
      scannedFileCount: sources.length,
      complete,
      risk,
    } satisfies DependencyImpact];
  }));
  return { byTarget, scannedFileCount: sources.length, complete };
}
