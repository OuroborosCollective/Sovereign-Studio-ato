import type { RepoFile } from '../../github/types';
import { defaultSettings, starterCards } from '../constants';
import type { Card, ProjectSettings } from '../types';
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
  const pkg = buildSovereignImplementationPackage({
    blueprint: input.mission.trim() || 'README + Update History',
    cards: input.cards ?? starterCards(),
    settings: input.settings ?? defaultSettings,
    selectedFilePath: input.selectedFilePath ?? 'README.md',
    repoPaths: input.repoFiles.map((file) => file.path),
    previousPreview: input.previousPreview,
  });

  runtimeAssertSovereignPackage(pkg);
  return pkg;
}

export function summarizeSovereignPackage(pkg: SovereignImplementationPackage): string {
  return [
    `Architecture: ${pkg.architecture.summary}`,
    `Brain: ${pkg.brain.analysis.severity} / ${pkg.brain.plan.estimatedComplexity}`,
    `Files: ${pkg.files.map((file) => file.path).join(', ')}`,
  ].join('\n');
}
