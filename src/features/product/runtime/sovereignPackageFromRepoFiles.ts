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

const PLACEHOLDER_MISSIONS = [
  'README + Update History',
  'Beschreibe deine Idee oder deinen Auftrag.',
  'Starte mit diesem Auftrag.',
  'awaiting-intent',
  'repo-setup',
];

export function hasConcreteSovereignMission(mission: string): boolean {
  const normalized = mission.trim();
  if (normalized.length < 12) return false;
  const lower = normalized.toLowerCase();
  if (PLACEHOLDER_MISSIONS.some((placeholder) => lower.includes(placeholder.toLowerCase()))) return false;
  return /\b(add|build|fix|implement|create|update|wire|connect|harden|test|remove|refactor|repair|behebe|baue|erstelle|verbinde|haerte|teste|repariere|aktualisiere)\b/i.test(normalized);
}

export function assertConcreteSovereignMission(mission: string): void {
  if (!hasConcreteSovereignMission(mission)) {
    throw new Error('Concrete user mission is required before package build. Enter a real implementation request; placeholder planning text must not start Draft PR package build.');
  }
}

export function buildSovereignPackageFromRepoFiles(
  input: BuildSovereignPackageFromRepoFilesInput,
): SovereignImplementationPackage {
  assertLoadedRepoSnapshot(input.repoFiles);
  assertConcreteSovereignMission(input.mission);

  const pkg = buildSovereignImplementationPackage({
    blueprint: input.mission.trim(),
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
