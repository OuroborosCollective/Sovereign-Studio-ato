import type { SovereignTelemetryEvent } from './sovereignTelemetry';

export type RuntimeOutcomeStatus = 'fulfilled' | 'partial' | 'blocked' | 'noise' | 'invalid';

export interface RuntimeOutcomeExpectation {
  required: string[];
  blockers?: string[];
  noise?: string[];
}

export interface RuntimeOutcomeReport {
  status: RuntimeOutcomeStatus;
  score: number;
  matched: string[];
  missing: string[];
  blockers: string[];
  noise: string[];
  learnable: boolean;
  summary: string;
}

function norm(value: string): string {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

function hits(source: string, tokens: string[] = []): string[] {
  const clean = norm(source);
  return tokens.map(norm).filter((token) => token.length > 0 && clean.includes(token));
}

export function isRuntimeFeedbackNoiseText(label: string, message: string): boolean {
  const source = `${norm(label)} ${norm(message)}`;
  const healthGateLike = [
    'health red prevents guarded output',
    'health idle prevents guarded output',
    'health gate blockiert',
    'prevents guarded output',
  ];

  return healthGateLike.some((token) => source.includes(token)) ||
    (source.includes('runtime needs attention') && source.includes('health'));
}

export function isRuntimeFeedbackNoiseEvent(event: SovereignTelemetryEvent): boolean {
  return isRuntimeFeedbackNoiseText(event.label, event.message);
}

export function evaluateRuntimeOutcome(expectation: RuntimeOutcomeExpectation, delivered: string): RuntimeOutcomeReport {
  const required = expectation.required.map(norm).filter(Boolean);
  const matched = hits(delivered, required);
  const missing = required.filter((token) => !matched.includes(token));
  const blockers = hits(delivered, expectation.blockers ?? []);
  const noise = hits(delivered, expectation.noise ?? []);

  if (!required.length) {
    return { status: 'invalid', score: 0, matched, missing: ['required outcome'], blockers, noise, learnable: false, summary: 'Outcome contract has no required signal.' };
  }

  if (noise.length && !matched.length) {
    return { status: 'noise', score: 0, matched, missing, blockers, noise, learnable: false, summary: `Outcome is feedback noise: ${noise.join(', ')}.` };
  }

  if (blockers.length) {
    return { status: 'blocked', score: 0, matched, missing, blockers, noise, learnable: false, summary: `Outcome is blocked: ${blockers.join(', ')}.` };
  }

  const score = matched.length / required.length;
  if (!missing.length) {
    return { status: 'fulfilled', score, matched, missing, blockers, noise, learnable: true, summary: 'Outcome fulfilled all required signals.' };
  }

  if (matched.length) {
    return { status: 'partial', score, matched, missing, blockers, noise, learnable: false, summary: `Outcome is partial; missing ${missing.join(', ')}.` };
  }

  return { status: 'invalid', score: 0, matched, missing, blockers, noise, learnable: false, summary: `Outcome did not match required signals: ${missing.join(', ')}.` };
}
