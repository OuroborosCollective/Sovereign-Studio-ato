import type { RepoFile } from '../../github/types';
import { defaultSettings, starterCards } from '../constants';
import type { Card, ProjectSettings } from '../types';
import {
  assertGeneratedPackageReady,
  assertLoadedRepoSnapshot,
  buildRepoSnapshotSummary,
} from './sovereignFunctionalGuards';
import {
  analyzeRepoArchitecture,
  buildSovereignImplementationPackage,
  classifyRequestedWork,
  runtimeAssertSovereignPackage,
  SOVEREIGN_LLM_ROUTES,
  type SovereignImplementationPackage,
} from './sovereignRuntime';
import { assertSovereignBrainResult, toImplementationFiles } from '../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llm/llmRuntimeChecks';
import { runSovereignLlmRuntime } from './sovereignLlmRuntime';

export interface BuildSovereignPackageFromRepoFilesInput {
  mission: string;
  repoFiles: RepoFile[];
  selectedFilePath?: string;
  cards?: Card[];
  settings?: ProjectSettings;
  previousPreview?: string;
  memoryContext?: string[];
  runtimeEvents?: string[];
  allowUserKeyRoutes?: boolean;
  userKeys?: {
    gemini?: string;
    groq?: string;
    huggingface?: string;
    together?: string;
    openrouter?: string;
    pollinations?: string;
  };
}

const USER_API_KEYS_STORAGE_KEY = 'sovereign-user-api-keys';

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

const HARD_PLACEHOLDER_SUBSTRINGS = [
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

function isSoftPlaceholderSovereignMission(mission: string): boolean {
  return EXACT_PLACEHOLDER_MISSIONS.has(normalizeMissionText(mission));
}

function isHardPlaceholderSovereignMission(mission: string): boolean {
  const normalized = normalizeMissionText(mission);
  if (isSoftPlaceholderSovereignMission(normalized)) return false;
  if (normalized.length < 12) return true;
  return HARD_PLACEHOLDER_SUBSTRINGS.some((placeholder) => normalized.includes(placeholder));
}

function isPlaceholderSovereignMission(mission: string): boolean {
  return isSoftPlaceholderSovereignMission(mission) || isHardPlaceholderSovereignMission(mission);
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

function readStoredUserKeys(): BuildSovereignPackageFromRepoFilesInput['userKeys'] | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    const stored = window.localStorage.getItem(USER_API_KEYS_STORAGE_KEY);
    if (!stored) return undefined;
    const parsed = JSON.parse(stored) as BuildSovereignPackageFromRepoFilesInput['userKeys'];
    return parsed && typeof parsed === 'object' ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function runtimeUserKeys(input: BuildSovereignPackageFromRepoFilesInput): BuildSovereignPackageFromRepoFilesInput['userKeys'] | undefined {
  if (!input.allowUserKeyRoutes) return undefined;
  return input.userKeys ?? readStoredUserKeys();
}

export function hasConcreteSovereignMission(mission: string): boolean {
  const normalized = mission.trim();
  if (isPlaceholderSovereignMission(normalized)) return false;
  return hasConcreteMissionVerb(normalized);
}

function assertNoHardPlaceholderMission(mission: string): void {
  if (isHardPlaceholderSovereignMission(mission)) {
    throw new Error('Concrete user mission is required before package build. Hard placeholder text must not start package build.');
  }
}

export function resolveAutonomousSovereignMission(mission: string, repoFiles: RepoFile[]): string {
  const trimmed = mission.trim();
  if (hasConcreteSovereignMission(trimmed)) return trimmed;
  assertNoHardPlaceholderMission(trimmed);

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
    '6. Pruefe und verbessere Runtime-Komponenten, Tests und Guards passend zum geladenen Repository.',
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
  assertNoHardPlaceholderMission(input.mission);

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

export async function buildSovereignPackageFromRepoFilesWithLlm(
  input: BuildSovereignPackageFromRepoFilesInput,
): Promise<SovereignImplementationPackage> {
  assertLoadedRepoSnapshot(input.repoFiles);
  assertNoHardPlaceholderMission(input.mission);

  const effectiveMission = resolveAutonomousSovereignMission(input.mission, input.repoFiles);
  assertConcreteSovereignMission(effectiveMission);

  const llmResult = await runSovereignLlmRuntime({
    mission: effectiveMission,
    repoPaths: input.repoFiles.map((file) => file.path),
    selectedFilePath: input.selectedFilePath ?? 'README.md',
    previousPreview: input.previousPreview,
    memoryContext: input.memoryContext ?? [],
    runtimeEvents: input.runtimeEvents ?? [],
    allowExternalNoKey: true,
    allowUserKeyRoutes: input.allowUserKeyRoutes ?? false,
    userKeys: runtimeUserKeys(input),
    cards: input.cards ?? starterCards(),
    settings: input.settings ?? defaultSettings,
  });

  if (llmResult.ok && llmResult.brain) {
    assertSovereignBrainResult(llmResult.brain);
    assertPushableBrain(llmResult.providerId as never, effectiveMission, llmResult.brain);

    const implementationFiles = toImplementationFiles(llmResult.brain);
    implementationFiles.push({
      path: 'generated/sovereign-product/workflow.ts',
      content: `// Generated by Sovereign Studio\nexport const sovereignImplementationAudit = ${JSON.stringify({
        request: effectiveMission,
        generatedFiles: implementationFiles.map((file) => file.path),
        providerOrder: SOVEREIGN_LLM_ROUTES.map((route) => route.id),
        llmSource: llmResult.source,
        providerId: llmResult.providerId,
        attempts: llmResult.attempts,
        brain: {
          severity: llmResult.brain.analysis.severity,
          strategy: llmResult.brain.plan.strategy,
        },
        retrySeconds: 66,
      }, null, 2)} as const;\n`,
      reason: 'Audit artifact for generated implementation package.',
    });

    const architecture = analyzeRepoArchitecture(input.repoFiles.map((file) => file.path));
    const requestedWork = classifyRequestedWork(effectiveMission);

    const pkg: SovereignImplementationPackage = {
      architecture,
      brain: llmResult.brain,
      files: implementationFiles,
      suggestions: [
        `Target files: ${implementationFiles.map((file) => file.path).join(', ')}`,
        `Architecture: ${architecture.summary}`,
        `Brain: ${llmResult.brain.analysis.severity} / ${llmResult.brain.plan.estimatedComplexity}`,
        `LLM source: ${llmResult.source} via ${llmResult.providerId}`,
        'Wait for real GitHub checks before final approval.',
      ],
      providerRoutes: SOVEREIGN_LLM_ROUTES,
      requestedWork,
    };

    runtimeAssertSovereignPackage(pkg);
    assertGeneratedPackageReady(pkg, input.repoFiles);
    return pkg;
  }

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
