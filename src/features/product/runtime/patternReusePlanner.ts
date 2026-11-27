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

// Optimization: Hoist regular expressions to module scope to avoid re-compilation in hot paths
const TOKENIZE_CLEAN_RE = /[^a-z0-9\s_-]/g;
const TOKENIZE_SPLIT_RE = /\s+/;
const NORMALIZE_TAG_CLEAN_RE = /[^a-z0-9:_-]+/g;
const NORMALIZE_TAG_TRIM_RE = /^-|-$/g;

function tokenize(text: string): string[] {
  const words = text
    .toLowerCase()
    .replace(TOKENIZE_CLEAN_RE, ' ')
    .split(TOKENIZE_SPLIT_RE);
  const result: string[] = [];
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (w.length >= 3) {
      result.push(w);
    }
  }
  return result;
}

function normalizeTag(value: string): string {
  return value.trim().toLowerCase().replace(NORMALIZE_TAG_CLEAN_RE, '-').replace(NORMALIZE_TAG_TRIM_RE, '').slice(0, 40);
}

// Optimization: Cache parsed token and tag Sets per immutable LearnedPatternEntry reference.
// Using WeakMap avoids memory leaks (entries are automatically GC'd) and avoids re-tokenizing
// titles and summaries on repeated planning calls.
interface CachedPatternMeta {
  readonly titleTokens: Set<string>;
  readonly summaryTokens: Set<string>;
  readonly tagsSet: Set<string>;
}

const patternTokenCache = new WeakMap<LearnedPatternEntry, CachedPatternMeta>();

function getCachedPatternMeta(entry: LearnedPatternEntry): CachedPatternMeta {
  let cached = patternTokenCache.get(entry);
  if (!cached) {
    cached = {
      titleTokens: new Set(tokenize(entry.title)),
      summaryTokens: new Set(tokenize(entry.summary)),
      tagsSet: new Set(entry.tags),
    };
    patternTokenCache.set(entry, cached);
  }
  return cached;
}

function scoreMatch(entry: LearnedPatternEntry, queryTokens: string[], queryTags: string[]): { score: number; reasons: string[] } {
  const reasons: string[] = [];
  let score = 0;

  const { titleTokens, summaryTokens, tagsSet } = getCachedPatternMeta(entry);

  // Optimization: O(1) Set lookups replace O(M) Array.includes searches
  let titleOverlap = 0;
  for (let i = 0; i < queryTokens.length; i++) {
    if (titleTokens.has(queryTokens[i])) {
      titleOverlap++;
    }
  }
  if (titleOverlap > 0) {
    score += titleOverlap * 3;
    reasons.push(`${titleOverlap} Titel-Token übereinstimmend`);
  }

  let summaryOverlap = 0;
  for (let i = 0; i < queryTokens.length; i++) {
    if (summaryTokens.has(queryTokens[i])) {
      summaryOverlap++;
    }
  }
  if (summaryOverlap > 0) {
    score += summaryOverlap;
    reasons.push(`${summaryOverlap} Beschreibungs-Token übereinstimmend`);
  }

  let tagOverlap = 0;
  for (let i = 0; i < queryTags.length; i++) {
    if (tagsSet.has(queryTags[i])) {
      tagOverlap++;
    }
  }
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

  // Single-pass normalized tag extraction avoiding intermediate arrays
  const rawTags = query.tags;
  const queryTags: string[] = [];
  if (rawTags && rawTags.length > 0) {
    for (let i = 0; i < rawTags.length; i++) {
      const tag = normalizeTag(rawTags[i]);
      if (tag) {
        queryTags.push(tag);
      }
    }
  }

  const reqVerified = query.requireVerified === true;
  const reqLocal = query.requireLocalExecutable === true;

  // Optimization: Consolidate filtering, scoring, and score threshold checking
  // into a single-pass loop over entries, eliminating multiple intermediate array allocations.
  const scored: PatternReuseMatch[] = [];
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    if (reqVerified && !e.verified) continue;
    if (reqLocal && !e.localExecutable) continue;

    const { score, reasons } = scoreMatch(e, queryTokens, queryTags);
    if (score >= MIN_SCORE) {
      scored.push({
        patternId: e.id,
        title: e.title,
        summary: e.summary,
        localExecutable: e.localExecutable,
        verified: e.verified,
        reuseCount: e.reuseCount,
        score,
        matchReasons: reasons,
      });
    }
  }

  scored.sort((a, b) => b.score - a.score || b.reuseCount - a.reuseCount);
  const topMatches = scored.slice(0, limit);

  let localExecutableCount = 0;
  for (let i = 0; i < topMatches.length; i++) {
    if (topMatches[i].localExecutable) {
      localExecutableCount++;
    }
  }
  const localPrepareAvailable = localExecutableCount > 0;

  const chatHint = buildChatHint(topMatches, localPrepareAvailable);

  return {
    hasMatches: topMatches.length > 0,
    matchCount: topMatches.length,
    localExecutableCount,
    topMatches,
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
