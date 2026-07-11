/**
 * Hook-level tests for usePatternMemoryStore — Issue #4
 *
 * Covers:
 *  - Sovereign Agent path: first draft_pr_ready saves pattern + appends chat line
 *  - Duplicate-guard: same PR URL never fires twice (within a session)
 *  - Second distinct PR URL fires again
 *  - Non-draft_pr_ready states are ignored
 *  - Null / missing draftPrUrl is ignored
 *  - Traditional publish path (publishedPrUrl prop) saves pattern
 *  - Duplicate-guard is shared across both paths (same URL = no double-save)
 *  - localStorage is written whenever patternMemoryStore changes
 *  - loadPatternMemoryStoreFromStorage rehydrates a valid store
 *  - loadPatternMemoryStoreFromStorage falls back on corrupt data
 */

import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  usePatternMemoryStore,
  loadPatternMemoryStoreFromStorage,
  PATTERN_MEMORY_LS_KEY,
  type UsePatternMemoryStoreOptions,
  type AppendableChatLine,
} from './usePatternMemoryStore';
import {
  createPatternMemoryStore,
  type PatternMemoryStore,
} from '../runtime/patternMemoryRuntime';
import {
  createIdleSnapshot,
  transitionBranchCreated,
  transitionChecksRunning,
  transitionCommitCreated,
  transitionDraftPrReady,
  transitionExecutorStarting,
  transitionExecutorRunning,
  transitionIntentDetected,
  type AgentWorkSnapshot,
} from '../runtime/agentWorkRuntime';

// ── localStorage stub ────────────────────────────────────────────────────────

function buildLsStub(): Storage & { _store: Record<string, string> } {
  const _store: Record<string, string> = {};
  return {
    _store,
    getItem: (k: string) => _store[k] ?? null,
    setItem: (k: string, v: string) => { _store[k] = v; },
    removeItem: (k: string) => { delete _store[k]; },
    clear: () => { Object.keys(_store).forEach((k) => delete _store[k]); },
    key: (i: number) => Object.keys(_store)[i] ?? null,
    get length() { return Object.keys(_store).length; },
  };
}

let lsStub: ReturnType<typeof buildLsStub>;

beforeEach(() => {
  lsStub = buildLsStub();
  vi.stubGlobal('localStorage', lsStub);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── Snapshot helpers ─────────────────────────────────────────────────────────

function idleSnap(): AgentWorkSnapshot {
  return createIdleSnapshot('test-trace');
}

function readySnap(prUrl: string): AgentWorkSnapshot {
  // Walk the evidence-backed state machine path to reach draft_pr_ready.
  const base = createIdleSnapshot('test-trace');
  const withIntent = transitionIntentDetected(base, 'owner/repo', 'main');
  const starting = transitionExecutorStarting(withIntent, 'sovereign-agent');
  const running = transitionExecutorRunning(starting, 'job-test-123');
  const branched = transitionBranchCreated(running, 'sovereign/test-work');
  const committed = transitionCommitCreated(branched, 'abc1234');
  const checking = transitionChecksRunning(committed);
  return transitionDraftPrReady(checking, prUrl);
}

// ── Options builder ──────────────────────────────────────────────────────────

function makeOpts(overrides: Partial<UsePatternMemoryStoreOptions> = {}): {
  opts: UsePatternMemoryStoreOptions;
  chatLines: AppendableChatLine[];
  stores: PatternMemoryStore[];
  setPatternMemoryStore: (updater: (prev: PatternMemoryStore) => PatternMemoryStore) => void;
} {
  const chatLines: AppendableChatLine[] = [];
  const stores: PatternMemoryStore[] = [createPatternMemoryStore()];

  const setPatternMemoryStore = (
    updater: ((prev: PatternMemoryStore) => PatternMemoryStore) | PatternMemoryStore,
  ) => {
    const prev = stores[stores.length - 1];
    const next = typeof updater === 'function' ? updater(prev) : updater;
    stores.push(next);
  };

  const opts: UsePatternMemoryStoreOptions = {
    agentWorkSnapshot: idleSnap(),
    patternMemoryStore: stores[stores.length - 1],
    setPatternMemoryStore: setPatternMemoryStore as UsePatternMemoryStoreOptions['setPatternMemoryStore'],
    mission: 'Improve the dark-mode toggle',
    repoOwner: 'OuroborosCollective',
    repoName: 'Sovereign-Studio-ato',
    appendChatLine: (line) => chatLines.push(line),
    ...overrides,
  };

  return { opts, chatLines, stores, setPatternMemoryStore };
}

// ── Sovereign Agent path ───────────────────────────────────────────────────────────

describe('Sovereign Agent path (agentWorkSnapshot)', () => {
  const PR_URL = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1';

  it('saves a pattern when state transitions to draft_pr_ready', () => {
    const { opts, stores } = makeOpts({ agentWorkSnapshot: readySnap(PR_URL) });
    renderHook(() => usePatternMemoryStore(opts));
    expect(stores.length).toBeGreaterThan(1);
    expect(stores[stores.length - 1].entries).toHaveLength(1);
  });

  it('appends exactly one assistant chat line', () => {
    const { opts, chatLines } = makeOpts({ agentWorkSnapshot: readySnap(PR_URL) });
    renderHook(() => usePatternMemoryStore(opts));
    expect(chatLines).toHaveLength(1);
    expect(chatLines[0].role).toBe('assistant');
    expect(chatLines[0].text).toContain('✅');
  });

  it('saved pattern entry contains the PR URL as objectRef', () => {
    const { opts, stores } = makeOpts({ agentWorkSnapshot: readySnap(PR_URL) });
    renderHook(() => usePatternMemoryStore(opts));
    const entry = stores[stores.length - 1].entries[0];
    expect(entry.objectRef).toBe(PR_URL);
  });

  it('does nothing when state is idle', () => {
    const { opts, stores, chatLines } = makeOpts({ agentWorkSnapshot: idleSnap() });
    renderHook(() => usePatternMemoryStore(opts));
    expect(stores).toHaveLength(1); // no update
    expect(chatLines).toHaveLength(0);
  });

  it('does nothing when draftPrUrl is null', () => {
    const snap = { ...readySnap(PR_URL), draftPrUrl: null };
    const { opts, stores, chatLines } = makeOpts({ agentWorkSnapshot: snap });
    renderHook(() => usePatternMemoryStore(opts));
    expect(stores).toHaveLength(1);
    expect(chatLines).toHaveLength(0);
  });
});

// ── Duplicate guard ──────────────────────────────────────────────────────────

describe('Duplicate-guard (same PR URL)', () => {
  const PR_URL = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/10';

  it('does not save a second time when snapshot re-renders with the same URL', () => {
    const { opts, stores, chatLines } = makeOpts({ agentWorkSnapshot: readySnap(PR_URL) });
    const { rerender } = renderHook(
      (o: UsePatternMemoryStoreOptions) => usePatternMemoryStore(o),
      { initialProps: opts },
    );
    const countAfterFirst = stores.length;
    // Re-render with identical snapshot
    act(() => { rerender(opts); });
    expect(stores.length).toBe(countAfterFirst); // no new update
    expect(chatLines).toHaveLength(1);           // only one chat line
  });

  it('saves again when a different PR URL arrives', () => {
    const PR2 = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/11';
    const { opts, stores, chatLines } = makeOpts({ agentWorkSnapshot: readySnap(PR_URL) });
    const { rerender } = renderHook(
      (o: UsePatternMemoryStoreOptions) => usePatternMemoryStore(o),
      { initialProps: opts },
    );
    act(() => {
      rerender({ ...opts, agentWorkSnapshot: readySnap(PR2) });
    });
    expect(chatLines).toHaveLength(2);
    expect(stores[stores.length - 1].entries).toHaveLength(2);
  });
});

// ── Traditional publish path ─────────────────────────────────────────────────

describe('Traditional publish path (publishedPrUrl)', () => {
  const PR_URL = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/99';

  it('saves a pattern when publishedPrUrl is set', () => {
    const { opts, stores } = makeOpts({
      agentWorkSnapshot: idleSnap(),
      publishedPrUrl: PR_URL,
    });
    renderHook(() => usePatternMemoryStore(opts));
    expect(stores[stores.length - 1].entries).toHaveLength(1);
  });

  it('appends a chat line when publishedPrUrl is set', () => {
    const { opts, chatLines } = makeOpts({
      agentWorkSnapshot: idleSnap(),
      publishedPrUrl: PR_URL,
    });
    renderHook(() => usePatternMemoryStore(opts));
    expect(chatLines).toHaveLength(1);
    expect(chatLines[0].role).toBe('assistant');
  });

  it('does not save a second pattern when the same URL arrives via both paths', () => {
    const { opts, stores, chatLines } = makeOpts({
      agentWorkSnapshot: readySnap(PR_URL),
      publishedPrUrl: PR_URL,
    });
    renderHook(() => usePatternMemoryStore(opts));
    // Both effects fire but the Set guard blocks the second one.
    expect(stores.filter((s) => s.entries.length > 0).length).toBeGreaterThan(0);
    expect(chatLines).toHaveLength(1);
  });

  it('does nothing when publishedPrUrl is undefined', () => {
    const { opts, stores, chatLines } = makeOpts({
      agentWorkSnapshot: idleSnap(),
      publishedPrUrl: undefined,
    });
    renderHook(() => usePatternMemoryStore(opts));
    expect(stores).toHaveLength(1);
    expect(chatLines).toHaveLength(0);
  });
});

// ── localStorage persistence ─────────────────────────────────────────────────

describe('localStorage persistence', () => {
  const PR_URL = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/5';

  it('writes the store to localStorage when the store changes', () => {
    // Simulate a store that already has an entry (as if a save just happened).
    const filledStore = (() => {
      const base = createPatternMemoryStore();
      // We just need any store with updatedAt different from fresh one.
      return { ...base, updatedAt: 12345 };
    })();

    const { opts } = makeOpts({
      agentWorkSnapshot: idleSnap(),
      patternMemoryStore: filledStore,
    });
    renderHook(() => usePatternMemoryStore(opts));
    const raw = lsStub.getItem(PATTERN_MEMORY_LS_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.version).toBe(1);
  });
});

// ── loadPatternMemoryStoreFromStorage ─────────────────────────────────────────

describe('loadPatternMemoryStoreFromStorage', () => {
  it('returns an empty store when localStorage has nothing', () => {
    const store = loadPatternMemoryStoreFromStorage();
    expect(store.version).toBe(1);
    expect(store.entries).toHaveLength(0);
  });

  it('rehydrates a valid store from localStorage', () => {
    const saved = { version: 1, entries: [], updatedAt: 99999 };
    lsStub.setItem(PATTERN_MEMORY_LS_KEY, JSON.stringify(saved));
    const store = loadPatternMemoryStoreFromStorage();
    expect(store.updatedAt).toBe(99999);
  });

  it('falls back to an empty store when the stored JSON is invalid', () => {
    lsStub.setItem(PATTERN_MEMORY_LS_KEY, 'not-json{{{');
    const store = loadPatternMemoryStoreFromStorage();
    expect(store.entries).toHaveLength(0);
  });

  it('falls back to an empty store when the stored object fails validation', () => {
    // Wrong version number — should fail validatePatternMemoryStore
    lsStub.setItem(PATTERN_MEMORY_LS_KEY, JSON.stringify({ version: 99, entries: [] }));
    const store = loadPatternMemoryStoreFromStorage();
    expect(store.entries).toHaveLength(0);
  });
});
