import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';
import type { SolutionPatternLearningInput } from './solutionPatternMemory';

/**
 * OpenHands Pattern Gateway Bridge
 *
 * Guards the learning flow from OpenHands job results to Pattern Memory.
 *
 * Architecture rules enforced:
 * - OpenHands is executor, not truth source
 * - Sovereign Runtime decides preconditions, context, memory intake, result display
 * - Pattern Gateway validates every new learning pattern
 * - No direct unvalidated write access to Remote Memory
 * - No Auto-Merge, no Plan-only Draft PR, no Secrets in logs/preview/memory
 */

export type OpenHandsResultType = 'idle' | 'running' | 'success' | 'blocker' | 'empty' | 'plan-only';

export interface OpenHandsPatternIntakeInput {
  mission: string;
  snapshot: OpenHandsJobSnapshot;
  providerId?: string;
  now?: number;
}

/**
 * Validates that an OpenHands result represents a real outcome.
 * Only actual changed files, diff, or draft PR counts as a valid result.
 */
export function classifyOpenHandsResult(snapshot: OpenHandsJobSnapshot): OpenHandsResultType {
  if (snapshot.status === 'idle' || snapshot.status === 'queued' || snapshot.status === 'running' || snapshot.status === 'waiting-for-user') {
    return 'running';
  }

  if (snapshot.status === 'blocked') {
    return 'blocker';
  }

  if (snapshot.status === 'failed') {
    return 'blocker';
  }

  // Terminal status: check for real content
  const hasChangedFiles = snapshot.changedFiles && snapshot.changedFiles.length > 0;
  const hasDraftPr = Boolean(snapshot.draftPrUrl);
  const hasResult = hasChangedFiles || hasDraftPr;

  if (!hasResult) {
    return 'empty';
  }

  // Check if the result is plan-only (only docs or config files changed)
  const significantFiles = snapshot.changedFiles.filter((file) => {
    const lower = file.toLowerCase();
    return !lower.endsWith('.md') &&
      !lower.endsWith('.txt') &&
      !lower.endsWith('.json') &&
      !lower.includes('/docs/') &&
      !lower.includes('/doc/');
  });

  if (significantFiles.length === 0 && hasResult) {
    return 'plan-only';
  }

  return 'success';
}

/**
 * Result gate: Only real changedFiles/Diff/Draft PR or clear blocker counts as result.
 * Plan-only results are rejected from intake.
 */
export interface OpenHandsResultGate {
  allowed: boolean;
  type: OpenHandsResultType;
  summary: string;
  changedFiles: string[];
  draftPrUrl?: string;
  blockerReason?: string;
}

export function gateOpenHandsResult(snapshot: OpenHandsJobSnapshot): OpenHandsResultGate {
  const type = classifyOpenHandsResult(snapshot);

  switch (type) {
    case 'running':
      return {
        allowed: false,
        type,
        summary: 'OpenHands job is still running or waiting.',
        changedFiles: snapshot.changedFiles ?? [],
        draftPrUrl: snapshot.draftPrUrl,
      };

    case 'blocker':
      return {
        allowed: true,
        type,
        summary: snapshot.lastError || 'OpenHands job blocked by a gate.',
        changedFiles: snapshot.changedFiles ?? [],
        blockerReason: snapshot.lastError,
      };

    case 'empty':
      return {
        allowed: false,
        type,
        summary: 'OpenHands job completed but produced no changed files or draft PR.',
        changedFiles: [],
      };

    case 'plan-only':
      return {
        allowed: false,
        type,
        summary: 'OpenHands result contains only documentation/config changes. Plan-only Draft PRs are prohibited.',
        changedFiles: snapshot.changedFiles ?? [],
      };

    case 'success':
      return {
        allowed: true,
        type,
        summary: snapshot.draftPrUrl
          ? `OpenHands produced real changes: ${snapshot.changedFiles.length} file(s), Draft PR created.`
          : `OpenHands produced real changes: ${snapshot.changedFiles.length} file(s).`,
        changedFiles: snapshot.changedFiles ?? [],
        draftPrUrl: snapshot.draftPrUrl,
      };

    default:
      return {
        allowed: false,
        type: 'idle',
        summary: 'Unknown OpenHands job status.',
        changedFiles: [],
      };
  }
}

/**
 * Filter events for UI display.
 * Removes raw OpenHands logs that may contain sensitive data.
 */
export interface FilteredOpenHandsEvent {
  at: number;
  level: 'info' | 'warning' | 'error' | 'success';
  stage: string;
  message: string;
  safe: boolean;
}

export function filterOpenHandsEventsForUI(events: OpenHandsJobSnapshot['events']): FilteredOpenHandsEvent[] {
  if (!Array.isArray(events)) return [];

  return events.map((event): FilteredOpenHandsEvent => {
    // Mark all events as potentially unsafe until filtered
    let safeMessage = event.message;
    let safe = true;

    // Remove potential secret patterns
    const secretPatterns = [
      /token[=:\s]*\S+/gi,
      /password[=:\s]*\S+/gi,
      /credential[=:\s]*\S+/gi,
      /secret[=:\s]*\S+/gi,
      /api[_-]?key[=:\s]*\S+/gi,
      /license[_-]?id[=:\s]*\S+/gi,
    ];

    for (const pattern of secretPatterns) {
      pattern.lastIndex = 0;
      if (pattern.test(safeMessage)) {
        safeMessage = safeMessage.replace(pattern, '[REDACTED]');
        safe = false;
      }
    }

    return {
      at: event.at,
      level: event.level,
      stage: event.stage,
      message: safeMessage,
      safe,
    };
  });
}

/**
 * Build Pattern Learning Input from validated OpenHands result.
 * Only called when gateOpenHandsResult returns allowed: true.
 */
export function buildPatternIntakeFromOpenHands(input: OpenHandsPatternIntakeInput): SolutionPatternLearningInput | null {
  const gate = gateOpenHandsResult(input.snapshot);

  if (!gate.allowed) {
    return null;
  }

  const firstFile = gate.changedFiles[0] ?? 'unknown';

  return {
    intakeNode: 'openhands-runtime',
    processingNode: 'learning-memory',
    outputNodes: ['action-builder', 'generated-file-review', 'learning-memory'],
    problem: {
      category: 'learning-memory',
      severity: gate.type === 'blocker' ? 'high' : 'medium',
      filePath: firstFile,
      description: `OpenHands mission: ${input.mission}`,
      contextPaths: gate.changedFiles,
      contextSignals: [
        `openhands-result:${gate.type}`,
        `changed-files:${gate.changedFiles.length}`,
        gate.draftPrUrl ? 'has-draft-pr' : 'no-draft-pr',
      ],
    },
    fix: {
      summary: gate.summary,
      changedFiles: gate.changedFiles,
      steps: [`OpenHands result type: ${gate.type}`],
      completed: gate.type === 'success',
      proof: gate.draftPrUrl,
    },
    confidence: gate.type === 'success' ? 'completed' : 'inferred',
    tags: ['openhands', 'agent-result', gate.type],
    now: input.now,
  };
}

/**
 * Check if an OpenHands job should trigger pattern learning.
 */
export function shouldLearnFromOpenHands(snapshot: OpenHandsJobSnapshot): boolean {
  const gate = gateOpenHandsResult(snapshot);
  return gate.allowed;
}

/**
 * Summarize OpenHands status for Chat display.
 * Returns short status hints, not raw logs.
 */
export function summarizeOpenHandsChatStatus(snapshot: OpenHandsJobSnapshot): string {
  const gate = gateOpenHandsResult(snapshot);

  switch (gate.type) {
    case 'running':
      return snapshot.status === 'running'
        ? `OpenHands arbeitet: ${snapshot.changedFiles?.length ?? 0} Datei(en) bisher.`
        : 'OpenHands wartet...';
    case 'success':
      return `OpenHands fertig: ${gate.changedFiles.length} Datei(en)${gate.draftPrUrl ? ', Draft PR erstellt' : ''}.`;
    case 'blocker':
      return 'OpenHands blockiert.';
    case 'empty':
      return 'OpenHands: Kein greifbares Ergebnis.';
    case 'plan-only':
      return 'OpenHands: Nur Dokumentation. Nicht als Ergebnis akzeptiert.';
    default:
      return 'OpenHands Status unbekannt.';
  }
}
