/**
 * usePatternMemoryStore — Issues #447, #2, #3
 *
 * Watches for successful workflow completions and automatically saves
 * PatternMemoryEntries, appending an informational chat line each time.
 *
 * Two completion signals are handled:
 *  1. OpenHands path  — agentWorkSnapshot.state === 'draft_pr_ready'
 *  2. Traditional path — publishedPrUrl prop (set by parent after mergeWhenGreen)
 *
 * The store is persisted to localStorage and rehydrated on mount so patterns
 * survive page refreshes and browser restarts.
 *
 * Product rules respected:
 *  - No fake truth: pattern is saved only when a real PR URL is present.
 *  - No auto-execute on repo writes: only writes to in-memory + localStorage.
 *  - No duplicate proposals: a Set ref guards per PR URL across both paths.
 */

import { useEffect, useRef } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import {
  addPatternEntry,
  createPatternMemoryStore,
  validatePatternMemoryStore,
  type PatternMemoryStore,
} from '../runtime/patternMemoryRuntime';
import {
  derivePatternIntakeFromWorkflow,
  buildPatternSavedChatText,
} from '../runtime/patternMemoryProposalRuntime';
import type { AgentWorkSnapshot } from '../runtime/agentWorkRuntime';

// ── localStorage key ─────────────────────────────────────────────────────────

export const PATTERN_MEMORY_LS_KEY = 'sovereign.patternMemoryStore.v1';

// ── Safe localStorage helpers ────────────────────────────────────────────────

function lsGet<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function lsSet<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Quota exceeded or private-browsing restriction — silently skip.
  }
}

// ── Public: store loader (for useState initializer in BuilderContainer) ───────

/**
 * Loads and validates the PatternMemoryStore from localStorage.
 * Falls back to a fresh empty store if nothing is saved or the data is corrupt.
 */
export function loadPatternMemoryStoreFromStorage(): PatternMemoryStore {
  const candidate = lsGet<PatternMemoryStore>(PATTERN_MEMORY_LS_KEY);
  if (!candidate) return createPatternMemoryStore();
  const report = validatePatternMemoryStore(candidate);
  if (!report.valid) return createPatternMemoryStore();
  return candidate;
}

// ── Public: structural type for appendChatLine ────────────────────────────────
// ChatLine is defined privately inside BuilderContainer; a compatible structural
// type avoids the import coupling.
export interface AppendableChatLine {
  readonly role: 'system' | 'thought' | 'user' | 'assistant';
  readonly text: string;
  readonly id?: string;
  readonly createdAt?: number;
}

// ── Public: hook options ─────────────────────────────────────────────────────

export interface UsePatternMemoryStoreOptions {
  /** Runtime snapshot — the hook reacts when state transitions to 'draft_pr_ready'. */
  agentWorkSnapshot: AgentWorkSnapshot;
  /** Current pattern memory store — used for persistence tracking. */
  patternMemoryStore: PatternMemoryStore;
  /** Setter from useState — the hook calls this to add new entries. */
  setPatternMemoryStore: Dispatch<SetStateAction<PatternMemoryStore>>;
  /** Active mission / task text used to title and tag the saved pattern. */
  mission: string;
  /** GitHub repo owner from the active chat repo snapshot. Empty string if unknown. */
  repoOwner: string;
  /** GitHub repo name from the active chat repo snapshot. Empty string if unknown. */
  repoName: string;
  /** Appends a line to the BuilderContainer chat history (informational only). */
  appendChatLine: (line: AppendableChatLine) => void;
  /**
   * Traditional publish path (optional).
   * Set by the parent component to the PR URL returned by mergeWhenGreen once
   * approvalConfirmed === true. Leave undefined if not available in this context.
   */
  publishedPrUrl?: string;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

/**
 * Automatically saves a learned pattern and appends a chat notification when
 * a Draft PR workflow completes via either the OpenHands path or the
 * traditional publish path.
 *
 * Also persists the entire store to localStorage whenever it changes, and
 * should be initialised with `loadPatternMemoryStoreFromStorage()` in the
 * parent's useState call so patterns survive a page refresh.
 */
export function usePatternMemoryStore(opts: UsePatternMemoryStoreOptions): void {
  const {
    agentWorkSnapshot,
    patternMemoryStore,
    setPatternMemoryStore,
    mission,
    repoOwner,
    repoName,
    appendChatLine,
    publishedPrUrl,
  } = opts;

  /**
   * Tracks every PR URL for which a pattern has already been saved in this
   * session. A Set rather than a single string handles the edge case where
   * both paths fire for different URLs in the same session.
   */
  const savedPrUrlsRef = useRef<Set<string>>(new Set());

  // ── Persist to localStorage whenever the store changes ──────────────────
  useEffect(() => {
    lsSet(PATTERN_MEMORY_LS_KEY, patternMemoryStore);
  }, [patternMemoryStore]);

  // ── Shared save helper ───────────────────────────────────────────────────
  // Extracted so both effects use identical logic.
  const maybeSave = (prUrl: string | null | undefined): void => {
    if (!prUrl) return;
    if (savedPrUrlsRef.current.has(prUrl)) return;
    savedPrUrlsRef.current.add(prUrl);

    const intake = derivePatternIntakeFromWorkflow({
      mission,
      repoOwner,
      repoName,
      prUrl,
    });

    setPatternMemoryStore((prev) => addPatternEntry(prev, intake));

    appendChatLine({
      role: 'assistant',
      text: buildPatternSavedChatText(intake.title, prUrl, repoOwner, repoName),
    });
  };

  // ── Signal 1: OpenHands path ─────────────────────────────────────────────
  useEffect(() => {
    if (agentWorkSnapshot.state !== 'draft_pr_ready') return;
    maybeSave(agentWorkSnapshot.draftPrUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentWorkSnapshot.state, agentWorkSnapshot.draftPrUrl]);

  // ── Signal 2: Traditional publish path ───────────────────────────────────
  useEffect(() => {
    if (!publishedPrUrl) return;
    maybeSave(publishedPrUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [publishedPrUrl]);
}
