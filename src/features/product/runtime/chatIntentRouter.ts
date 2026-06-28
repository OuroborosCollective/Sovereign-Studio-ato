/**
 * Chat Intent Router - Runtime spine for chat workbench
 *
 * Translates natural language messages from the chat into validated runtime actions.
 * UI sends intent, runtime validates preconditions and produces actionable output.
 *
 * No DOM/React dependencies - pure runtime module.
 */

export type ChatIntent =
  | 'load-repo'
  | 'explain-status'
  | 'generate-package'
  | 'create-draft-pr'
  | 'show-diff'
  | 'watch-workflow'
  | 'repair-workflow'
  | 'search-patterns'
  | 'unknown';

/**
 * Extended input for more granular precondition checks.
 * All boolean fields default to false for backward compatibility.
 */
export interface ChatIntentRouterInput {
  message: string;
  repoReady: boolean;
  repoFileCount: number;
  hasToken: boolean;
  hasPackage: boolean;
  hasDraft: boolean;
  /** If true, indicates a concrete mission was provided (not placeholder text) */
  hasConcreteMission?: boolean;
  /** If true, generated files passed self-review and contain actionable output */
  selfReviewAccepted?: boolean;
  /** If true, draft PR has a recorded commit SHA for workflow watching */
  hasDraftCommit?: boolean;
  /** If true, workflow failure report exists for repair decisions */
  hasWorkflowReport?: boolean;
  activeBlockers: string[];
}

export interface ChatIntentRouterOutput {
  intent: ChatIntent;
  allowed: boolean;
  blockedReason: string;
  recommendedAction: string;
  targetTab?: 'repo' | 'builder' | 'files' | 'diff' | 'workflow' | 'repair';
}

interface IntentPrecondition {
  requiredRepoReady: boolean;
  requiredHasToken: boolean;
  requiredHasPackage: boolean;
  requiredHasDraft: boolean;
  minFileCount: number;
  maxActiveBlockers: number;
}

const INTENT_PRECONDITIONS: Record<ChatIntent, IntentPrecondition> = {
  'load-repo': {
    requiredRepoReady: false,
    requiredHasToken: false, // Allow public repos without token
    requiredHasPackage: false,
    requiredHasDraft: false,
    minFileCount: 0,
    maxActiveBlockers: Infinity,
  },
  'explain-status': {
    requiredRepoReady: false,
    requiredHasToken: false,
    requiredHasPackage: false,
    requiredHasDraft: false,
    minFileCount: 0,
    maxActiveBlockers: Infinity,
  },
  'generate-package': {
    requiredRepoReady: true,
    requiredHasToken: false,
    requiredHasPackage: false,
    requiredHasDraft: false,
    minFileCount: 1,
    maxActiveBlockers: 0,
  },
  'create-draft-pr': {
    requiredRepoReady: true,
    requiredHasToken: true,
    requiredHasPackage: true,
    requiredHasDraft: false,
    minFileCount: 1,
    maxActiveBlockers: 0,
  },
  'show-diff': {
    requiredRepoReady: true,
    requiredHasToken: false,
    requiredHasPackage: true,
    requiredHasDraft: false,
    minFileCount: 1,
    maxActiveBlockers: Infinity,
  },
  'watch-workflow': {
    requiredRepoReady: true,
    requiredHasToken: true,
    requiredHasPackage: false,
    requiredHasDraft: true,
    minFileCount: 0,
    maxActiveBlockers: Infinity,
  },
  'repair-workflow': {
    requiredRepoReady: true,
    requiredHasToken: true,
    requiredHasPackage: false,
    requiredHasDraft: true,
    minFileCount: 0,
    maxActiveBlockers: Infinity,
  },
  'search-patterns': {
    requiredRepoReady: true,
    requiredHasToken: false,
    requiredHasPackage: false,
    requiredHasDraft: false,
    minFileCount: 1, // Allow small repos with non-empty file list
    maxActiveBlockers: Infinity,
  },
  'unknown': {
    requiredRepoReady: false,
    requiredHasToken: false,
    requiredHasPackage: false,
    requiredHasDraft: false,
    minFileCount: 0,
    maxActiveBlockers: Infinity,
  },
};

// Intents that should NOT be blocked by existing draft PR (read-only actions)
const READ_ONLY_INTENTS = new Set<ChatIntent>([
  'explain-status',
  'show-diff',
  'watch-workflow',
  'search-patterns',
]);

const INTENT_SIGNALS: Record<ChatIntent, string[]> = {
  'load-repo': [
    'load repo', 'fetch repository', 'open repo', 'select repository', 'repo url', 'github link',
    'lade repository', 'repository laden', 'repo laden', 'github repository öffnen',
    'welches repository', 'repo auswählen',
    // GitHub URL patterns
    'github.com/', 'https://github.com/',
  ],
  'explain-status': [
    'status', 'was ist der status', 'what is the status', 'explain', 'erkläre', 'show state', 'zustand',
    'wie sieht es aus', 'was läuft gerade', 'was ist los', 'aktueller stand',
    'was wurde gemacht', 'was ist passiert',
  ],
  'generate-package': [
    'generate', 'build package', 'create package', 'implement',
    'erstelle paket', 'paket erstellen', 'generiere paket', 'paket generieren',
    'erstelle implementierung', 'implementierung erstellen', 'baue paket',
    'führe auftrag aus', 'auftrag umsetzen',
  ],
  'create-draft-pr': [
    'draft pr', 'pull request', 'create pr', 'publish', 'veröffentlichen',
    'pr erstellen', 'pull request erstellen', 'draft pr erstellen',
    'erstelle pull request', 'veröffentliche änderungen',
    'pr raus', 'mach den pr', 'pr machen',
  ],
  'show-diff': [
    'diff', 'show changes', 'differences', 'vergleich',
    'änderungen', 'was wurde geändert', 'unterschiede anzeigen',
    'zeig änderungen', 'zeig diff', 'vergleich anzeigen',
  ],
  'watch-workflow': [
    'watch workflow', 'workflow status', 'ci status', 'github actions',
    'beobachte workflow', 'workflow überwachen', 'ci status prüfen',
    'läuft der workflow', 'workflow ergebnis', 'github actions status',
  ],
  'repair-workflow': [
    'fix workflow', 'ci fix', // Scope to CI/workflow wording only
    'workflow reparieren', 'behebe workflow', 'workflowfehler beheben',
    'ci fehler', 'workflowfehler',
  ],
  'search-patterns': [
    'search patterns', 'find code', 'pattern analysis',
    'suche muster', 'muster suchen', 'code muster finden',
    'analyse muster', 'struktur analyse', 'code analyse',
  ],
  'unknown': [],
};

const DEFAULT_RECOMMENDED_ACTIONS: Record<ChatIntent, string> = {
  'load-repo': 'Lade ein GitHub Repository um zu starten.',
  'explain-status': 'Zeige aktuellen Runtime-Status.',
  'generate-package': 'Lade ein Repository und gib einen konkreten Auftrag ein.',
  'create-draft-pr': 'Erst Paket generieren, dann Draft PR erstellen.',
  'show-diff': 'Paket generieren um Diff zu sehen.',
  'watch-workflow': 'Erst Draft PR erstellen, dann Workflow beobachten.',
  'repair-workflow': 'Erst Draft PR erstellen, dann Workflow reparieren.',
  'search-patterns': 'Lade ein Repository mit genügend Dateien für Musteranalyse.',
  'unknown': 'Gib einen klaren Auftrag oder eine Anfrage ein.',
};

const TARGET_TABS: Record<ChatIntent, ChatIntentRouterOutput['targetTab'] | undefined> = {
  'load-repo': 'repo',
  'explain-status': undefined,
  'generate-package': 'builder',
  'create-draft-pr': 'files',
  'show-diff': 'diff',
  'watch-workflow': 'workflow',
  'repair-workflow': 'repair',
  'search-patterns': 'files',
  'unknown': undefined,
};

const GITHUB_URL_REGEX = /^https?:\/\/github\.com\/[\w-]+\/[\w.-]+(?:\/.*)?$/i;

function detectIntent(message: string): ChatIntent {
  const normalized = message.toLowerCase().trim();

  // Check for GitHub URL first (more specific than word signals)
  if (GITHUB_URL_REGEX.test(message.trim())) {
    return 'load-repo';
  }

  // Sort signals by specificity: workflow-specific first, then generic
  const intentOrder: ChatIntent[] = [
    'watch-workflow',
    'repair-workflow',
    'load-repo',
    'create-draft-pr',
    'show-diff',
    'generate-package',
    'search-patterns',
    'explain-status',
  ];

  for (const intent of intentOrder) {
    const signals = INTENT_SIGNALS[intent];
    for (const signal of signals) {
      if (normalized.includes(signal)) {
        return intent;
      }
    }
  }

  return 'unknown';
}

function buildBlockedReason(intent: ChatIntent, input: ChatIntentRouterInput): string {
  const preconditions = INTENT_PRECONDITIONS[intent];

  if (preconditions.requiredRepoReady && !input.repoReady) {
    return 'Repository snapshot is not ready. Load a repository first.';
  }
  if (preconditions.requiredHasToken && !input.hasToken) {
    return 'GitHub token required. Add your token to proceed.';
  }
  if (preconditions.requiredHasPackage && !input.hasPackage) {
    return 'No package generated yet. Generate a package first.';
  }
  if (preconditions.requiredHasDraft && !input.hasDraft) {
    return 'No draft PR exists. Create a draft PR first.';
  }
  // Only block create-draft-pr when draft already exists, not read-only intents
  if (intent === 'create-draft-pr' && input.hasDraft) {
    return 'Draft PR already exists. Use the existing draft or close it first.';
  }
  if (input.repoFileCount < preconditions.minFileCount) {
    return `Repository needs at least ${preconditions.minFileCount} files. Current: ${input.repoFileCount}`;
  }
  if (input.activeBlockers.length > preconditions.maxActiveBlockers) {
    return `Too many active blockers: ${input.activeBlockers.join(', ')}. Resolve blockers first.`;
  }

  // P1: Block vague package-build commands without concrete mission
  if (intent === 'generate-package' && input.hasConcreteMission === false) {
    return 'Enter a concrete mission (not placeholder text) to generate a package.';
  }

  // P1: Gate Draft PR on generated-file self-review acceptance
  if (intent === 'create-draft-pr' && input.selfReviewAccepted === false) {
    return 'Generated files must pass review before creating draft PR.';
  }

  // P1: Require workflow report before repair
  if (intent === 'repair-workflow' && input.hasWorkflowReport === false) {
    return 'Watch the workflow first to get the failure report for repair.';
  }

  // P1: Require draft commit SHA before watching workflows
  if (intent === 'watch-workflow' && input.hasDraftCommit === false) {
    return 'Draft PR commit must be recorded before watching workflow.';
  }

  return '';
}

export function routeChatIntent(input: ChatIntentRouterInput): ChatIntentRouterOutput {
  const intent = detectIntent(input.message);

  // Unknown intent is always blocked - user needs to provide a clear mission
  if (intent === 'unknown') {
    return {
      intent: 'unknown',
      allowed: false,
      blockedReason: 'Enter a clear mission or request.',
      recommendedAction: 'Enter a clear mission or request.',
      targetTab: undefined,
    };
  }

  const blockedReason = buildBlockedReason(intent, input);
  const allowed = blockedReason === '';

  return {
    intent,
    allowed,
    blockedReason,
    recommendedAction: allowed ? DEFAULT_RECOMMENDED_ACTIONS[intent] : blockedReason,
    targetTab: TARGET_TABS[intent],
  };
}

export function getIntentPreconditions(intent: ChatIntent): IntentPrecondition {
  return INTENT_PRECONDITIONS[intent];
}

export function getAvailableIntents(input: Pick<ChatIntentRouterInput, 'repoReady' | 'hasToken' | 'hasPackage' | 'hasDraft' | 'repoFileCount' | 'activeBlockers' | 'hasConcreteMission' | 'selfReviewAccepted' | 'hasDraftCommit' | 'hasWorkflowReport'>): ChatIntent[] {
  return (Object.keys(INTENT_PRECONDITIONS) as ChatIntent[]).filter((intent) => {
    if (intent === 'unknown') return false;
    const blockedReason = buildBlockedReason(intent, {
      ...input,
      message: '',
    });
    return blockedReason === '';
  });
}