import type { RepoFile } from '../../github/types';
import { defaultSettings, starterCards } from '../constants';
import type { Card, ProjectSettings } from '../types';
import {
  assertGeneratedPackageReady,
  assertLoadedRepoSnapshot,
  buildRepoSnapshotSummary,
} from './sovereignFunctionalGuards';
import {
  buildSovereignImplementationPackage,
  runtimeAssertSovereignPackage,
  type SovereignImplementationPackage,
} from './sovereignRuntime';

export interface BuildSovereignPackageFromRepoFilesInput {
  mission: string;
  repoFiles: RepoFile[];
  selectedFilePath?: string;
  cards?: Card[];
  settings?: ProjectSettings;
  previousPreview?: string;
}

export function buildSovereignPackageFromRepoFiles(
  input: BuildSovereignPackageFromRepoFilesInput,
): SovereignImplementationPackage {
  assertLoadedRepoSnapshot(input.repoFiles);

  const pkg = buildSovereignImplementationPackage({
    blueprint: input.mission.trim() || 'README + Update History',
    cards: input.cards ?? starterCards(),
    settings: input.settings ?? defaultSettings,
    selectedFilePath: input.selectedFilePath ?? 'README.md',
    repoPaths: input.repoFiles.map((file) => file.path),
    previousPreview: input.previousPreview,
  });

  runtimeAssertSovereignPackage(pkg);
  assertGeneratedPackageReady(pkg, input.repoFiles);
  return pkg;
}

export function summarizeSovereignPackage(pkg: SovereignImplementationPackage, repoFiles?: RepoFile[]): string {
  return [
    repoFiles ? buildRepoSnapshotSummary(repoFiles) : undefined,
    `Architecture: ${pkg.architecture.summary}`,
    `Brain: ${pkg.brain.analysis.severity} / ${pkg.brain.plan.estimatedComplexity}`,
    `Files: ${pkg.files.map((file) => file.path).join(', ')}`,
  ].filter(Boolean).join('\n');
}
