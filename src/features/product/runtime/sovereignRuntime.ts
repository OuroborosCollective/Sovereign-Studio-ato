import type { Card, ProjectSettings } from '../types';
import { freeFirstProviderRoute } from '../freeFirstPlan';
import {
  assertSovereignBrainResult,
  toImplementationFiles,
  type SovereignBrainResult,
} from '../brain/sovereignBrainContract';
import {
  buildLaunchPackageMarkdown,
  evaluateRepoReadiness,
  type RepoSignals,
} from './repoLaunchReadiness';

export type ProviderStatus = 'primary' | 'enabled' | 'fallback' | 'experimental';

export interface LlmRouteDescriptor {
  id: string;
  label: string;
  status: ProviderStatus;
  requiresApiKey: boolean;
  requiresUserOptIn: boolean;
  endpoint?: string;
}

export interface RepoArchitectureRuntime {
  summary: string;
  repoKind: 'react-vite-capacitor' | 'node' | 'docs-only' | 'unknown';
  hasReadme: boolean;
  hasGithubWorkflows: boolean;
  hasTests: boolean;
  hasRuntimeValidation: boolean;
  suggestedTargets: string[];
  riskNotes: string[];
}

export interface ImplementationFile {
  path: string;
  content: string;
  reason: string;
}

export interface SovereignImplementationPackage {
  architecture: RepoArchitectureRuntime;
  brain: SovereignBrainResult;
  files: ImplementationFile[];
  suggestions: string[];
  providerRoutes: LlmRouteDescriptor[];
  requestedWork: string;
}

export interface BuildImplementationInput {
  blueprint: string;
  cards: Card[];
  settings: ProjectSettings;
  selectedFilePath: string;
  repoPaths: string[];
  previousPreview?: string;
  existingProviderOrder?: string[];
}

const EXISTING_ROUTE_INFO: Record<string, LlmRouteDescriptor> = {
  'optional-user-keys': {
    id: 'optional-user-keys',
    label: 'Sovereign Backend · OpenRouter Paid + FreeLLM Free',
    status: 'primary',
    requiresApiKey: false,
    requiresUserOptIn: false,
    endpoint: '/api/llm/chat',
  },
};

export const SOVEREIGN_LLM_ROUTES: LlmRouteDescriptor[] = [
  ...freeFirstProviderRoute.map((id) => EXISTING_ROUTE_INFO[id]),
];

function hasPath(paths: string[], predicate: (path: string) => boolean): boolean {
  return paths.some((path) => predicate(path.toLowerCase()));
}

function includesAny(text: string, words: string[]): boolean {
  const value = text.toLowerCase();
  return words.some((word) => value.includes(word));
}

export function analyzeRepoArchitecture(repoPaths: string[]): RepoArchitectureRuntime {
  const hasPackageJson = hasPath(repoPaths, (path) => path === 'package.json');
  const hasAndroid = hasPath(repoPaths, (path) => path.startsWith('android/') || path === 'capacitor.config.ts');
  const hasVite = hasPath(repoPaths, (path) => path.includes('vite'));
  const hasReadme = hasPath(repoPaths, (path) => path === 'readme.md');
  const hasGithubWorkflows = hasPath(repoPaths, (path) => path.startsWith('.github/workflows/'));
  const hasTests = hasPath(repoPaths, (path) => path.includes('.test.') || path.includes('.spec.') || path.startsWith('tests/'));
  const hasRuntimeValidation = hasPath(repoPaths, (path) => path.includes('runtimevalidation') || path.includes('/runtime/') || path.includes('/brain/'));

  const repoKind = hasPackageJson && hasAndroid && hasVite
    ? 'react-vite-capacitor'
    : hasPackageJson
      ? 'node'
      : hasReadme && repoPaths.length < 25
        ? 'docs-only'
        : 'unknown';

  const riskNotes: string[] = [];
  if (!hasTests) riskNotes.push('No test files detected in scanned tree.');
  if (!hasGithubWorkflows) riskNotes.push('No workflow files detected.');
  if (!hasRuntimeValidation) riskNotes.push('Runtime validation should be expanded.');

  return {
    summary: `${repoKind} repo, README=${hasReadme ? 'yes' : 'no'}, workflows=${hasGithubWorkflows ? 'yes' : 'no'}, tests=${hasTests ? 'yes' : 'no'}, runtime=${hasRuntimeValidation ? 'yes' : 'no'}`,
    repoKind,
    hasReadme,
    hasGithubWorkflows,
    hasTests,
    hasRuntimeValidation,
    suggestedTargets: ['README.md', 'docs/UPDATE_HISTORY.md', 'docs/SOVEREIGN_RUNTIME.md', 'docs/LAUNCH_READINESS.md', 'generated/sovereign-product/workflow.ts'],
    riskNotes,
  };
}

export function classifyRequestedWork(blueprint: string): 'readme-docs' | 'tests' | 'runtime-hardening' | 'feature' | 'general' {
  if (includesAny(blueprint, ['readme', 'documentation', 'dokumentation', 'update history', 'changelog'])) return 'readme-docs';
  if (includesAny(blueprint, ['runtime', 'fallback', 'llm', 'provider', 'workflow', 'github'])) return 'runtime-hardening';
  if (includesAny(blueprint, ['test', 'vitest', 'e2e', 'smoke', 'typecheck', 'lint'])) return 'tests';
  if (includesAny(blueprint, ['build', 'implement', 'feature', 'route', 'component'])) return 'feature';
  return 'general';
}

function providerList(): string {
  return SOVEREIGN_LLM_ROUTES.map((route, index) => `${index + 1}. ${route.id} - ${route.label}`).join('\n');
}

function buildRepoSignals(input: BuildImplementationInput, architecture: RepoArchitectureRuntime): RepoSignals {
  return {
    owner: 'target',
    repo: 'repository',
    recentCommitCount: 0,
    branchProtectionActive: false,
    hasReadme: architecture.hasReadme,
    hasLicense: hasPath(input.repoPaths, (path) => path === 'license' || path === 'license.md'),
    hasTests: architecture.hasTests,
    hasGithubWorkflows: architecture.hasGithubWorkflows,
    hasPackageJson: hasPath(input.repoPaths, (path) => path === 'package.json'),
    hasRuntimeValidation: architecture.hasRuntimeValidation,
  };
}

function createDocsBrain(input: BuildImplementationInput, architecture: RepoArchitectureRuntime): SovereignBrainResult {
  const signals = buildRepoSignals(input, architecture);
  const readiness = evaluateRepoReadiness(signals);
  const launchReadiness = buildLaunchPackageMarkdown(signals, readiness, input.blueprint);
  const readme = `# Sovereign Studio\n\n${input.blueprint}\n\n## Runtime goals\n\n- Provider output is never trusted blindly.\n- Each result must pass the Sovereign five-layer brain contract.\n- README requests must update README/docs, not only generated preview artifacts.\n- GitHub push uses real repo tree analysis before branch creation.\n- Workflows are surfaced to the user before final approval.\n\n## Architecture\n\n${architecture.summary}\n\n## Launch readiness\n\n${readiness.summary}\n\n## Provider order\n\n${providerList()}\n`;

  const history = `# Update History\n\n## Sovereign brain guarded package\n\nRequest:\n\n${input.blueprint}\n\nArchitecture:\n\n${architecture.summary}\n\nReadiness:\n\n${readiness.summary}\n\nCards:\n\n${input.cards.map((card) => `- ${card.title}: ${card.body}`).join('\n') || '- none'}\n`;

  const runtime = `# Sovereign Runtime\n\n## Brain gate\n\nEvery provider route must produce perception, analysis, plan, execution and learning layers. A response without execution patches is rejected before GitHub push.\n\n## Routes\n\n${providerList()}\n\n## Launch readiness rail\n\nSovereign runtime imports the RepoP3N12 launch-readiness idea as deterministic TypeScript checks: safe repo inspection, task extraction, readiness evaluation, owner checklist, copywriting and workflow watch.\n\n## Checks\n\n- npm run type-check\n- npm run lint\n- npm run test:run\n- npm run build:web\n`;

  return {
    perception: {
      domain: architecture.repoKind === 'react-vite-capacitor' ? 'React Vite Capacitor repository automation' : 'repository automation',
      intent: input.blueprint,
      architecture: architecture.summary,
      confidence: architecture.repoKind === 'unknown' ? 0.62 : 0.86,
    },
    analysis: {
      severity: readiness.grade === 'BLOCKED' ? 'high' : 'medium',
      issues: [
        {
          type: 'architecture',
          location: 'generation pipeline',
          description: 'Single preview artifact generation does not satisfy documentation requests.',
          impact: 'README tasks can produce irrelevant workflow artifacts and failing PRs.',
        },
      ],
      rootCause: 'Provider output was not gated through a repository-aware brain schema before push.',
      systemicRisk: 'The app may open noisy PRs that fail checks and do not satisfy the user request.',
    },
    plan: {
      strategy: 'Classify request, analyze repo tree, score launch readiness, produce concrete files, validate package, then push through GitHub PR flow.',
      phases: [
        { phase: 1, name: 'Perception', actions: ['scan repo tree', 'classify request'], rationale: 'Target files depend on repository shape.' },
        { phase: 2, name: 'Readiness', actions: ['score docs/tests/workflows', 'build owner checklist'], rationale: 'Launch readiness catches missing documentation and CI before push.' },
        { phase: 3, name: 'Execution', actions: ['create files', 'wait workflows'], rationale: 'The PR must contain real requested files.' },
      ],
      estimatedComplexity: readiness.grade === 'BLOCKED' ? 'high' : 'medium',
    },
    execution: {
      patches: [
        { file: 'README.md', type: architecture.hasReadme ? 'replace' : 'create', description: 'Repository README generated from architecture and launch-readiness analysis.', code: readme },
        { file: 'docs/UPDATE_HISTORY.md', type: 'create', description: 'Update history generated from request context.', code: history },
        { file: 'docs/SOVEREIGN_RUNTIME.md', type: 'create', description: 'Runtime and provider behavior documentation.', code: runtime },
        { file: 'docs/LAUNCH_READINESS.md', type: 'create', description: 'Launch readiness package generated from RepoP3N12-derived rubric.', code: launchReadiness },
      ],
      integrationNotes: 'Use these patches as GitHub tree entries after user approval.',
      testStrategy: 'Run type-check, lint, test:run and build:web; wait for GitHub checks with 66 second retry windows.',
    },
    learning: {
      patterns: ['Brain-gated providers prevent preview-only PRs.', 'Repository tree analysis must happen before file generation.', 'Launch readiness scoring catches missing CI and docs before merge.'],
      rules: ['Never push provider text without valid execution patches.', 'README tasks must touch README or docs files.', 'Workflow failures must route back to fix mode.'],
      architectureUpgrade: 'Promote Sovereign brain output plus launch-readiness report to the central planning contract of the app.',
    },
  };
}

function createFallbackBrain(input: BuildImplementationInput, architecture: RepoArchitectureRuntime): SovereignBrainResult {
  return {
    perception: { domain: 'repository automation', intent: input.blueprint, architecture: architecture.summary, confidence: 0.7 },
    analysis: {
      severity: 'low',
      issues: [{ type: 'missing', location: 'request classifier', description: 'No specific file class was detected.', impact: 'A visible plan is safer than a fake code patch.' }],
      rootCause: 'The request needs more targeted file selection.',
      systemicRisk: 'A generic provider response could push unrelated code.',
    },
    plan: {
      strategy: 'Create a visible plan file and keep the user in the approval loop.',
      phases: [{ phase: 1, name: 'Plan', actions: ['record request', 'surface next steps'], rationale: 'Avoid fake implementation.' }],
      estimatedComplexity: 'low',
    },
    execution: {
      patches: [{ file: 'docs/SOVEREIGN_PLAN.md', type: 'create', description: 'Visible implementation plan.', code: `# Sovereign Plan\n\n${input.blueprint}\n` }],
      integrationNotes: 'Use as planning artifact only.',
      testStrategy: 'Run type-check, lint and tests after concrete patches are accepted.',
    },
    learning: { patterns: ['Fallback planning is safer than fake implementation.'], rules: ['No concrete patch, no code push.'], architectureUpgrade: 'Ask the brain for more precise target files.' },
  };
}

export function buildSovereignImplementationPackage(input: BuildImplementationInput): SovereignImplementationPackage {
  const architecture = analyzeRepoArchitecture(input.repoPaths);
  const requestedWork = classifyRequestedWork(input.blueprint);
  const brain = requestedWork === 'readme-docs'
    ? createDocsBrain(input, architecture)
    : createFallbackBrain(input, architecture);

  assertSovereignBrainResult(brain);
  const files = toImplementationFiles(brain);
  files.push({
    path: 'generated/sovereign-product/workflow.ts',
    content: `// Generated by Sovereign Studio\nexport const sovereignImplementationAudit = ${JSON.stringify({
      request: input.blueprint,
      architecture: architecture.summary,
      generatedFiles: files.map((file) => file.path),
      providerOrder: SOVEREIGN_LLM_ROUTES.map((route) => route.id),
      brain: {
        severity: brain.analysis.severity,
        strategy: brain.plan.strategy,
      },
      retrySeconds: 66,
    }, null, 2)} as const;\n`,
    reason: 'Audit artifact for generated implementation package.',
  });

  return {
    architecture,
    brain,
    files,
    suggestions: [
      `Target files: ${files.map((file) => file.path).join(', ')}`,
      `Architecture: ${architecture.summary}`,
      `Brain: ${brain.analysis.severity} / ${brain.plan.estimatedComplexity}`,
      'Wait for real GitHub checks before final approval.',
    ],
    providerRoutes: SOVEREIGN_LLM_ROUTES,
    requestedWork,
  };
}

export function buildWorkflowWatchSummary(checkRuns: string[], retrySeconds = 66, attempt = 1, maxAttempts = 3): string {
  const names = checkRuns.length ? checkRuns.join(' | ') : 'no checks';
  return `Workflow Watch ${attempt}/${maxAttempts}: ${names}. Next retry in ${retrySeconds}s if not green.`;
}

export function runtimeAssertSovereignPackage(pkg: SovereignImplementationPackage): void {
  if (!pkg.files.length) throw new Error('Package must contain real files.');
  const invalid = pkg.files.find((file) => !file.path || !file.content.trim());
  if (invalid) throw new Error(`Invalid generated file: ${invalid.path || '<missing-path>'}`);
  if (pkg.providerRoutes[0]?.id !== 'optional-user-keys') throw new Error('Online route order must start with the Sovereign Backend.');
  assertSovereignBrainResult(pkg.brain);
}
