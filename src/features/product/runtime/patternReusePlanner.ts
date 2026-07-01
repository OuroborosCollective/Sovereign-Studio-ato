/**
 * Pattern Reuse Planner — Issue #447
 * Matches existing learned patterns to chat intents and produces
 * transparent, honest chat hints. No fake intelligence claims.
 */

import type { LearnedPatternEntry } from './patternMemoryRuntime';

export interface PatternReuseMatch {
  readonly patternId: string;
  readonly title: string;
  readonly summary: string;
  readonly localExecutable: boolean;
  readonly verified: boolean;
  readonly reuseCount: number;
  readonly score: number;
  readonly matchReasons: string[];
}

export interface PatternReusePlanResult {
  readonly hasMatches: boolean;
  readonly matchCount: number;
  readonly localExecutableCount: number;
  readonly topMatches: PatternReuseMatch[];
  readonly chatHint: string;
  readonly localPrepareAvailable: boolean;
}

export interface PatternReuseQuery {
  readonly intentText: string;
  readonly tags?: string[];
  readonly requireVerified?: boolean;
  readonly requireLocalExecutable?: boolean;
  readonly limit?: number;
}

const MAX_MATCHES = 10;
const MIN_SCORE = 1;
const FREQUENTLY_USED_THRESHOLD = 3;

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s_-]/g, ' ')
    .split(/\s+/)
    .filter((t) => t.length >= 3);
}

function normalizeTag(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9:_-]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
}

function scoreMatch(entry: LearnedPatternEntry, queryTokens: string[], queryTags: string[]): { score: number; reasons: string[] } {
  const reasons: string[] = [];
  let score = 0;

  const titleTokens = tokenize(entry.title);
  const summaryTokens = tokenize(entry.summary);

  const titleOverlap = queryTokens.filter((t) => titleTokens.includes(t)).length;
  if (titleOverlap > 0) {
    score += titleOverlap * 3;
    reasons.push(`${titleOverlap} Titel-Token übereinstimmend`);
  }

  const summaryOverlap = queryTokens.filter((t) => summaryTokens.includes(t)).length;
  if (summaryOverlap > 0) {
    score += summaryOverlap;
    reasons.push(`${summaryOverlap} Beschreibungs-Token übereinstimmend`);
  }

  const tagOverlap = queryTags.filter((t) => entry.tags.includes(t)).length;
  if (tagOverlap > 0) {
    score += tagOverlap * 2;
    reasons.push(`${tagOverlap} Tag(s) übereinstimmend`);
  }

  // Quality bonuses only apply when there is already a content match
  if (score > 0) {
    if (entry.verified) {
      score += 1;
      reasons.push('geprüftes Pattern');
    }

    if (entry.localExecutable) {
      score += 1;
      reasons.push('lokal ausführbar');
    }

    if (entry.reuseCount >= FREQUENTLY_USED_THRESHOLD) {
      score += 1;
      reasons.push(`${entry.reuseCount}× wiederverwendet`);
    }
  }

  return { score, reasons };
}

export function planPatternReuse(entries: LearnedPatternEntry[], query: PatternReuseQuery): PatternReusePlanResult {
  const limit = Math.max(1, Math.min(query.limit ?? 5, MAX_MATCHES));
  const queryTokens = tokenize(query.intentText);
  const queryTags = (query.tags ?? []).map(normalizeTag).filter(Boolean);

  const filtered = entries
    .filter((e) => !query.requireVerified || e.verified)
    .filter((e) => !query.requireLocalExecutable || e.localExecutable);

  const scored: PatternReuseMatch[] = filtered
    .map((e) => {
      const { score, reasons } = scoreMatch(e, queryTokens, queryTags);
      return {
        patternId: e.id,
        title: e.title,
        summary: e.summary,
        localExecutable: e.localExecutable,
        verified: e.verified,
        reuseCount: e.reuseCount,
        score,
        matchReasons: reasons,
      };
    })
    .filter((m) => m.score >= MIN_SCORE)
    .sort((a, b) => b.score - a.score || b.reuseCount - a.reuseCount)
    .slice(0, limit);

  const localExecutableCount = scored.filter((m) => m.localExecutable).length;
  const localPrepareAvailable = localExecutableCount > 0;

  const chatHint = buildChatHint(scored, localPrepareAvailable);

  return {
    hasMatches: scored.length > 0,
    matchCount: scored.length,
    localExecutableCount,
    topMatches: scored,
    chatHint,
    localPrepareAvailable,
  };
}

function buildChatHint(matches: PatternReuseMatch[], localPrepareAvailable: boolean): string {
  if (matches.length === 0) {
    return [
      'Dafür gibt es noch kein geprüftes lokales Pattern.',
      'Ich kann den Ablauf nach erfolgreicher Arbeit als neues Pattern vorschlagen.',
    ].join('\n');
  }

  const count = matches.length;
  const localNote = localPrepareAvailable
    ? 'Ich kann zuerst lokal vorbereiten und nur bei Lücken eine Modellroute nutzen.'
    : 'Lokale Vorbereitung ist für diese Pattern noch nicht verfügbar.';

  return [
    `Ich kenne dafür ${count} geprüfte${count === 1 ? 's' : ''} Pattern${count === 1 ? '' : 's'} aus deiner bisherigen Arbeit.`,
    localNote,
  ].join('\n');
}

export function buildPatternReuseHintActions(result: PatternReusePlanResult): string[] {
  if (!result.hasMatches) {
    return [];
  }
  const actions: string[] = [];
  if (result.localPrepareAvailable) actions.push('Lokal vorbereiten');
  actions.push('Mit Modellroute starten');
  actions.push('Patterns ansehen');
  return actions;
}

export function buildNoPatternHintActions(): string[] {
  return [];
}

export interface PatternReuseHintViewModel {
  readonly hintText: string;
  readonly actions: string[];
  readonly hasMatches: boolean;
  readonly matchCount: number;
  readonly localExecutableCount: number;
}

export function buildPatternReuseHintViewModel(
  entries: LearnedPatternEntry[],
  query: PatternReuseQuery,
): PatternReuseHintViewModel {
  const result = planPatternReuse(entries, query);
  return {
    hintText: result.chatHint,
    actions: result.hasMatches ? buildPatternReuseHintActions(result) : buildNoPatternHintActions(),
    hasMatches: result.hasMatches,
    matchCount: result.matchCount,
    localExecutableCount: result.localExecutableCount,
  };
}
