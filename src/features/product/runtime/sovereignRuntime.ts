import type { Card, ProjectSettings } from '../types';

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

export const SOVEREIGN_LLM_ROUTES: LlmRouteDescriptor[] = [
  { id: 'current-primary', label: 'Existing first provider', status: 'primary', requiresApiKey: true, requiresUserOptIn: false },
  { id: 'pollinations-dev-key', label: 'Existing Pollinations dev-key route', status: 'enabled', requiresApiKey: true, requiresUserOptIn: false },
  { id: 'mlvocka-dev-key', label: 'Existing Mlvocka dev-key route', status: 'enabled', requiresApiKey: true, requiresUserOptIn: false },
  { id: 'ovh-anonymous-code-chat', label: 'OVHcloud anonymous code_chat@latest', status: 'fallback', requiresApiKey: false, requiresUserOptIn: false, endpoint: 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions' },
  { id: 'ovh-anonymous-fixed-model', label: 'OVHcloud anonymous pinned model', status: 'fallback', requiresApiKey: false, requiresUserOptIn: false, endpoint: 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions' },
  { id: 'puter-js-opt-in', label: 'Puter.js opt-in route', status: 'experimental', requiresApiKey: false, requiresUserOptIn: true },
  { id: 'hf-curated-public-space', label: 'Curated Hugging Face public Space', status: 'experimental', requiresApiKey: false, requiresUserOptIn: true },
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
  const hasRuntimeValidation = hasPath(repoPaths, (path) => path.includes('runtimevalidation') || path.includes('/runtime/'));

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
    suggestedTargets: ['README.md', 'docs/UPDATE_HISTORY.md', 'docs/SOVEREIGN_RUNTIME.md', 'generated/sovereign-product/workflow.ts'],
    riskNotes,
  };
}

export function classifyRequestedWork(blueprint: string): 'readme-docs' | 'tests' | 'runtime-hardening' | 'feature' | 'general' {
  if (includesAny(blueprint, ['readme', 'documentation', 'dokumentation', 'update history', 'changelog'])) return 'readme-docs';
  if (includesAny(blueprint, ['test', 'vitest', 'e2e', 'smoke', 'typecheck', 'lint'])) return 'tests';
  if (includesAny(blueprint, ['runtime', 'fallback', 'llm', 'provider', 'workflow', 'github'])) return 'runtime-hardening';
  if (includesAny(blueprint, ['build', 'implement', 'feature', 'route', 'component'])) return 'feature';
  return 'general';
}

function readmeContent(input: BuildImplementationInput, architecture: RepoArchitectureRuntime): string {
  return `# Sovereign Studio\n\n${input.blueprint}\n\n## Runtime goals\n\n- Keep the existing first provider as the first route.\n- Keep existing dev-key routes in place.\n- Add legal fallback routes underneath the existing routes.\n- Analyze the live GitHub tree before push.\n- Push real requested files, not only a preview artifact.\n- Wait for GitHub checks with a visible 66 second retry window.\n\n## Architecture\n\n${architecture.summary}\n\n## Provider order\n\n${SOVEREIGN_LLM_ROUTES.map((route, index) => `${index + 1}. ${route.id} - ${route.label}`).join('\n')}\n\n## Validation\n\n\`\`\`bash\nnpm run type-check\nnpm run lint\nnpm run test:run\nnpm run build:web\n\`\`\`\n`;
}

function updateHistoryContent(input: BuildImplementationInput, architecture: RepoArchitectureRuntime): string {
  return `# Update History\n\n## ${new Date().toISOString()} - Sovereign implementation package\n\nRequest:\n\n${input.blueprint}\n\nArchitecture:\n\n${architecture.summary}\n\nCards:\n\n${input.cards.map((card) => `- ${card.title}: ${card.body}`).join('\n') || '- none'}\n\nChanges:\n\n- Documentation requests now generate documentation files.\n- GitHub push can write multiple files.\n- Provider order is preserved before fallback routes.\n- Workflow check waiting uses a visible 66 second retry window.\n`;
}

function runtimeDocContent(input: BuildImplementationInput, architecture: RepoArchitectureRuntime): string {
  return `# Sovereign Runtime\n\n## Request\n\n${input.blueprint}\n\n## Architecture\n\n${architecture.summary}\n\n## LLM routes\n\n${SOVEREIGN_LLM_ROUTES.map((route) => `- ${route.id}: ${route.label}; status=${route.status}; key=${route.requiresApiKey ? 'yes' : 'no'}; optIn=${route.requiresUserOptIn ? 'yes' : 'no'}`).join('\n')}\n\n## Rules\n\n- Existing primary provider stays first.\n- Dev-key integrations stay enabled.\n- OVH anonymous routes are fallback only.\n- Puter and Hugging Face routes require explicit user opt-in.\n- Tokens and private repository data must not be sent to public fallback routes.\n- Failed provider responses remain real errors and are not hidden.\n`;
}

function auditContent(input: BuildImplementationInput, architecture: RepoArchitectureRuntime, files: ImplementationFile[]): string {
  return `// Generated by Sovereign Studio\nexport const sovereignImplementationAudit = ${JSON.stringify({
    request: input.blueprint,
    architecture: architecture.summary,
    generatedFiles: files.map((file) => file.path),
    providerOrder: SOVEREIGN_LLM_ROUTES.map((route) => route.id),
    retrySeconds: 66,
  }, null, 2)} as const;\n`;
}

export function buildSovereignImplementationPackage(input: BuildImplementationInput): SovereignImplementationPackage {
  const architecture = analyzeRepoArchitecture(input.repoPaths);
  const requestedWork = classifyRequestedWork(input.blueprint);
  const files: ImplementationFile[] = [];

  if (requestedWork === 'readme-docs' || requestedWork === 'general') {
    files.push({ path: 'README.md', content: readmeContent(input, architecture), reason: 'Repository documentation requested.' });
    files.push({ path: 'docs/UPDATE_HISTORY.md', content: updateHistoryContent(input, architecture), reason: 'Update history requested.' });
  }

  if (requestedWork === 'runtime-hardening' || requestedWork === 'readme-docs' || requestedWork === 'general') {
    files.push({ path: 'docs/SOVEREIGN_RUNTIME.md', content: runtimeDocContent(input, architecture), reason: 'Runtime behavior documentation.' });
  }

  if (requestedWork === 'tests') {
    files.push({
      path: 'docs/TEST_PLAN.md',
      content: `# Test Plan\n\n${input.blueprint}\n\n- npm run type-check\n- npm run lint\n- npm run test:run\n- npm run build:web\n`,
      reason: 'Test request.',
    });
  }

  const auditFile: ImplementationFile = {
    path: 'generated/sovereign-product/workflow.ts',
    content: '',
    reason: 'Audit artifact for generated implementation package.',
  };
  auditFile.content = auditContent(input, architecture, [...files, auditFile]);
  files.push(auditFile);

  return {
    architecture,
    files,
    suggestions: [
      `Target files: ${files.map((file) => file.path).join(', ')}`,
      `Architecture: ${architecture.summary}`,
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
  if (pkg.providerRoutes[0]?.id !== 'current-primary') throw new Error('Existing primary provider must remain first.');
}
