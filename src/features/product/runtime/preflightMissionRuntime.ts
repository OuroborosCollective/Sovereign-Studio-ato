export interface MissionValidationQuestion {
  id: string;
  question: string;
}

export interface MissionValidationResult {
  confidence: number;
  questions: MissionValidationQuestion[];
  warnings: string[];
  canStart: boolean;
}

const VAGUE_PHRASES = [
  'refactor everything',
  'refactor the whole codebase',
  'fix everything',
  'make it better',
  'improve the app',
  'do the rest',
];

export function validateMissionLocally(mission: string): MissionValidationResult {
  const clean = mission.trim();
  const warnings: string[] = [];
  const questions: MissionValidationQuestion[] = [];
  let confidence = 100;

  if (clean.length < 24) {
    confidence -= 35;
    warnings.push('Mission is too short to establish a bounded implementation target.');
    questions.push({ id: 'target', question: 'Which exact component or runtime path should change?' });
  }
  if (VAGUE_PHRASES.some((phrase) => clean.toLowerCase().includes(phrase))) {
    confidence -= 35;
    warnings.push('Mission contains an unbounded whole-system instruction.');
    questions.push({ id: 'scope', question: 'Which files, feature, or failure family define the scope?' });
  }
  if (!/\b(test|verify|evidence|acceptance|expected|must|should)\b/i.test(clean)) {
    confidence -= 20;
    warnings.push('No explicit verification or acceptance condition was detected.');
    questions.push({ id: 'evidence', question: 'What evidence proves the mission is complete?' });
  }
  if (!/\b(file|route|component|module|endpoint|workflow|runtime|screen|api|database|branch|pr)\b/i.test(clean)) {
    confidence -= 15;
    warnings.push('No concrete technical surface was detected.');
    questions.push({ id: 'surface', question: 'Which technical surface is authoritative for this change?' });
  }

  const boundedConfidence = Math.max(0, Math.min(100, confidence));
  return {
    confidence: boundedConfidence,
    questions: questions.slice(0, 3),
    warnings,
    canStart: boundedConfidence >= 40,
  };
}

export function shouldWarnBeforeMissionStart(result: MissionValidationResult): boolean {
  return result.confidence < 40;
}
