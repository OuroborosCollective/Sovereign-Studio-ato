/**
 * Worker Intent Detector - Runtime module for Worker message routing
 *
 * Extracts and exports Worker-specific intent detection logic.
 * Used by BuilderContainer and can be unit tested directly.
 */

// Free language belongs to the online LLM. These legacy context tokens are used
// only after an explicit machine control such as /confirm; they must never decide
// the route of a fresh natural-language message.
const SOVEREIGN_AGENT_EXECUTION_TOKENS = [
  'sovereign agent', 'sovereign-agent', 'sovereign_agent', 'draft pr', 'draft-pr', 'pull request', 'pr erstellen',
  'push', 'commit', 'repo schreiben', 'github schreiben', 'branch erstellen',
];

const EXACT_CODE_COMMANDS = ['/code', '/fix', '/implement'] as const;
const EXACT_AGENT_COMMANDS = ['/agent', '/draft-pr'] as const;
const EXACT_RETRY_COMMANDS = ['retry', '/retry'] as const;
const EXACT_DIAGNOSTIC_COMMANDS = ['diagnose', '/diagnose'] as const;
const EXACT_STATUS_COMMANDS = ['/status'] as const;

// Delegation tokens: explicit handover to executor. Includes the confirmation
// vocabulary emitted by the Integration-Draft UX: user confirms by saying
// "Einbauen", "Ja einbauen", "Übernehmen", etc.
const DELEGATION_TOKENS = [
  'tu du das',
  'mach das',
  'mach du das',
  'erledige das',
  'setze das um',
  'setz das um',
  'übernimm das',
  'uebernimm das',
  'kannst du das für mich',
  'mach das für mich',
  'einbauen',
  'ja einbauen',
  'bitte einbauen',
  'übernehmen',
  'uebernehmen',
  'bestätigen',
  'bestaetigen',
  'freigeben',
];

// Alternative write route tokens: user explicitly asks NOT to use Sovereign Agent
const ALTERNATIVE_WRITE_ROUTE_TOKENS = [
  'nicht sovereign agent',
  'nicht sovereign-agent',
  'ohne sovereign agent',
  'ohne sovereign-agent',
  'andere route',
  'alternative route',
  'direkt über github',
  'direkt ueber github',
  'direkt patchen',
  'github patch route',
  'ohne executor',
  'ohne agent',
  'einfache route',
  'simple route',
  'github direkt',
];

// Code/repo context tokens that make delegation meaningful
const CODE_CONTEXT_TOKENS = [
  'readme', 'datei', 'code', 'patch', 'commit', 'pr', 'pull request',
  'draft', 'repo', 'repository', 'github', 'build', 'bau', 'implementier',
  'fix', 'fehler', 'bug', 'feature', 'änderung', 'aktualisier', 'update',
  'lösche', 'entfern', 'ergänz', 'füge hinzu', 'ersetze', 'schreibe',
  'test', 'tests', 'hinzufüg', 'ergänz', 'integrationsauftrag',
  'integration', 'runtime', 'route', 'router', 'workflow', 'executor',
  'sovereign agent', 'sovereign-agent', 'draft pr', 'einbauen', 'umsetzen', 'umsetzung',
];

/**
 * Free language is never presumed to be an implementation request.
 * The online LLM must return structured intent evidence; offline runtime stays
 * fail-closed and only accepts explicit controls in the dedicated helpers below.
 */
export function isLikelyIntegrationImplementationIntent(_text: string): boolean {
  return false;
}

/**
 * Detects if a message is an explicit Sovereign Agent execution intent.
 * Generic implementation text stays code-route until a confirmed executor handoff.
 */
export function isSovereignAgentExecutionIntent(text: string): boolean {
  const command = text.trim().toLowerCase().split(/\s+/, 1)[0];
  return EXACT_AGENT_COMMANDS.some((candidate) => candidate === command);
}

/**
 * Detects code-generation work that should go to code-capable LLM routes
 * before any external executor is considered.
 */
export function isCodeGenerationIntent(text: string): boolean {
  const command = text.trim().toLowerCase().split(/\s+/, 1)[0];
  return EXACT_CODE_COMMANDS.some((candidate) => candidate === command);
}

/**
 * Detects if a message is a Worker retry intent.
 * These messages should trigger a retry of the failed Worker request.
 */
export function isWorkerRetryIntent(text: string): boolean {
  const clean = text.trim().toLowerCase();
  return EXACT_RETRY_COMMANDS.some((candidate) => candidate === clean);
}

/**
 * Detects if a message is a Worker diagnostic question.
 * These messages should get a local diagnostic answer without retry.
 */
export function isWorkerDiagnosticQuestion(text: string): boolean {
  const clean = text.trim().toLowerCase();
  return EXACT_DIAGNOSTIC_COMMANDS.some((candidate) => candidate === clean);
}

/**
 * Detects delegation/confirmation intent without blindly starting Sovereign Agent.
 * Only qualifies as execution intent if there's prior code/repo context.
 */
export function isDelegationIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return DELEGATION_TOKENS.some((token) => lower.includes(token));
}

/**
 * Checks if recent chat context contains code/repo-related content.
 * Used to determine if a delegation intent should trigger executor.
 */
export function hasCodeContextInHistory(recentMessages: readonly { role: string; text: string }[]): boolean {
  const relevant = recentMessages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .slice(-6); // last 6 messages

  const allText = relevant.map((m) => m.text.toLowerCase()).join(' ');

  return CODE_CONTEXT_TOKENS.some((token) => allText.includes(token));
}

/**
 * Combined check: delegation intent + code context = executor candidate.
 * Use this in BuilderContainer routing instead of just isDelegationIntent.
 */
export function hasExecutorContextInHistory(recentMessages: readonly { role: string; text: string }[]): boolean {
  const relevant = recentMessages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .slice(-6);
  const allText = relevant.map((m) => m.text.toLowerCase()).join(' ');
  return SOVEREIGN_AGENT_EXECUTION_TOKENS.some((token) => allText.includes(token)) ||
    allText.includes('integrationsauftrag') ||
    allText.includes('integration') ||
    allText.includes('einbauen') ||
    allText.includes('umsetzung');
}

export function isDelegatedSovereignAgentExecutionIntent(
  text: string,
  recentMessages: readonly { role: string; text: string }[],
): boolean {
  if (!isDelegationIntent(text)) return false;
  return hasExecutorContextInHistory(recentMessages);
}

/**
 * Detects if a message is explicitly asking for an alternative write route
 * instead of Sovereign Agent. These must be answered locally from runtime state,
 * not forwarded to Sovereign Agent or Worker.
 * 
 * Examples:
 * - "Nutzen wir eine andere Route und nicht Sovereign Agent"
 * - "Kannst du direkt über GitHub patchen ohne Executor?"
 * - "Alternative Route für diesen einfachen Patch?"
 */
export function isAlternativeWriteRouteIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return ALTERNATIVE_WRITE_ROUTE_TOKENS.some((token) => lower.includes(token));
}

/**
 * Detects if a message is asking about the current executor/Sovereign Agent status.
 * These messages should be answered locally from agentWorkSnapshot, not sent to Worker.
 */
export function isExecutorStatusQuestion(text: string): boolean {
  const clean = text.trim().toLowerCase();
  return EXACT_STATUS_COMMANDS.some((candidate) => candidate === clean);
}

export type ExecutorStatusArgs = {
  readonly agentState: string;
  readonly agentStatus?: string;
  readonly changedFiles?: number;
  readonly draftPrUrl?: string | null;
  readonly blockerReason?: string | null;
};

/**
 * Builds a truthful local answer for executor status questions
 * ("arbeitet er schon?", "läuft das?", etc.) from real runtime state.
 * Never fabricates — empty/idle states are reported honestly.
 * 
 * #500: Fix next action based on actual missing capability, not GitHub access.
 */
export function buildExecutorStatusAnswer(args: ExecutorStatusArgs): string {
  const { agentState, agentStatus, changedFiles = 0, draftPrUrl, blockerReason } = args;

  if (agentState === 'idle' && (!agentStatus || agentStatus === 'idle')) {
    return 'Nein, Sovereign Agent läuft noch nicht.\nKein Auftrag wurde gestartet.';
  }
  if (agentState === 'executor_running' || agentStatus === 'running') {
    const fileInfo = changedFiles > 0
      ? `Geänderte Dateien bisher: ${changedFiles}.`
      : 'Geänderte Dateien bisher: 0.';
    const prInfo = draftPrUrl ? 'Draft PR: wird vorbereitet.' : 'Draft PR: noch nicht bereit.';
    return `Ja, Sovereign Agent läuft.\n${fileInfo}\n${prInfo}`;
  }
  if (agentState === 'executor_starting' || agentStatus === 'queued') {
    return 'Sovereign Agent wird gestartet. Warte auf erste Rückmeldung.';
  }
  if (agentState === 'blocked' || agentStatus === 'blocked') {
    const reason = blockerReason || 'Kein Grund angegeben.';
    // #500: Fix next action based on actual blocker type
    const nextAction = reason.includes('GitHub')
      ? 'Sicheren GitHub-Zugang öffnen.'
      : 'Sovereign Agent Backend und isolierten Workspace verbinden.';
    return `Nein, Sovereign Agent läuft nicht.\nStatus: blockiert.\nGrund: ${reason}\nNächste Aktion: ${nextAction}`;
  }
  if (agentState === 'failed' || agentStatus === 'failed') {
    const reason = blockerReason || 'Sovereign Agent Runtime fehlgeschlagen.';
    return `Nein, Sovereign Agent ist fehlgeschlagen.\nGrund: ${reason}`;
  }
  if (agentState === 'draft_pr_ready') {
    return draftPrUrl
      ? `Sovereign Agent hat einen Draft PR erstellt: ${draftPrUrl}`
      : 'Sovereign Agent meldet Draft-PR-Ready, aber keine Draft-PR-URL liegt vor. Ergebnis noch nicht belegbar.';
  }
  if (agentStatus === 'completed') {
    return draftPrUrl
      ? `Sovereign Agent hat einen Draft PR erstellt: ${draftPrUrl}`
      : 'Sovereign Agent meldet completed, aber keine Draft-PR-URL liegt vor. Ergebnis noch nicht belegbar.';
  }
  if (agentState === 'intent_detected' || agentState === 'access_required') {
    // #500: Report GitHub access as required only when it's actually the blocker
    const isGithubBlocker = blockerReason && blockerReason.includes('GitHub');
    if (isGithubBlocker) {
      return 'Auftrag erkannt. Sovereign Agent wurde noch nicht gestartet.\nGrund: GitHub-Schreibzugang erforderlich.\nNächste Aktion: Sicheren GitHub-Zugang öffnen.';
    }
    return 'Auftrag erkannt. Sovereign Agent wurde noch nicht gestartet.\nGrund: Executor nicht bereit.\nNächste Aktion: Sovereign Agent Backend und isolierten Workspace verbinden.';
  }
  return 'Executor-Status wird ermittelt. Bitte kurz warten.';
}

/**
 * Blocker types for write intents when GitHub is ready but executor is not available.
 * Used to distinguish between GitHub access issues and executor capability issues.
 */
export type WriteRouteBlockerType = 
  | 'github_access_required'   // GitHub access not yet ready
  | 'executor_unavailable'      // Sovereign Agent not configured
  | 'patch_route_unavailable';  // Alternative patch route not available

/**
 * Builds a truthful local answer for alternative write route questions.
 * Must NOT claim GitHub access is missing when it is ready.
 * Must correctly identify the actual blocker type.
 */
export function buildAlternativeRouteStatusAnswer(args: {
  readonly githubAccessReady: boolean;
  readonly githubAccessState?: string;
  readonly agentReady: boolean;
  readonly directPatchAvailable: boolean;
}): string {
  const { githubAccessReady, githubAccessState, agentReady, directPatchAvailable } = args;

  // GitHub access not ready — report this truthfully
  if (!githubAccessReady) {
    if (githubAccessState === 'validating') {
      return 'Der GitHub-Zugang wird gerade geprüft. Bitte warten.';
    }
    if (githubAccessState === 'requested') {
      return 'Der GitHub-Zugang wurde nur im Format akzeptiert. Die echte GitHub-API-Prüfung steht noch aus.';
    }
    return 'GitHub-Zugang fehlt. Bitte zuerst sicheren GitHub-Zugang einrichten.';
  }

  // GitHub is ready, but the Sovereign Agent backend is not configured
  if (!agentReady && !directPatchAvailable) {
    return [
      'GitHub-Zugang ist bereit.',
      'Sovereign Agent Backend ist nicht verbunden.',
      'Auch einfache README-/Docs-Änderungen müssen über den backend-eigenen isolierten Workspace ausgeführt werden.',
      'Für Multi-Datei-/Test-Aufträge ist derselbe Workspace-Executor erforderlich.',
      'Nächste Aktion: Sovereign Agent Backend und isolierten Workspace verbinden.',
    ].join('\n');
  }

  if (!agentReady && directPatchAvailable) {
    return [
      'GitHub-Zugang ist bereit.',
      'Sovereign Agent Backend ist nicht verbunden.',
      'Der backend-eigene Workspace-Executor ist für einfache Änderungen verfügbar.',
      'Für Multi-Datei-/Test-Aufträge wird derselbe kontrollierte Executor verwendet.',
    ].join('\n');
  }

  return 'Alle Routen sind bereit.';
}

/**
 * Determines the appropriate action hint based on Worker state and message intent.
 */
export function getWorkerActionHint(args: {
  readonly submittedText: string;
  readonly workerBlocked: boolean;
  readonly agentDisabled?: boolean;
}): string {
  const clean = args.submittedText.trim();
  if (isSovereignAgentExecutionIntent(clean)) {
    return args.agentDisabled
      ? 'Executor blockiert · Code-Route prüft zuerst'
      : 'Executor-Schreibroute starten';
  }
  if (isCodeGenerationIntent(clean)) {
    return 'Code-LLM Route · Patch erzeugen';
  }
  if (args.workerBlocked && !isWorkerRetryIntent(clean)) {
    return 'Worker blockiert · keine lokale Sprachdeutung';
  }
  if (args.workerBlocked && isWorkerRetryIntent(clean)) {
    return 'Worker Retry · Diagnose wird aktualisiert';
  }
  return '';
}
