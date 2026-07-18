/**
 * usePatternMemoryStore — Issues #447, #2, #3
 *
 * Projects server-accepted learning evidence into the local pattern cache and
 * appends an informational chat line only after a vector was really stored.
 *
 * A Draft PR URL is context, never learning truth. The authoritative signal is
 * the bounded preparation response: allowed + candidateId + vectorStored.
 * The accepted cache survives refreshes but never promotes local observations.
 *
 * Product rules respected:
 *  - No fake truth: PR context plus accepted candidate/vector evidence is required.
 *  - No auto-execute on repo writes: only writes to in-memory + localStorage.
 *  - No duplicate projections: a Set ref guards by accepted candidate identity.
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
import type { SovereignPatternLearningEvidence } from '../runtime/sovereignAgentClient';

// ── localStorage key ─────────────────────────────────────────────────────────

export const PATTERN_MEMORY_LS_KEY = 'sovereign.acceptedPatternMemory.v2';

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
  try {
    const report = validatePatternMemoryStore(candidate);
    if (!report.valid) return createPatternMemoryStore();
    const acceptedEntries = candidate.entries.filter((entry) => entry.verified && Boolean(entry.vectorRef));
    return acceptedEntries.length === candidate.entries.length
      ? candidate
      : { ...candidate, entries: acceptedEntries };
  } catch {
    return createPatternMemoryStore();
  }
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
  /** Normalized server-side learning and vector evidence from Draft-PR preparation. */
  learningEvidence?: SovereignPatternLearningEvidence;
  /**
   * Traditional publish path (optional).
   * Set by the parent component to the PR URL returned by mergeWhenGreen once
   * approvalConfirmed === true. Leave undefined if not available in this context.
   */
  publishedPrUrl?: string;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

/**
 * Projects one accepted server-side learning result into the local cache and
 * chat only when a PR context and stored vector evidence are both available.
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
    learningEvidence,
    publishedPrUrl,
  } = opts;

  /**
   * Tracks accepted candidate identities already projected in this session.
   * PR URLs may repeat across retries and are not identity evidence.
   */
  const savedCandidateIdsRef = useRef<Set<string>>(new Set());

  // ── Persist to localStorage whenever the store changes ──────────────────
  useEffect(() => {
    lsSet(PATTERN_MEMORY_LS_KEY, patternMemoryStore);
  }, [patternMemoryStore]);

  // ── Shared save helper ───────────────────────────────────────────────────
  // Extracted so both effects use identical logic.
  const maybeSave = (prUrl: string | null | undefined): void => {
    const candidateId = learningEvidence?.candidateId;
    if (!prUrl || !candidateId || !learningEvidence.allowed || !learningEvidence.vectorStored) return;
    if (savedCandidateIdsRef.current.has(candidateId)) return;
    savedCandidateIdsRef.current.add(candidateId);

    const proposal = derivePatternIntakeFromWorkflow({
      mission,
      repoOwner,
      repoName,
      prUrl,
    });
    const intake = {
      ...proposal,
      sourceTraceId: `accepted:${candidateId}`,
      vectorRef: candidateId,
      verified: true,
      localExecutable: false,
    };

    setPatternMemoryStore((prev) => addPatternEntry(prev, intake));

    appendChatLine({
      role: 'assistant',
      text: buildPatternSavedChatText(intake.title, prUrl, repoOwner, repoName),
    });
  };

  // ── Signal 1: Sovereign Agent path ─────────────────────────────────────────────
  useEffect(() => {
    if (agentWorkSnapshot.state !== 'draft_pr_ready') return;
    maybeSave(agentWorkSnapshot.draftPrUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentWorkSnapshot.state, agentWorkSnapshot.draftPrUrl, learningEvidence]);

  // ── Signal 2: Traditional publish path ───────────────────────────────────
  useEffect(() => {
    if (!publishedPrUrl) return;
    maybeSave(publishedPrUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [publishedPrUrl, learningEvidence]);
}
