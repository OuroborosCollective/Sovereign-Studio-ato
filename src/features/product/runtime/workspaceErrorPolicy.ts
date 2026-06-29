/**
 * Workspace Error Policy
 *
 * Classifies and handles errors from the agent workspace runtime.
 * Follows the Sovereign error handling rule:
 * - Failures must route into a repair flow, not into blind retry loops
 * - Record error result, classified state, safe next action, repair mission
 *
 * This is NOT an ErrorBoundary (React component) - it's a pure runtime
 * error classification system for workspace operations.
 */

import type { AgentWorkspaceResult, AgentWorkspaceStatus } from './agentWorkspaceRuntime';

/** Error severity classification */
export type WorkspaceErrorSeverity = 'fatal' | 'blocked' | 'warning' | 'info';

/** Workspace error classification categories */
export type WorkspaceErrorKind =
  | 'validation-failed'
  | 'executor-not-ready'
  | 'backend-unavailable'
  | 'network-error'
  | 'timeout'
  | 'cleanup-failed'
  | 'secret-detected'
  | 'invalid-repo'
  | 'workspace-occupied'
  | 'unknown';

export interface WorkspaceErrorClass {
  kind: WorkspaceErrorKind;
  severity: WorkspaceErrorSeverity;
  retryable: boolean;
  repairHint: string;
}

/**
 * Classify a workspace result's blocker into an error category.
 * Returns the error classification for routing to repair flow.
 */
export function classifyWorkspaceError(result: AgentWorkspaceResult): WorkspaceErrorClass {
  const blocker = result.blocker?.toLowerCase() ?? '';
  const workspaceId = result.workspaceId ?? '';

  // Validation failures
  if (blocker.includes('valid https github') || blocker.includes('invalid') && blocker.includes('url')) {
    return {
      kind: 'invalid-repo',
      severity: 'blocked',
      retryable: false,
      repairHint: 'Prüfe die GitHub Repository URL. Muss mit https://github.com/ beginnen.',
    };
  }

  if (blocker.includes('secret-like') || blocker.includes('secret')) {
    return {
      kind: 'secret-detected',
      severity: 'fatal',
      retryable: false,
      repairHint: 'Request enthält geheime Werte. Bitte entferne Tokens und API-Keys aus der Aufgabe.',
    };
  }

  // Executor errors
  if (blocker.includes('executor') && (blocker.includes('not ready') || blocker.includes('disabled') || blocker.includes('not supported'))) {
    return {
      kind: 'executor-not-ready',
      severity: 'blocked',
      retryable: true,
      repairHint: 'OpenHands Executor ist nicht bereit. Prüfe die OpenHands Konfiguration.',
    };
  }

  if (blocker.includes('backend') && (blocker.includes('not ready') || blocker.includes('disabled') || blocker.includes('available'))) {
    return {
      kind: 'backend-unavailable',
      severity: 'blocked',
      retryable: true,
      repairHint: 'OpenHands Backend ist nicht verfügbar. Prüfe die Netzwerkverbindung.',
    };
  }

  if (blocker.includes('timeout') || blocker.includes('timed out')) {
    return {
      kind: 'timeout',
      severity: 'warning',
      retryable: true,
      repairHint: 'Workspace Timeout. Erhöhe maxRuntimeMs oder prüfe die Aufgabe.',
    };
  }

  if (blocker.includes('network') || blocker.includes('connection') || blocker.includes('fetch')) {
    return {
      kind: 'network-error',
      severity: 'warning',
      retryable: true,
      repairHint: 'Netzwerkfehler. Prüfe die Internetverbindung und GitHub Erreichbarkeit.',
    };
  }

  if (blocker.includes('cleanup') || blocker.includes('bereinig')) {
    return {
      kind: 'cleanup-failed',
      severity: 'warning',
      retryable: false,
      repairHint: 'Workspace Bereinigung fehlgeschlagen. Manueller Eingriff erforderlich.',
    };
  }

  if (workspaceId.startsWith('blocked-') || blocker.includes('validation')) {
    return {
      kind: 'validation-failed',
      severity: 'blocked',
      retryable: false,
      repairHint: 'Request Validierung fehlgeschlagen. Bitte prüfe die Eingabewerte.',
    };
  }

  if (blocker.includes('already') && blocker.includes('running')) {
    return {
      kind: 'workspace-occupied',
      severity: 'blocked',
      retryable: false,
      repairHint: 'Ein Workspace läuft bereits. Warte bis er abgeschlossen ist oder bereinige ihn.',
    };
  }

  // Default unknown error
  return {
    kind: 'unknown',
    severity: result.status === 'failed' ? 'warning' : 'info',
    retryable: result.status !== 'failed',
    repairHint: blocker ? `Blocker: ${blocker.slice(0, 100)}` : 'Unbekannter Fehler. Details im Workspace-Log.',
  };
}

/** Determines the next safe action based on error classification */
export function getWorkspaceErrorNextAction(error: WorkspaceErrorClass): {
  action: 'none' | 'retry' | 'fix-input' | 'cleanup' | 'contact-admin';
  label: string;
  blocked: boolean;
} {
  if (error.kind === 'secret-detected' || error.kind === 'invalid-repo') {
    return { action: 'fix-input', label: 'Eingabe korrigieren', blocked: true };
  }

  if (error.kind === 'workspace-occupied') {
    return { action: 'cleanup', label: 'Workspace bereinigen', blocked: true };
  }

  if (error.kind === 'executor-not-ready' || error.kind === 'backend-unavailable') {
    return { action: 'contact-admin', label: 'Konfiguration prüfen', blocked: true };
  }

  if (error.retryable) {
    return { action: 'retry', label: 'Erneut versuchen', blocked: false };
  }

  return { action: 'none', label: 'Manuelle Prüfung erforderlich', blocked: true };
}

/**
 * Safe reducer for workspace status transitions.
 * Prevents invalid state transitions and logs violations.
 * 
 * Note: 'idle' is handled as 'no active workspace' - cleaned → queued starts fresh workspace.
 */
export function safeWorkspaceStatusTransition(
  current: AgentWorkspaceStatus | 'idle',
  next: AgentWorkspaceStatus | 'idle',
): { valid: boolean; safeNext: AgentWorkspaceStatus | 'idle' } {
  // Define valid transitions (idle = no active workspace)
  const validTransitions: Record<string, (AgentWorkspaceStatus | 'idle')[]> = {
    idle: ['queued'],
    queued: ['running', 'blocked', 'failed'],
    running: ['completed', 'failed', 'blocked'],
    completed: ['cleaned'],
    failed: ['cleaned', 'queued'], // allow retry
    blocked: ['cleaned', 'queued'], // allow retry
    cleaned: ['queued'], // allow new workspace (starts fresh)
  };

  const allowed = validTransitions[current] ?? [];
  const isValid = allowed.includes(next);

  if (!isValid) {
    console.warn(
      `[WorkspaceErrorPolicy] Invalid status transition: ${current} → ${next}. Allowed: ${allowed.join(', ') || 'none'}`,
    );
    // Fall back to a safe state instead of crashing
    return { valid: false, safeNext: current };
  }

  return { valid: true, safeNext: next };
}
