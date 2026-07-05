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

// ─────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────

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
  | { type: 'CREATE_DRAFT'; input: string; repoFiles?: RepoFile[] }
  | { type: 'CONFIRM_DRAFT' }
  | { type: 'REJECT_DRAFT' }
  | { type: 'REPHRASE_DRAFT' }
  | { type: 'CLEAR_DRAFT' };

// ─────────────────────────────────────────────────────────────
// INTERNAL HELPERS
// ─────────────────────────────────────────────────────────────

function generateId(): string {
  return `draft_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Extract keywords from input text for scope analysis
 */
function extractScopeKeywords(input: string): string[] {
  const keywords: string[] = [];
  const lower = input.toLowerCase();

  const scopePatterns = [
    { pattern: /ui|oberfläche|interface|komponente|komponent|button|button|eingabe|formular|form/i, label: 'UI/Komponenten' },
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
      keywords: ['ui', 'oberfläche', 'interface', 'komponente', 'button'],
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
    .replace(/^(bitte |könnten sie |könntest du |ich möchte |ich will |soll |kann man |können wir )+/gi, '')
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
    { pattern: /baue|gebaut|bauen|implementier|stelle her/i, goal: 'Neue Funktionalität implementieren' },
    { pattern: /fix|repariere|beheb|korrigier/i, goal: 'Fehler beheben' },
    { pattern: /änder|modifizier|anpass|umgestal/i, goal: 'Bestehende Funktionalität ändern' },
    { pattern: /test|teste|prüf/i, goal: 'Tests hinzufügen oder verbessern' },
    { pattern: /entfern|lösch|streich/i, goal: 'Funktionalität entfernen' },
    { pattern: /verbesser|optimier|verstärk|härt/i, goal: 'Qualität verbessern' },
    { pattern: /dokumentier|beschreib|erklär/i, goal: 'Dokumentation erstellen' },
    { pattern: /refaktor|umstrukturiere|überarbeite/i, goal: 'Code refaktorieren' },
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
  if (!/^(baue|implementier|fix|änder|test|entfern|verbesser|dokumentier|refaktor)/i.test(rephrased)) {
    // Add "Implementiere" if no clear action verb
    if (!rephrased.startsWith('Der ') && !rephrased.startsWith('Die ')) {
      rephrased = 'Implementiere: ' + rephrased;
    }
  }

  return rephrased;
}

// ─────────────────────────────────────────────────────────────
// CORE RUNTIME FUNCTIONS
// ─────────────────────────────────────────────────────────────

/**
 * Create an integration intent draft from user input.
 * Returns null if input should not be treated as an integration request.
 *
 * Rules:
 * - Questions ending with ? are not auto-executed
 * - Repo URLs are load commands, not integration requests
 * - Very short inputs (< 4 chars) are ignored
 * - Commands starting with / are handled by slash command parser
 */
export function createIntegrationIntentDraft(
  input: string,
  repoFiles?: RepoFile[],
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

  const now = Date.now();

  return {
    id: generateId(),
    originalText: clean,
    title: extractTitle(clean),
    goal: extractGoal(clean),
    scope: extractScopeKeywords(clean),
    affectedFiles: deriveAffectedFiles(clean, repoFiles),
    createdAt: now,
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

  // For GitHub write operations, need GitHub write ready OR executor ready
  if (gates.githubWriteReady || gates.openhandsReady || gates.directPatchReady) {
    return { canConfirm: true };
  }

  // No write path available
  return {
    canConfirm: false,
    blocker: gates.blockerMessage || 'Kein Ausführungspfad verfügbar. Executor oder GitHub-Zugang erforderlich.',
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
      const draft = createIntegrationIntentDraft(action.input, repoFiles);
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

// ─────────────────────────────────────────────────────────────
// ACTION EVENT BUILDERS
// ─────────────────────────────────────────────────────────────

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
    label: 'Integrationsauftrag bestätigt',
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

// ─────────────────────────────────────────────────────────────
// INITIAL STATE
// ─────────────────────────────────────────────────────────────

export function createInitialDraftState(): IntegrationIntentDraftState {
  return { status: 'idle' };
}

// ─────────────────────────────────────────────────────────────
// QUERY HELPERS
// ─────────────────────────────────────────────────────────────

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
