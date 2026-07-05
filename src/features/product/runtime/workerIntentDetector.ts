/**
 * Worker Intent Detector - Runtime module for Worker message routing
 *
 * Extracts and exports Worker-specific intent detection logic.
 * Used by BuilderContainer and can be unit tested directly.
 */

// German + English keywords for intent detection.
// Sovereign is not a generic chatbot inside a connected repository. A normal
// non-question message is treated as an implementation/integration request by
// default, unless it is clearly repo loading, status, retry, diagnostic, or a
// small-talk/greeting phrase. Questions still stay advisory, but the Worker
// prompt must answer them as repo-specific integration guidance.
const OPENHANDS_EXECUTION_TOKENS = [
  'openhands', 'draft pr', 'draft-pr', 'pull request', 'pr erstellen',
  'push', 'commit', 'repo schreiben', 'github schreiben', 'branch erstellen',
];

const CODE_GENERATION_TOKENS = [
  'baue', 'bauen', 'implementiere', 'implementieren', 'fixe', 'repariere',
  'patch', 'ändere datei', 'datei ändern', 'ersatzdatei', 'runtime-check',
  'tests ergänzen', 'test ergänzen', 'code ändern', 'feature einbauen',
  'schreibe code', 'code schreiben', 'integration', 'integriere',
  'einbauen', 'umsetzen', 'umsetzung', 'stabilisiere', 'härte', 'haerte',
];

const WORKER_RETRY_TOKENS = ['retry', 'erneut', 'nochmal', 'noch mal', 'wiederholen', 'testen', 'versuch'];

const WORKER_DIAGNOSTIC_TOKENS = [
  'warum', 'wieso', 'weshalb', 'hilfe', 'hilf', 'help', 'erklär', 'erklaer',
  'diagnose', 'fehler', '500', 'worker', 'cloudflare', 'blockiert', 'kaputt',
];

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

// Alternative write route tokens: user explicitly asks NOT to use OpenHands
const ALTERNATIVE_WRITE_ROUTE_TOKENS = [
  'nicht openhands',
  'ohne openhands',
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

// Executor status question tokens: user asks if/what the executor is doing
const EXECUTOR_STATUS_TOKENS = [
  'arbeitet er schon',
  'läuft das',
  'läuft er',
  'was macht er',
  'sehe nichts bei replit',
  'status?',
  'ist er fertig',
  'hat er angefangen',
  'warum passiert nichts',
  'macht er was',
  'tut er was',
  'ist er gestartet',
  'passiert etwas',
  'passiert gerade',
];

// Code/repo context tokens that make delegation meaningful
const CODE_CONTEXT_TOKENS = [
  'readme', 'datei', 'code', 'patch', 'commit', 'pr', 'pull request',
  'draft', 'repo', 'repository', 'github', 'build', 'bau', 'implementier',
  'fix', 'fehler', 'bug', 'feature', 'änderung', 'aktualisier', 'update',
  'lösche', 'entfern', 'ergänz', 'füge hinzu', 'ersetze', 'schreibe',
  'test', 'tests', 'hinzufüg', 'ergänz', 'integrationsauftrag',
  'integration', 'runtime', 'route', 'router', 'workflow', 'executor',
  'openhands', 'draft pr', 'einbauen', 'umsetzen', 'umsetzung',
];

const GREETING_OR_SMALLTALK_TOKENS = [
  'hallo', 'hi', 'hello', 'hey', 'guten morgen', 'guten tag', 'danke',
  'thanks', 'thank you', 'wie geht es dir', 'how are you',
];

function hasAnyToken(text: string, tokens: readonly string[]): boolean {
  const lower = text.toLowerCase();
  return tokens.some((token) => lower.includes(token));
}

function isGithubRepoUrl(text: string): boolean {
  return /^https?:\/\/github\.com\/[\w-]+\/[\w.-]+(?:\/.*)?$/i.test(text.trim());
}

function isQuestionText(text: string): boolean {
  return /\?\s*$/.test(text.trim());
}

/**
 * Runtime default: inside this product, a non-question user sentence is presumed
 * to be a repository integration request, not advice/small talk. This function
 * deliberately stays conservative around questions, status checks, retry,
 * diagnostics and greetings so those routes remain honest.
 */
export function isLikelyIntegrationImplementationIntent(text: string): boolean {
  const clean = text.trim();
  if (clean.length < 4) return false;
  if (clean.startsWith('/')) return false;
  if (isGithubRepoUrl(clean)) return false;
  if (isQuestionText(clean)) return false;
  if (hasAnyToken(clean, GREETING_OR_SMALLTALK_TOKENS)) return false;
  if (hasAnyToken(clean, EXECUTOR_STATUS_TOKENS)) return false;
  if (hasAnyToken(clean, WORKER_RETRY_TOKENS)) return false;
  if (hasAnyToken(clean, ALTERNATIVE_WRITE_ROUTE_TOKENS)) return false;
  return true;
}

/**
 * Detects if a message is an OpenHands execution intent.
 * These messages should trigger the OpenHands executor.
 */
export function isOpenHandsExecutionIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return OPENHANDS_EXECUTION_TOKENS.some((token) => lower.includes(token)) ||
    isLikelyIntegrationImplementationIntent(text);
}

/**
 * Detects code-generation work that should go to code-capable LLM routes
 * before any external executor is considered.
 */
export function isCodeGenerationIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return CODE_GENERATION_TOKENS.some((token) => lower.includes(token)) ||
    isLikelyIntegrationImplementationIntent(text);
}

/**
 * Detects if a message is a Worker retry intent.
 * These messages should trigger a retry of the failed Worker request.
 */
export function isWorkerRetryIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return WORKER_RETRY_TOKENS.some((token) => lower.includes(token));
}

/**
 * Detects if a message is a Worker diagnostic question.
 * These messages should get a local diagnostic answer without retry.
 */
export function isWorkerDiagnosticQuestion(text: string): boolean {
  const lower = text.toLowerCase();
  return WORKER_DIAGNOSTIC_TOKENS.some((token) => lower.includes(token));
}

/**
 * Detects delegation/confirmation intent without blindly starting OpenHands.
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
  return OPENHANDS_EXECUTION_TOKENS.some((token) => allText.includes(token)) ||
    allText.includes('integrationsauftrag') ||
    allText.includes('integration') ||
    allText.includes('einbauen') ||
    allText.includes('umsetzung');
}

export function isDelegatedOpenHandsExecutionIntent(
  text: string,
  recentMessages: readonly { role: string; text: string }[],
): boolean {
  if (!isDelegationIntent(text)) return false;
  return hasExecutorContextInHistory(recentMessages);
}

/**
 * Detects if a message is explicitly asking for an alternative write route
 * instead of OpenHands. These must be answered locally from runtime state,
 * not forwarded to OpenHands or Worker.
 * 
 * Examples:
 * - "Nutzen wir eine andere Route und nicht OpenHands"
 * - "Kannst du direkt über GitHub patchen ohne Executor?"
 * - "Alternative Route für diesen einfachen Patch?"
 */
export function isAlternativeWriteRouteIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return ALTERNATIVE_WRITE_ROUTE_TOKENS.some((token) => lower.includes(token));
}

/**
 * Detects if a message is asking about the current executor/OpenHands status.
 * These messages should be answered locally from agentWorkSnapshot, not sent to Worker.
 */
export function isExecutorStatusQuestion(text: string): boolean {
  const lower = text.toLowerCase();
  return EXECUTOR_STATUS_TOKENS.some((token) => lower.includes(token));
}

export type ExecutorStatusArgs = {
  readonly agentState: string;
  readonly openhandsStatus?: string;
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
  const { agentState, openhandsStatus, changedFiles = 0, draftPrUrl, blockerReason } = args;

  if (agentState === 'idle' && (!openhandsStatus || openhandsStatus === 'idle')) {
    return 'Nein, OpenHands läuft noch nicht.\nKein Auftrag wurde gestartet.';
  }
  if (agentState === 'executor_running' || openhandsStatus === 'running') {
    const fileInfo = changedFiles > 0
      ? `Geänderte Dateien bisher: ${changedFiles}.`
      : 'Geänderte Dateien bisher: 0.';
    const prInfo = draftPrUrl ? 'Draft PR: wird vorbereitet.' : 'Draft PR: noch nicht bereit.';
    return `Ja, OpenHands läuft.\n${fileInfo}\n${prInfo}`;
  }
  if (agentState === 'executor_starting' || openhandsStatus === 'queued') {
    return 'OpenHands wird gestartet. Warte auf erste Rückmeldung.';
  }
  if (agentState === 'blocked' || openhandsStatus === 'blocked') {
    const reason = blockerReason || 'Kein Grund angegeben.';
    // #500: Fix next action based on actual blocker type
    const nextAction = reason.includes('GitHub')
      ? 'Sicheren GitHub-Zugang öffnen.'
      : 'OpenHands konfigurieren oder Direct GitHub Patch Route nutzen.';
    return `Nein, OpenHands läuft nicht.\nStatus: blockiert.\nGrund: ${reason}\nNächste Aktion: ${nextAction}`;
  }
  if (agentState === 'failed' || openhandsStatus === 'failed') {
    const reason = blockerReason || 'OpenHands Executor fehlgeschlagen.';
    return `Nein, OpenHands ist fehlgeschlagen.\nGrund: ${reason}`;
  }
  if (agentState === 'draft_pr_ready' || openhandsStatus === 'completed') {
    return draftPrUrl
      ? `OpenHands hat einen Draft PR erstellt: ${draftPrUrl}`
      : 'OpenHands ist fertig. Draft PR wurde erstellt.';
  }
  if (agentState === 'intent_detected' || agentState === 'access_required') {
    // #500: Report GitHub access as required only when it's actually the blocker
    const isGithubBlocker = blockerReason && blockerReason.includes('GitHub');
    if (isGithubBlocker) {
      return 'Auftrag erkannt. OpenHands wurde noch nicht gestartet.\nGrund: GitHub-Schreibzugang erforderlich.\nNächste Aktion: Sicheren GitHub-Zugang öffnen.';
    }
    return 'Auftrag erkannt. OpenHands wurde noch nicht gestartet.\nGrund: Executor nicht bereit.\nNächste Aktion: OpenHands konfigurieren oder Direct GitHub Patch Route nutzen.';
  }
  return 'Executor-Status wird ermittelt. Bitte kurz warten.';
}

/**
 * Blocker types for write intents when GitHub is ready but executor is not available.
 * Used to distinguish between GitHub access issues and executor capability issues.
 */
export type WriteRouteBlockerType = 
  | 'github_access_required'   // GitHub access not yet ready
  | 'executor_unavailable'      // OpenHands not configured
  | 'patch_route_unavailable';  // Alternative patch route not available

/**
 * Builds a truthful local answer for alternative write route questions.
 * Must NOT claim GitHub access is missing when it is ready.
 * Must correctly identify the actual blocker type.
 */
export function buildAlternativeRouteStatusAnswer(args: {
  readonly githubAccessReady: boolean;
  readonly githubAccessState?: string;
  readonly openhandsReady: boolean;
  readonly directPatchAvailable: boolean;
}): string {
  const { githubAccessReady, githubAccessState, openhandsReady, directPatchAvailable } = args;

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

  // GitHub is ready, but OpenHands is not configured
  if (!openhandsReady && !directPatchAvailable) {
    return [
      'GitHub-Zugang ist bereit.',
      'OpenHands ist nicht konfiguriert.',
      'Für einfache README-/Docs-Änderungen könnte eine Direct GitHub Patch Route genutzt werden, wenn verfügbar.',
      'Für große Multi-Datei-/Test-Aufträge braucht es einen Workspace-Executor.',
      'Nächste Aktion: OpenHands konfigurieren oder Direct GitHub Patch Runtime aktivieren.',
    ].join('\n');
  }

  if (!openhandsReady && directPatchAvailable) {
    return [
      'GitHub-Zugang ist bereit.',
      'OpenHands ist nicht konfiguriert.',
      'Direct GitHub Patch Route ist verfügbar für einfache Änderungen.',
      'Für große Multi-Datei-/Test-Aufträge braucht es einen Workspace-Executor.',
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
  if (isOpenHandsExecutionIntent(clean)) {
    return args.agentDisabled
      ? 'Executor blockiert · Code-Route prüft zuerst'
      : 'Executor-Schreibroute starten';
  }
  if (isCodeGenerationIntent(clean)) {
    return 'Code-LLM Route · Patch erzeugen';
  }
  if (args.workerBlocked && !isWorkerRetryIntent(clean)) {
    return 'Worker blockiert · lokale Diagnose statt blindem Retry';
  }
  if (args.workerBlocked && isWorkerRetryIntent(clean)) {
    return 'Worker Retry · Diagnose wird aktualisiert';
  }
  return '';
}
