import type { RepoFile } from '../../github/types';
import type { SovereignHealthReport } from './sovereignHealth';
import type { ImplementationFile, SovereignImplementationPackage } from './sovereignRuntime';

const FORBIDDEN_OUTPUT_PREFIXES = ['.git/', 'node_modules/', 'dist/', 'build/'];
const FORBIDDEN_OUTPUT_FILES = ['.env', '.env.local', '.env.production'];

export interface RepoSnapshotStatus {
  ready: boolean;
  fileCount: number;
  reason: string;
}

export interface SovereignHealthRuntimeGate {
  allowed: boolean;
  status: SovereignHealthReport['status'];
  reason: string;
  warnings: string[];
}

export function normalizeRepoPath(path: string): string {
  return path.trim().replace(/^\/+/, '');
}

export function getRepoSnapshotStatus(repoFiles: RepoFile[]): RepoSnapshotStatus {
  if (!repoFiles.length) {
    return {
      ready: false,
      fileCount: 0,
      reason: 'Load a real repository tree before generating Sovereign packages.',
    };
  }

  const blobCount = repoFiles.filter((file) => file.type === 'blob').length;
  if (blobCount === 0) {
    return {
      ready: false,
      fileCount: repoFiles.length,
      reason: 'Repository snapshot contains no files, only folders.',
    };
  }

  return {
    ready: true,
    fileCount: repoFiles.length,
    reason: `${repoFiles.length} repository entries loaded.`,
  };
}

export function assertLoadedRepoSnapshot(repoFiles: RepoFile[]): void {
  const status = getRepoSnapshotStatus(repoFiles);
  if (!status.ready) throw new Error(status.reason);
}

export function assertNoDuplicateGeneratedFiles(files: ImplementationFile[]): void {
  const seen = new Set<string>();
  for (const file of files) {
    const path = normalizeRepoPath(file.path);
    if (seen.has(path)) {
      throw new Error(`Duplicate generated file path: ${path}`);
    }
    seen.add(path);
  }
}

export function assertSafeGeneratedFiles(files: ImplementationFile[]): void {
  for (const file of files) {
    const path = normalizeRepoPath(file.path);
    const lower = path.toLowerCase();

    if (!path || path.includes('..') || path.startsWith('/')) {
      throw new Error(`Invalid generated file path: ${file.path || '<missing-path>'}`);
    }

    if (FORBIDDEN_OUTPUT_FILES.includes(lower) || FORBIDDEN_OUTPUT_PREFIXES.some((prefix) => lower.startsWith(prefix))) {
      throw new Error(`Forbidden generated file path: ${path}`);
    }

    if (!file.content.trim()) {
      throw new Error(`Generated file is empty: ${path}`);
    }
  }
}

export function assertDocsPackageShape(pkg: SovereignImplementationPackage): void {
  if (pkg.requestedWork !== 'readme-docs') return;

  const paths = new Set(pkg.files.map((file) => normalizeRepoPath(file.path).toLowerCase()));
  const required = ['readme.md', 'docs/update_history.md', 'docs/sovereign_runtime.md', 'docs/launch_readiness.md'];
  const missing = required.filter((path) => !paths.has(path));

  if (missing.length) {
    throw new Error(`Sovereign docs package missing required files: ${missing.join(', ')}`);
  }
}

export function getSovereignHealthRuntimeGate(report: SovereignHealthReport): SovereignHealthRuntimeGate {
  const warnings = report.recommendations.filter((item) => item.trim().length > 0);

  if (report.status === 'red' || report.status === 'idle') {
    return {
      allowed: false,
      status: report.status,
      reason: `Health ${report.status} prevents guarded output: ${report.summary}`,
      warnings,
    };
  }

  return {
    allowed: true,
    status: report.status,
    reason: report.status === 'warning'
      ? `Health warning allows guarded output with review: ${report.summary}`
      : `Health green allows guarded output: ${report.summary}`,
    warnings,
  };
}

export function assertSovereignHealthAllowsRuntimeOutput(report: SovereignHealthReport): void {
  const gate = getSovereignHealthRuntimeGate(report);
  if (!gate.allowed) throw new Error(gate.reason);
}

export function assertGeneratedPackageReady(pkg: SovereignImplementationPackage, repoFiles?: RepoFile[]): void {
  if (repoFiles) assertLoadedRepoSnapshot(repoFiles);
  assertNoDuplicateGeneratedFiles(pkg.files);
  assertSafeGeneratedFiles(pkg.files);
  assertDocsPackageShape(pkg);
}

export function buildRepoSnapshotSummary(repoFiles: RepoFile[]): string {
  const blobs = repoFiles.filter((file) => file.type === 'blob').length;
  const trees = repoFiles.filter((file) => file.type === 'tree').length;
  return `Snapshot: ${repoFiles.length} entries (${blobs} files, ${trees} folders).`;
}
