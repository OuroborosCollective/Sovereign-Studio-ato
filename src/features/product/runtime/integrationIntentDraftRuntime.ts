/**
 * Integration Intent Draft Runtime
 *
 * Pure runtime functions for creating, formatting, and reducing integration intent drafts.
 * Follows Sovereign runtime principles:
 * - No mocks, stubs, or facades in live paths
 * - No fake successes
 * - Progress derived from real runtime state
 * - Every action produces actionable events
 *
 * Issue #520: Runtime rule for normal non-question inputs as integration requests
 */

import type { SovereignActionEventInput } from './sovereignActionStreamRuntime';
import type { RepoFile } from '../../github/types';

// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ
// TYPES
// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ

export interface IntegrationIntentDraft {
  /** Unique identifier for this draft */
  readonly id: string;
  /** Original user input text */
  readonly originalText: string;
  /** Extracted/improved title for the integration task */
  readonly title: string;
  /** Core goal/objective of the integration */
  readonly goal: string;
  /** Scope: what files/areas might be affected */
  readonly scope: string[];
  /** Possible affected files derived from repo context */
  readonly affectedFiles: string[];
  /** Timestamp when draft was created */
  readonly createdAt: number;
  /** Rephrased/previewed text for the input field */
  readonly rephrasedText: string;
}

/**
 * Gate snapshot reflecting current runtime readiness.
 * These are REAL state checks, not hardcoded assumptions.
 */
export interface IntegrationIntentDraftGateSnapshot {
  readonly repoReady: boolean;
  readonly githubWriteReady: boolean;
  readonly directPatchReady: boolean;
  readonly openhandsReady: boolean;
  readonly blockerMessage?: string;
}

/**
 * State machine states for integration intent draft flow
 */
export type IntegrationIntentDraftState =
  | { status: 'idle' }
  | { status: 'pending'; draft: IntegrationIntentDraft }
  | { status: 'confirmed'; draft: IntegrationIntentDraft }
  | { status: 'rejected'; originalText: string }
  | { status: 'rephrased'; draft: IntegrationIntentDraft; rephrasedText: string };

/**
 * Actions that can be performed on the draft
 */
export type IntegrationIntentDraftAction =
  | { type: 'CREATE_DRAFT'; input: string; repoFiles?: RepoFile[]; options?: CreateDraftOptions }
  | { type: 'CONFIRM_DRAFT' }
  | { type: 'REJECT_DRAFT' }
  | { type: 'REPHRASE_DRAFT' }
  | { type: 'CLEAR_DRAFT' };

// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ
// INTERNAL HELPERS
// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ

/**
 * Generate a unique ID for drafts.
 * Uses provided seed for determinism in tests, falls back to time+random for production.
 */
function generateId(seed?: string): string {
  if (seed) {
    return `draft_${seed}`;
  }
  return `draft_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Extract keywords from input text for scope analysis
 */
function extractScopeKeywords(input: string): string[] {
  const keywords: string[] = [];
  const lower = input.toLowerCase();

  const scopePatterns = [
    { pattern: /ui|oberflГӨche|interface|komponente|komponent|button|button|eingabe|formular|form/i, label: 'UI/Komponenten' },
    { pattern: /runtime|routing|router|route|pfad|aktion/i, label: 'Runtime/Routing' },
    { pattern: /security|sicherheit|token|key|auth|zugang/i, label: 'Sicherheit/Auth' },
    { pattern: /test|testen|pruef|validierung/i, label: 'Tests/Validierung' },
    { pattern: /repo|repository|datei|file|struktur|architektur/i, label: 'Repo/Struktur' },
    { pattern: /github|pr|pull.?request|branch|commit/i, label: 'GitHub/Versionierung' },
    { pattern: /worker|executor|openhands|agent/i, label: 'Executor/Agent' },
    { pattern: /chat|nachricht|eingabe|eingabefeld/i, label: 'Chat/Interface' },
    { pattern: /api|endpoint|server|daten/i, label: 'API/Daten' },
    { pattern: /build|deploy|produktion|publish/i, label: 'Build/Deploy' },
  ];

  for (const { pattern, label } of scopePatterns) {
    if (pattern.test(lower)) {
      keywords.push(label);
    }
  }

  return keywords.length > 0 ? keywords : ['Allgemein'];
}

/**
 * Derive possible affected files from repo context and input
 */
function deriveAffectedFiles(input: string, repoFiles?: RepoFile[]): string[] {
  if (!repoFiles || repoFiles.length === 0) {
    return [];
  }

  const lower = input.toLowerCase();
  const affected: string[] = [];

  // Map keywords to potential file patterns
  const fileMappings: Array<{ keywords: string[]; patterns: string[] }> = [
    {
      keywords: ['ui', 'oberflГӨche', 'interface', 'komponente', 'button'],
      patterns: ['components', 'ui', 'styles'],
    },
    {
      keywords: ['runtime', 'routing', 'router'],
      patterns: ['runtime', 'router'],
    },
    {
      keywords: ['chat', 'nachricht', 'eingabe'],
      patterns: ['chat', 'conversation'],
    },
    {
      keywords: ['github', 'pr', 'pull'],
      patterns: ['github', 'pr'],
    },
    {
      keywords: ['worker', 'executor', 'openhands'],
      patterns: ['worker', 'executor', 'openhands'],
    },
    {
      keywords: ['security', 'sicherheit', 'token'],
      patterns: ['security', 'auth'],
    },
    {
      keywords: ['test'],
      patterns: ['test', '.test.', '.spec.'],
    },
  ];

  for (const { keywords, patterns } of fileMappings) {
    if (keywords.some((k) => lower.includes(k))) {
      for (const file of repoFiles) {
        if (file.type === 'blob') {
          const fileLower = file.path.toLowerCase();
          if (patterns.some((p) => fileLower.includes(p))) {
            affected.push(file.path);
            if (affected.length >= 5) break; // Limit to 5 suggestions
          }
        }
      }
    }
  }

  // If no specific matches, suggest top-level structure
  if (affected.length === 0 && repoFiles.length > 0) {
    const topDirs = new Set<string>();
    for (const file of repoFiles.slice(0, 20)) {
      const parts = file.path.split('/');
      if (parts.length > 1) {
        topDirs.add(parts[0]);
      }
    }
    return Array.from(topDirs).slice(0, 3).map((d) => `${d}/`);
  }

  return affected;
}

/**
 * Extract a concise title from input
 */
function extractTitle(input: string): string {
  // Remove common prefixes
  let cleaned = input
    .replace(/^(bitte |kГ¶nnten sie |kГ¶nntest du |ich mГ¶chte |ich will |soll |kann man |kГ¶nnen wir )+/gi, '')
    .trim();

  // Limit length
  if (cleaned.length > 80) {
    cleaned = cleaned.slice(0, 77) + '...';
  }

  // Capitalize first letter
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

/**
 * Extract the core goal from input
 */
function extractGoal(input: string): string {
  const lower = input.toLowerCase();

  // Pattern matching for common goals
  const goalPatterns: Array<{ pattern: RegExp; goal: string }> = [
    { pattern: /baue|gebaut|bauen|implementier|stelle her/i, goal: 'Neue FunktionalitГӨt implementieren' },
    { pattern: /fix|repariere|beheb|korrigier/i, goal: 'Fehler beheben' },
    { pattern: /ГӨnder|modifizier|anpass|umgestal/i, goal: 'Bestehende FunktionalitГӨt ГӨndern' },
    { pattern: /test|teste|prГјf/i, goal: 'Tests hinzufГјgen oder verbessern' },
    { pattern: /entfern|lГ¶sch|streich/i, goal: 'FunktionalitГӨt entfernen' },
    { pattern: /verbesser|optimier|verstГӨrk|hГӨrt/i, goal: 'QualitГӨt verbessern' },
    { pattern: /dokumentier|beschreib|erklГӨr/i, goal: 'Dokumentation erstellen' },
    { pattern: /refaktor|umstrukturiere|Гјberarbeite/i, goal: 'Code refaktorieren' },
  ];

  for (const { pattern, goal } of goalPatterns) {
    if (pattern.test(lower)) {
      return goal;
    }
  }

  return 'Integrationsauftrag analysieren und umsetzen';
}

/**
 * Create a rephrased version for the input field
 */
function createRephrasedText(input: string): string {
  let rephrased = input;

  // Remove trailing question mark and convert to imperative
  if (rephrased.endsWith('?')) {
    rephrased = rephrased.slice(0, -1);
  }

  // Make it more actionable
  if (!/^(baue|implementier|fix|ГӨnder|test|entfern|verbesser|dokumentier|refaktor)/i.test(rephrased)) {
    // Add "Implementiere" if no clear action verb
    if (!rephrased.startsWith('Der ') && !rephrased.startsWith('Die ')) {
      rephrased = 'Implementiere: ' + rephrased;
    }
  }

  return rephrased;
}

// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ
// CORE RUNTIME FUNCTIONS
// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ

export interface CreateDraftOptions {
  /** Override timestamp for deterministic testing */
  now?: number;
  /** Override ID seed for deterministic testing */
  idSeed?: string;
}

/**
 * Create an integration intent draft from user input.
 * Returns null if input should not be treated as an integration request.
 *
 * Rules:
 * - Questions ending with ? are not auto-executed
 * - Repo URLs are load commands, not integration requests
 * - Very short inputs (< 4 chars) are ignored
 * - Commands starting with / are handled by slash command parser
 *
 * @param input - The user input text
 * @param repoFiles - Optional repo files for affected file derivation
 * @param options - Optional overrides for deterministic testing (now, idSeed)
 */
export function createIntegrationIntentDraft(
  input: string,
  repoFiles?: RepoFile[],
  options?: CreateDraftOptions,
): IntegrationIntentDraft | null {
  const clean = input.trim();

  // Minimum length check
  if (clean.length < 4) {
    return null;
  }

  // Commands are not integration drafts
  if (clean.startsWith('/')) {
    return null;
  }

  // Questions are advisory, not auto-execution
  if (/\?\s*$/.test(clean)) {
    return null;
  }

  // GitHub URLs are load commands
  if (/^https?:\/\/github\.com\/[\w-]+\/[\w.-]+(?:\/.*)?$/i.test(clean)) {
    return null;
  }

  // Greetings are not integration drafts
  const greetingPattern = /^(hallo|hello|hey|guten morgen|guten tag|hi|thanks?|danke)/i;
  if (greetingPattern.test(clean)) {
    return null;
  }

  // ── Issue #522: P2 Fix 2 & 4 - Status/Retry Intents and Placeholder Missions
  // Status queries should not create drafts
  const statusPattern = /^(was ist|wie ist|status|stand|fortschritt|was läuft|was macht)/i;
  if (statusPattern.test(clean)) {
    return null;
  }

  // Retry intents should not create drafts
  const retryPattern = /^(nochmal|noch\s+ein|versuch|es\s+klappt|nicht\s+geht|funktioniert\s+nicht)/i;
  if (retryPattern.test(clean)) {
    return null;
  }

  // Placeholder missions that don't provide real direction
  // Issue #522 P2 Fix 4: Extended to include more vague inputs that lack concrete targets
  const placeholderPattern = /^(fehler|error|idee|ideen|idee:|plan|workflow|fehleranalyse|runtime\s+check|test\s+plan|mach\s+weiter|weiter|mach\s+was|mach\s+etwas|fix\s+me)$/i;
  if (placeholderPattern.test(clean)) {
    return null;
  }

  // Single-word or very short vague commands that lack context
  if (clean.length <= 12 && /^(fehler|plan|idee|ideen|weiter|mach|fix|verbesser|optimier|korrigier|beheb|hilf|hilfe|helfen)$/i.test(clean)) {
    return null;
  }

  const timestamp = options?.now ?? Date.now();

  return {
    id: generateId(options?.idSeed),
    originalText: clean,
    title: extractTitle(clean),
    goal: extractGoal(clean),
    scope: extractScopeKeywords(clean),
    affectedFiles: deriveAffectedFiles(clean, repoFiles),
    createdAt: timestamp,
    rephrasedText: createRephrasedText(clean),
  };
}

/**
 * Format a draft for display in the UI card.
 * Returns structured data for the IntegrationIntentDraftCard component.
 */
export function formatIntegrationIntentDraft(draft: IntegrationIntentDraft): {
  title: string;
  goal: string;
  scope: string[];
  affectedFiles: string[];
  hint: string;
} {
  return {
    title: draft.title,
    goal: draft.goal,
    scope: draft.scope,
    affectedFiles: draft.affectedFiles,
    hint: draft.rephrasedText !== draft.originalText
      ? `Vorschlag: "${draft.rephrasedText}"`
      : '',
  };
}

/**
 * Check if a draft can be confirmed based on current gate state.
 * Returns false if confirmation would fail due to missing prerequisites.
 * 
 * P2 Fix 4: Considers all valid execution paths:
 * - GitHub write ready (for Direct Patch)
 * - Direct Patch ready (valid token + repo)
 * - OpenHands ready (but GitHub write is still needed for actual writes)
 */
export function canConfirmIntegrationIntentDraft(
  draft: IntegrationIntentDraft,
  gates: IntegrationIntentDraftGateSnapshot,
): { canConfirm: boolean; blocker?: string } {
  // Must have repo ready for any integration
  if (!gates.repoReady) {
    return {
      canConfirm: false,
      blocker: 'Repository nicht geladen. Bitte zuerst Repo-Link senden.',
    };
  }

  // P2 Fix 4: Accept any valid execution path
  // Direct Patch and GitHub write are sufficient
  // OpenHands requires GitHub write for actual writes, but we allow the path
  // because the user can set up GitHub access when prompted
  if (gates.directPatchReady || gates.githubWriteReady) {
    return { canConfirm: true };
  }

  // OpenHands without GitHub write - show access gate option
  if (gates.openhandsReady) {
    return {
      canConfirm: false,
      blocker: 'GitHub-Zugang erforderlich für OpenHands-Ausführung.',
    };
  }

  // No write path available
  return {
    canConfirm: false,
    blocker: gates.blockerMessage || 'Kein Ausführungspfad verfügbar. Bitte GitHub-Zugang oder OpenHands konfigurieren.',
  };
}

/**
 * Reduce an action against the current draft state.
 * Returns the new state after applying the action.
 *
 * This is a pure function - no side effects, no API calls.
 */
export function reduceIntegrationIntentDraftAction(
  state: IntegrationIntentDraftState,
  action: IntegrationIntentDraftAction,
  repoFiles?: RepoFile[],
): IntegrationIntentDraftState {
  switch (action.type) {
    case 'CREATE_DRAFT': {
      const draft = createIntegrationIntentDraft(action.input, repoFiles, action.options);
      if (!draft) {
        return { status: 'idle' };
      }
      return { status: 'pending', draft };
    }

    case 'CONFIRM_DRAFT': {
      if (state.status !== 'pending') {
        return state;
      }
      return { status: 'confirmed', draft: state.draft };
    }

    case 'REJECT_DRAFT': {
      if (state.status !== 'pending') {
        return state;
      }
      return { status: 'rejected', originalText: state.draft.originalText };
    }

    case 'REPHRASE_DRAFT': {
      if (state.status !== 'pending') {
        return state;
      }
      const rephrasedText = state.draft.rephrasedText;
      return {
        status: 'rephrased',
        draft: state.draft,
        rephrasedText,
      };
    }

    case 'CLEAR_DRAFT': {
      return { status: 'idle' };
    }

    default: {
      // Exhaustive check - should never reach here
      const _exhaustive: never = action;
      return state;
    }
  }
}

// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ
// ACTION EVENT BUILDERS
// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ

/**
 * Build action events for the Sovereign Action Stream.
 * Every state transition must produce an event.
 */

export function buildDraftCreatedEvent(draft: IntegrationIntentDraft): SovereignActionEventInput {
  return {
    kind: 'intent_detected',
    route: 'runtime',
    label: 'Integrationsauftrag erkannt',
    detail: draft.title,
    state: 'done',
  };
}

export function buildDraftConfirmedEvent(draft: IntegrationIntentDraft): SovereignActionEventInput {
  return {
    kind: 'route_selected',
    route: 'runtime',
    label: 'Integrationsauftrag bestГӨtigt',
    detail: draft.title,
    state: 'done',
  };
}

export function buildDraftRejectedEvent(): SovereignActionEventInput {
  return {
    kind: 'blocked',
    route: 'runtime',
    label: 'Integrationsauftrag abgelehnt',
    detail: 'User hat den erkannten Auftrag verworfen',
    state: 'blocked',
  };
}

export function buildDraftRephrasedEvent(draft: IntegrationIntentDraft): SovereignActionEventInput {
  return {
    kind: 'intent_detected',
    route: 'runtime',
    label: 'Integrationsauftrag neu formuliert',
    detail: draft.rephrasedText,
    state: 'done',
  };
}

export function buildRouteStartedEvent(route: string): SovereignActionEventInput {
  return {
    kind: 'route_selected',
    route: route as SovereignActionEventInput['route'],
    label: 'Route gestartet',
    detail: 'Integration Execution',
    state: 'running',
  };
}

export function buildRouteBlockedEvent(blocker: string): SovereignActionEventInput {
  return {
    kind: 'blocked',
    route: 'runtime',
    label: 'Route blockiert',
    detail: blocker,
    state: 'blocked',
  };
}

// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ
// INITIAL STATE
// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ

export function createInitialDraftState(): IntegrationIntentDraftState {
  return { status: 'idle' };
}

// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ
// QUERY HELPERS
// в”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җв”Җ

/**
 * Check if the current state indicates a confirmed draft ready for execution
 */
export function isConfirmedDraft(state: IntegrationIntentDraftState): state is { status: 'confirmed'; draft: IntegrationIntentDraft } {
  return state.status === 'confirmed';
}

/**
 * Check if we have a pending draft to display
 */
export function hasPendingDraft(state: IntegrationIntentDraftState): state is { status: 'pending'; draft: IntegrationIntentDraft } {
  return state.status === 'pending';
}

/**
 * Get the current draft if any
 */
export function getCurrentDraft(state: IntegrationIntentDraftState): IntegrationIntentDraft | null {
  if (state.status === 'pending' || state.status === 'confirmed' || state.status === 'rephrased') {
    return state.draft;
  }
  return null;
}
