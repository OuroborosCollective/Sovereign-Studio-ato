/**
 * usePatternMemoryStore — Issue #447
 *
 * Watches for a successful workflow completion (agentWorkSnapshot.state ===
 * 'draft_pr_ready') and automatically saves the completed workflow as a
 * PatternMemoryEntry, then appends an informational chat line so the user
 * knows the pattern has been stored — without requiring any user action.
 *
 * Rules respected:
 *  - No fake truth: pattern is only saved when a real draftPrUrl is present.
 *  - No auto-execute on code writes: this only writes to the in-memory
 *    PatternMemoryStore, not to any repository or external service.
 *  - No duplicate proposals: a ref guards against re-firing for the same PR.
 */

import { useEffect, useRef } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import {
  addPatternEntry,
  type PatternMemoryStore,
} from '../runtime/patternMemoryRuntime';
import {
  derivePatternIntakeFromWorkflow,
  buildPatternSavedChatText,
} from '../runtime/patternMemoryProposalRuntime';
import type { AgentWorkSnapshot } from '../runtime/agentWorkRuntime';

// ── Minimal structural type for the appendChatLine callback ─────────────────
// ChatLine is defined privately inside BuilderContainer, so we use a
// compatible structural type rather than importing an internal interface.
export interface AppendableChatLine {
  readonly role: 'system' | 'thought' | 'user' | 'assistant';
  readonly text: string;
  readonly id?: string;
  readonly createdAt?: number;
}

export interface UsePatternMemoryStoreOptions {
  /** Runtime snapshot — the hook reacts when state transitions to 'draft_pr_ready'. */
  agentWorkSnapshot: AgentWorkSnapshot;
  /** Current pattern memory store (read-only; the hook produces a new store). */
  patternMemoryStore: PatternMemoryStore;
  /** Setter from useState — the hook calls this to persist the new entry. */
  setPatternMemoryStore: Dispatch<SetStateAction<PatternMemoryStore>>;
  /** Active mission / task text used to title and tag the saved pattern. */
  mission: string;
  /**
   * Resolved repo owner and name from the chat repo snapshot.
   * Pass empty strings when no repo is loaded.
   */
  repoOwner: string;
  repoName: string;
  /** Appends a line to the BuilderContainer chat history (informational only). */
  appendChatLine: (line: AppendableChatLine) => void;
}

/**
 * Automatically saves a learned pattern and appends a chat notification when
 * a Draft PR workflow completes successfully.
 *
 * Call this hook once inside BuilderContainer after both `patternMemoryStore`
 * and `appendChatLine` are in scope.
 */
export function usePatternMemoryStore(opts: UsePatternMemoryStoreOptions): void {
  const {
    agentWorkSnapshot,
    setPatternMemoryStore,
    mission,
    repoOwner,
    repoName,
    appendChatLine,
  } = opts;

  /**
   * Tracks the last PR URL for which we have already saved a pattern.
   * Prevents duplicate entries if the snapshot re-renders while still
   * in the 'draft_pr_ready' state.
   */
  const lastSavedPrUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (agentWorkSnapshot.state !== 'draft_pr_ready') return;

    const prUrl = agentWorkSnapshot.draftPrUrl;
    if (!prUrl) return;

    // Guard: only save once per unique PR URL.
    if (lastSavedPrUrlRef.current === prUrl) return;
    lastSavedPrUrlRef.current = prUrl;

    const intake = derivePatternIntakeFromWorkflow({
      mission,
      repoOwner,
      repoName,
      prUrl,
    });

    // Persist to the store — pure functional update, no side-effects.
    setPatternMemoryStore((prev) => addPatternEntry(prev, intake));

    // Inform the user via a single assistant chat line.
    const chatText = buildPatternSavedChatText(
      intake.title,
      prUrl,
      repoOwner,
      repoName,
    );
    appendChatLine({ role: 'assistant', text: chatText });
  }, [
    agentWorkSnapshot.state,
    agentWorkSnapshot.draftPrUrl,
    mission,
    repoOwner,
    repoName,
    setPatternMemoryStore,
    appendChatLine,
  ]);
}
