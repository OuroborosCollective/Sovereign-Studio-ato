import { resolvePrimaryBridgeConfig } from '../llm/primaryBridgeConfig';

export interface MissionValidationResult {
  readonly score: number;
  readonly specificEnough: boolean;
  readonly questions: readonly string[];
  readonly evidence: readonly string[];
  readonly status?: 'ready' | 'deterministic_fallback';
  readonly modelUsed?: string;
  readonly resolvedTransport?: string;
  readonly fallbackUsed?: boolean;
  readonly attemptedRouteCount?: number;
  readonly error?: string;
}

const ACTION_PATTERN = /\b(add|build|change|create|delete|fix|implement|integrate|migrate|refactor|remove|repair|replace|test|update|analyse|analysiere|baue|behebe|ändere|erstelle|füge|implementiere|integriere|lösche|migriere|prüfe|repariere|teste|überarbeite)\b/i;
const TARGET_PATTERN = /(?:\b(?:api|backend|branch|button|component|database|datei|endpoint|feature|frontend|funktion|modul|page|repository|route|runtime|screen|service|test|ui|workflow)\b|[A-Za-z0-9_.-]+\/(?:[A-Za-z0-9_.\/-]+)|[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|kt|sql|yml|yaml))/i;
const OUTCOME_PATTERN = /\b(acceptance|akzeptanz|block|build|ci|evidence|ergebnis|erwartet|fail|gate|grün|output|pass|result|test|validier|verifizier|when|wenn)\b/i;
const CONSTRAINT_PATTERN = /\b(autoritative|deterministic|draft|fail[- ]?closed|kein|keine|must|nicht|only|ohne|shall|soll|truth|wahrheit)\b/i;
const BROAD_PATTERN = /\b(all|alles|entire|ganze[nmrs]?|komplett|whole)\b/i;

function normalizeMission(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

export function validateMissionSpecificity(mission: string): MissionValidationResult {
  const clean = normalizeMission(mission);
  const evidence: string[] = [];
  const questions: string[] = [];
  let score = 0;

  if (clean.length >= 24) {
    score += 20;
    evidence.push('mission_has_minimum_detail');
  } else {
    questions.push('Was soll konkret geändert werden?');
  }

  if (ACTION_PATTERN.test(clean)) {
    score += 25;
    evidence.push('explicit_action_present');
  } else {
    questions.push('Welche konkrete Aktion soll laufen?');
  }

  if (TARGET_PATTERN.test(clean)) {
    score += 25;
    evidence.push('target_surface_present');
  } else {
    questions.push('Welche Datei oder Systemfläche ist betroffen?');
  }

  if (OUTCOME_PATTERN.test(clean)) {
    score += 20;
    evidence.push('verification_outcome_present');
  } else {
    questions.push('Woran ist der Erfolg belegbar?');
  }

  if (CONSTRAINT_PATTERN.test(clean)) {
    score += 10;
    evidence.push('constraint_present');
  }

  if (BROAD_PATTERN.test(clean) && clean.length < 120) {
    score = Math.max(0, score - 20);
    evidence.push('broad_scope_penalty');
  }

  const boundedScore = Math.max(0, Math.min(100, score));
  return {
    score: boundedScore,
    specificEnough: boundedScore >= 40,
    questions: questions.slice(0, 3),
    evidence,
  };
}

export async function requestMissionValidation(mission: string): Promise<MissionValidationResult> {
  const fallback = validateMissionSpecificity(mission);
  try {
    const base = resolvePrimaryBridgeConfig().backendBaseUrl;
    const response = await fetch(`${base}/api/user/agent/validate-mission`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ mission }),
    });
    const payload = await response.json() as Partial<MissionValidationResult>;
    if (!response.ok || typeof payload.score !== 'number' || !Number.isFinite(payload.score)) {
      return { ...fallback, status: 'deterministic_fallback', error: payload.error || `Mission validation HTTP ${response.status}` };
    }
    return {
      score: Math.max(0, Math.min(100, Number(payload.score))),
      specificEnough: payload.specificEnough === true,
      questions: Array.isArray(payload.questions) ? payload.questions.filter((value): value is string => typeof value === 'string').slice(0, 3) : fallback.questions,
      evidence: Array.isArray(payload.evidence) ? payload.evidence.filter((value): value is string => typeof value === 'string') : fallback.evidence,
      status: payload.status === 'ready' ? 'ready' : 'deterministic_fallback',
      modelUsed: payload.modelUsed,
      resolvedTransport: payload.resolvedTransport,
      fallbackUsed: payload.fallbackUsed,
      attemptedRouteCount: payload.attemptedRouteCount,
      error: payload.error,
    };
  } catch (error) {
    return { ...fallback, status: 'deterministic_fallback', error: error instanceof Error ? error.message : 'Mission validation unavailable' };
  }
}

export function formatMissionPreflight(result: MissionValidationResult): string {
  const state = result.specificEnough ? 'STARTBEREIT' : 'WARNUNG';
  const lines = [
    `Pre-flight Mission Validator: ${state} · ${result.score}/100`,
    `Evidence: ${result.evidence.length ? result.evidence.join(', ') : 'keine Spezifitätsmerkmale erkannt'}`,
  ];
  if (result.questions.length) {
    lines.push('Klärungsfragen:');
    result.questions.forEach((question) => lines.push(`- ${question}`));
    lines.push('- Der Nutzer darf trotzdem fortfahren; die Warnung ist kein erfundener Runtime-Blocker.');
  }
  return lines.join('\n');
}
