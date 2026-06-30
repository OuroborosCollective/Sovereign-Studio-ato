export interface AssistantResponsePacingConfig {
  readonly enabled: boolean;
  readonly thresholdWords: number;
  readonly initialWords: number;
  readonly wordsPerTick: number;
}

export interface AssistantResponsePacingState {
  readonly shouldPace: boolean;
  readonly totalWords: number;
  readonly visibleWords: number;
  readonly visibleText: string;
  readonly complete: boolean;
}

export const DEFAULT_ASSISTANT_RESPONSE_PACING: AssistantResponsePacingConfig = {
  enabled: true,
  thresholdWords: 22,
  initialWords: 18,
  wordsPerTick: 1,
};

export function countAssistantResponseWords(text: string): number {
  return text.match(/\S+/g)?.length ?? 0;
}

export function sliceAssistantResponseWords(text: string, visibleWords: number): string {
  if (visibleWords <= 0) return '';
  let seen = 0;
  for (const match of text.matchAll(/\S+\s*/g)) {
    seen += 1;
    const end = match.index + match[0].length;
    if (seen >= visibleWords) return text.slice(0, end);
  }
  return text;
}

export function createAssistantResponsePacingState(
  text: string,
  visibleWords: number,
  config: AssistantResponsePacingConfig = DEFAULT_ASSISTANT_RESPONSE_PACING,
): AssistantResponsePacingState {
  const totalWords = countAssistantResponseWords(text);
  const shouldPace = config.enabled && totalWords > config.thresholdWords;
  const boundedVisibleWords = shouldPace
    ? Math.min(totalWords, Math.max(0, visibleWords))
    : totalWords;

  return {
    shouldPace,
    totalWords,
    visibleWords: boundedVisibleWords,
    visibleText: shouldPace ? sliceAssistantResponseWords(text, boundedVisibleWords) : text,
    complete: boundedVisibleWords >= totalWords,
  };
}

export function initialAssistantResponseVisibleWords(
  text: string,
  config: AssistantResponsePacingConfig = DEFAULT_ASSISTANT_RESPONSE_PACING,
): number {
  const totalWords = countAssistantResponseWords(text);
  if (!config.enabled || totalWords <= config.thresholdWords) return totalWords;
  return Math.min(totalWords, config.initialWords);
}

export function nextAssistantResponseVisibleWords(
  currentVisibleWords: number,
  text: string,
  config: AssistantResponsePacingConfig = DEFAULT_ASSISTANT_RESPONSE_PACING,
): number {
  const totalWords = countAssistantResponseWords(text);
  if (!config.enabled || totalWords <= config.thresholdWords) return totalWords;
  return Math.min(totalWords, currentVisibleWords + Math.max(1, config.wordsPerTick));
}
