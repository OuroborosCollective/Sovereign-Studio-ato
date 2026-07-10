import type { SovereignAgentJobSnapshot } from './sovereignAgentRuntime';
import type { SolutionPatternLearningInput } from './solutionPatternMemory';

/**
 * Sovereign Agent Pattern Gateway Bridge
 *
 * Guards the learning flow from Sovereign Agent job results to Pattern Memory.
 *
 * Architecture rules enforced:
 * - Sovereign Agent is executor, not truth source
 * - Sovereign Runtime decides preconditions, context, memory intake, result display
 * - Pattern Gateway validates every new learning pattern
 * - No direct unvalidated write access to Remote Memory
 * - No Auto-Merge, no Plan-only Draft PR, no Secrets in logs/preview/memory
 */

export type SovereignAgentResultType = 'idle' | 'running' | 'success' | 'blocker' | 'empty' | 'plan-only';

export interface SovereignAgentPatternIntakeInput {
  mission: string;
  snapshot: SovereignAgentJobSnapshot;
  providerId?: string;
  now?: number;
}

/**
 * Validates that an Sovereign Agent result represents a real outcome.
 * Only actual changed files, diff, or draft PR counts as a valid result.
 */
export function classifySovereignAgentResult(snapshot: SovereignAgentJobSnapshot): SovereignAgentResultType {
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
export interface SovereignAgentResultGate {
  allowed: boolean;
  type: SovereignAgentResultType;
  summary: string;
  changedFiles: string[];
  draftPrUrl?: string;
  blockerReason?: string;
}

export function gateSovereignAgentResult(snapshot: SovereignAgentJobSnapshot): SovereignAgentResultGate {
  const type = classifySovereignAgentResult(snapshot);

  switch (type) {
    case 'running':
      return {
        allowed: false,
        type,
        summary: 'Sovereign Agent job is still running or waiting.',
        changedFiles: snapshot.changedFiles ?? [],
        draftPrUrl: snapshot.draftPrUrl,
      };

    case 'blocker':
      return {
        allowed: true,
        type,
        summary: snapshot.lastError || 'Sovereign Agent job blocked by a gate.',
        changedFiles: snapshot.changedFiles ?? [],
        blockerReason: snapshot.lastError,
      };

    case 'empty':
      return {
        allowed: false,
        type,
        summary: 'Sovereign Agent job completed but produced no changed files or draft PR.',
        changedFiles: [],
      };

    case 'plan-only':
      return {
        allowed: false,
        type,
        summary: 'Sovereign Agent result contains only documentation/config changes. Plan-only Draft PRs are prohibited.',
        changedFiles: snapshot.changedFiles ?? [],
      };

    case 'success':
      return {
        allowed: true,
        type,
        summary: snapshot.draftPrUrl
          ? `Sovereign Agent produced real changes: ${snapshot.changedFiles.length} file(s), Draft PR created.`
          : `Sovereign Agent produced real changes: ${snapshot.changedFiles.length} file(s).`,
        changedFiles: snapshot.changedFiles ?? [],
        draftPrUrl: snapshot.draftPrUrl,
      };

    default:
      return {
        allowed: false,
        type: 'idle',
        summary: 'Unknown Sovereign Agent job status.',
        changedFiles: [],
      };
  }
}

/**
 * Filter events for UI display.
 * Removes raw Sovereign Agent logs that may contain sensitive data.
 */
export interface FilteredSovereignAgentEvent {
  at: number;
  level: 'info' | 'warning' | 'error' | 'success';
  stage: string;
  message: string;
  safe: boolean;
}

export function filterSovereignAgentEventsForUI(events: SovereignAgentJobSnapshot['events']): FilteredSovereignAgentEvent[] {
  if (!Array.isArray(events)) return [];

  return events.map((event): FilteredSovereignAgentEvent => {
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
 * Build Pattern Learning Input from validated Sovereign Agent result.
 * Only called when gateSovereignAgentResult returns allowed: true.
 */
export function buildPatternIntakeFromSovereignAgent(input: SovereignAgentPatternIntakeInput): SolutionPatternLearningInput | null {
  const gate = gateSovereignAgentResult(input.snapshot);

  if (!gate.allowed) {
    return null;
  }

  const firstFile = gate.changedFiles[0] ?? 'unknown';

  return {
    intakeNode: 'sovereign-agent-runtime',
    processingNode: 'learning-memory',
    outputNodes: ['action-builder', 'generated-file-review', 'learning-memory'],
    problem: {
      category: 'learning-memory',
      severity: gate.type === 'blocker' ? 'high' : 'medium',
      filePath: firstFile,
      description: `Sovereign Agent mission: ${input.mission}`,
      contextPaths: gate.changedFiles,
      contextSignals: [
        `sovereign-agent-result:${gate.type}`,
        `changed-files:${gate.changedFiles.length}`,
        gate.draftPrUrl ? 'has-draft-pr' : 'no-draft-pr',
      ],
    },
    fix: {
      summary: gate.summary,
      changedFiles: gate.changedFiles,
      steps: [`Sovereign Agent result type: ${gate.type}`],
      completed: gate.type === 'success',
      proof: gate.draftPrUrl,
    },
    confidence: gate.type === 'success' ? 'completed' : 'inferred',
    tags: ['sovereign-agent', 'agent-result', gate.type],
    now: input.now,
  };
}

/**
 * Check if an Sovereign Agent job should trigger pattern learning.
 */
export function shouldLearnFromSovereignAgent(snapshot: SovereignAgentJobSnapshot): boolean {
  const gate = gateSovereignAgentResult(snapshot);
  return gate.allowed;
}

/**
 * Summarize agent status for Chat display.
 * Returns short status hints, not raw logs.
 */
export function summarizeSovereignAgentChatStatus(snapshot: SovereignAgentJobSnapshot): string {
  const gate = gateSovereignAgentResult(snapshot);

  switch (gate.type) {
    case 'running':
      return snapshot.status === 'running'
        ? `Sovereign Agent arbeitet: ${snapshot.changedFiles?.length ?? 0} Datei(en) bisher.`
        : 'Sovereign Agent wartet...';
    case 'success':
      return `Sovereign Agent fertig: ${gate.changedFiles.length} Datei(en)${gate.draftPrUrl ? ', Draft PR erstellt' : ''}.`;
    case 'blocker':
      return 'Sovereign Agent blockiert.';
    case 'empty':
      return 'Sovereign Agent: Kein greifbares Ergebnis.';
    case 'plan-only':
      return 'Sovereign Agent: Nur Dokumentation. Nicht als Ergebnis akzeptiert.';
    default:
      return 'Sovereign Agent Status unbekannt.';
  }
}
