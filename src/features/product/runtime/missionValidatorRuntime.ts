export interface MissionValidationResult {
  readonly score: number;
  readonly specificEnough: boolean;
  readonly questions: readonly string[];
  readonly evidence: readonly string[];
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
