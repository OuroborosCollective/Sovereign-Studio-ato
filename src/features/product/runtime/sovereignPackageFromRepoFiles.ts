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

const EXACT_PLACEHOLDER_MISSIONS = new Set([
  'readme + update history',
  'beschreibe deine idee oder deinen auftrag.',
  'starte mit diesem auftrag.',
  'awaiting-intent',
  'repo-setup',
  'workflow fehleranalyse + runtime check + test plan',
  'fehler',
  'ideen',
  'plan',
  'test plan',
  'mach weiter',
  'mach was',
  'mach irgendwas',
  'weiter',
]);

const PLACEHOLDER_SUBSTRINGS = [
  'placeholder',
  'awaiting intent',
  'concrete user mission is required',
];

const CONCRETE_MISSION_VERBS = [
  'add',
  'build',
  'connect',
  'create',
  'fix',
  'harden',
  'implement',
  'refactor',
  'remove',
  'repair',
  'test',
  'update',
  'wire',
  'aktualisiere',
  'baue',
  'behebe',
  'ergaenze',
  'ergaenzt',
  'erstelle',
  'erweitere',
  'erweiterung',
  'haerte',
  'implementiere',
  'implementieren',
  'plane',
  'pruefe',
  'pruefen',
  'repariere',
  'ersetze',
  'stabilisiere',
  'teste',
  'verbinde',
];

const AUTONOMOUS_MISSION_TARGETS = [
  'src/App.tsx',
  'src/global-runtime-monitor.tsx',
  'src/features/product/runtime/sovereignReleaseGuide.ts',
  'src/features/product/runtime/sovereignPackageFromRepoFiles.ts',
  'src/features/product/components/RepoInsightPanelBridge.tsx',
  'src/features/product/runtime/sovereignReleaseGuide.test.ts',
  'src/features/product/runtime/sovereignPackageFromRepoFiles.test.ts',
];

function normalizeMissionText(value: string): string {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

function isPlaceholderSovereignMission(mission: string): boolean {
  const normalized = normalizeMissionText(mission);
  if (normalized.length < 12) return true;
  if (EXACT_PLACEHOLDER_MISSIONS.has(normalized)) return true;
  return PLACEHOLDER_SUBSTRINGS.some((placeholder) => normalized.includes(placeholder));
}

function existingTargets(repoFiles: RepoFile[]): string[] {
  const paths = new Set(repoFiles.map((file) => file.path));
  const preferred = AUTONOMOUS_MISSION_TARGETS.filter((path) => paths.has(path));
  if (preferred.length > 0) return preferred;

  const fallback = repoFiles
    .map((file) => file.path)
    .filter((path) => path.startsWith('src/') || path.startsWith('tests/') || path === 'README.md')
    .slice(0, 5);

  return fallback.length > 0 ? fallback : ['README.md', 'docs/SOVEREIGN_RUNTIME.md'];
}

function hasConcreteMissionVerb(mission: string): boolean {
  const normalized = normalizeMissionText(mission);
  return CONCRETE_MISSION_VERBS.some((verb) => new RegExp(`(^|[^a-z0-9_-])${verb}($|[^a-z0-9_-])`, 'i').test(normalized));
}

export function hasConcreteSovereignMission(mission: string): boolean {
  const normalized = mission.trim();
  if (isPlaceholderSovereignMission(normalized)) return false;
  return hasConcreteMissionVerb(normalized);
}

export function resolveAutonomousSovereignMission(mission: string, repoFiles: RepoFile[]): string {
  const trimmed = mission.trim();
  if (hasConcreteSovereignMission(trimmed)) return trimmed;

  const targets = existingTargets(repoFiles);
  return [
    'Implementiere eine autonome Runtime-Stabilisierung fuer die geladene Sovereign-Studio-App.',
    `Zielpfade: ${targets.join(', ')}`,
    'Konkrete Arbeit:',
    '1. Ersetze Default-/Prozent-Fortschritt durch einen systembasierten Schrittplan, dessen Gesamtzahl aus den wirklich geplanten Arbeitsschritten entsteht.',
    '2. Stelle sicher, dass die UI nur die echte Runtime-Wahrheit spiegelt und keine eigene Fortschrittsanalyse ausfuehrt.',
    '3. Nutze Repo-Insight-Ergebnisse, um aus Default-Auftraegen automatisch eine sichere ausfuehrbare Mission abzuleiten.',
    '4. Halte den Guard gegen Plan-only Draft PRs, leere Patches und verbotene Pfade aktiv.',
    '5. Ergaenze oder aktualisiere passende Vitest-Abdeckung fuer autonome Mission und Schrittplan-Anzeige.',
  ].join('\n');
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

  const effectiveMission = resolveAutonomousSovereignMission(input.mission, input.repoFiles);
  assertConcreteSovereignMission(effectiveMission);

  const pkg = buildSovereignImplementationPackage({
    blueprint: effectiveMission,
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
