/**
 * Worker Intent Detector - Runtime module for Worker message routing
 *
 * Extracts and exports Worker-specific intent detection logic.
 * Used by BuilderContainer and can be unit tested directly.
 */

// German + English keywords for intent detection
const WORKER_EXECUTION_TOKENS = [
  'openhands', 'draft pr', 'pull request', 'pr erstellen', 'push', 'commit',
  'baue', 'bauen', 'implementiere', 'implementieren', 'fixe', 'repariere',
  'patch', 'ändere datei', 'datei ändern', 'ersatzdatei', 'runtime-check',
  'tests ergänzen', 'test ergänzen', 'code ändern', 'repo schreiben',
];

const WORKER_RETRY_TOKENS = ['retry', 'erneut', 'nochmal', 'noch mal', 'wiederholen', 'testen', 'versuch'];

const WORKER_DIAGNOSTIC_TOKENS = [
  'warum', 'wieso', 'weshalb', 'hilfe', 'hilf', 'help', 'erklär', 'erklaer',
  'diagnose', 'fehler', '500', 'worker', 'cloudflare', 'blockiert', 'kaputt',
];

// Delegation tokens: explicit handover to executor
const DELEGATION_TOKENS = [
  'tu du das',
  'mach das',
  'mach du das',
  'erledige das',
  'setze das um',
  'setz das um',
  'übernimm das',
  'kannst du das für mich',
  'mach das für mich',
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
  'test', 'tests', 'hinzufüg', 'ergänz',
];

/**
 * Detects if a message is an OpenHands execution intent.
 * These messages should trigger the OpenHands executor.
 */
export function isOpenHandsExecutionIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return WORKER_EXECUTION_TOKENS.some((token) => lower.includes(token));
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
 * Detects delegation intent ("Tu du das für mich") without blindly starting OpenHands.
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
export function isDelegatedOpenHandsExecutionIntent(
  text: string,
  recentMessages: readonly { role: string; text: string }[],
): boolean {
  if (!isDelegationIntent(text)) return false;
  return hasCodeContextInHistory(recentMessages);
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
    return `Nein, OpenHands läuft nicht.\nStatus: blockiert.\nGrund: ${reason}\nNächste Aktion: Sicheren GitHub-Zugang öffnen.`;
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
    return 'Auftrag erkannt. OpenHands wurde noch nicht gestartet.\nGrund: GitHub-Schreibzugang erforderlich.';
  }
  return 'Executor-Status wird ermittelt. Bitte kurz warten.';
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
      ? 'OpenHands blockiert · Worker erklärt zuerst'
      : 'OpenHands Executor starten';
  }
  if (args.workerBlocked && !isWorkerRetryIntent(clean)) {
    return 'Worker blockiert · lokale Diagnose statt blindem Retry';
  }
  if (args.workerBlocked && isWorkerRetryIntent(clean)) {
    return 'Worker Retry · Diagnose wird aktualisiert';
  }
  return '';
}
