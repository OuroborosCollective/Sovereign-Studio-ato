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
  'übernimm das',
  'kannst du das für mich',
  'mach das für mich',
];

// Code/repo context tokens that make delegation meaningful
const CODE_CONTEXT_TOKENS = [
  'readme', 'datei', 'code', 'patch', 'commit', 'pr', 'pull request',
  'draft', 'repo', 'repository', 'github', 'build', 'bau', 'implementier',
  'fix', 'fehler', 'bug', 'feature', 'änderung', 'aktualisier', 'update',
  'lösche', 'entfern', 'ergänz', 'füge hinzu', 'ersetze', 'schreibe',
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
