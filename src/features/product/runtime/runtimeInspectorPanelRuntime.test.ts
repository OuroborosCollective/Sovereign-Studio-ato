import { describe, expect, it } from "vitest";
import {
  deriveIntInspectorSignals,
  deriveOrcInspectorSignals,
  derivePatInspectorSignals,
  deriveBudInspectorSignals,
  deriveRuntimeInspectorSignals,
  toQuietInspectorSignal,
  buildPatInspectorStateFromStore,
  type BudInspectorState,
} from "./runtimeInspectorPanelRuntime";
import type { LlmRouteSelectionResult } from "./llmRouteBudgetRuntime";
import {
  createPatternMemoryStore,
  addPatternEntry,
  verifyPatternEntry,
  recordPatternReuse,
} from "./patternMemoryRuntime";

describe("runtimeInspectorPanelRuntime", () => {
  /* ───────────── PAT signals ───────────── */
  describe("derivePatInspectorSignals", () => {
    it("returns honest empty state when no memory exists", () => {
      const signals = derivePatInspectorSignals({ hasMemory: false, patternCount: 0 });
      expect(signals).toHaveLength(1);
      expect(signals[0].label).toBe("Pattern Memory");
      expect(signals[0].detail).toBe("Keine Pattern-Memory sichtbar.");
      expect(signals[0].prompt).toBeTruthy();
      expect(signals[0].lamp).toBe("yellow");
      expect(signals[0].targetTab).toBe("memory");
    });

    it("returns pattern count when memory exists", () => {
      const signals = derivePatInspectorSignals({ hasMemory: true, patternCount: 5 });
      expect(signals).toHaveLength(1);
      expect(signals[0].detail).toBe("5 Einträge gespeichert");
      expect(signals[0].lamp).toBe("green");
    });

    it("signal click fills prompt without auto-send", () => {
      const signals = derivePatInspectorSignals({ hasMemory: true, patternCount: 3 });
      expect(signals[0].prompt).toContain("Analysiere");
      expect(signals[0].prompt).not.toContain("Enter");
    });

    it("emits verified signal when verifiedCount > 0", () => {
      const signals = derivePatInspectorSignals({ hasMemory: true, patternCount: 5, verifiedCount: 3 });
      const verified = signals.find((s) => s.id === "pat-verified");
      expect(verified).toBeDefined();
      expect(verified!.detail).toBe("3 geprüft");
      expect(verified!.lamp).toBe("green");
    });

    it("omits verified signal when verifiedCount is 0", () => {
      const signals = derivePatInspectorSignals({ hasMemory: true, patternCount: 5, verifiedCount: 0 });
      expect(signals.find((s) => s.id === "pat-verified")).toBeUndefined();
    });

    it("emits local-executable signal when localExecutableCount > 0", () => {
      const signals = derivePatInspectorSignals({ hasMemory: true, patternCount: 5, localExecutableCount: 2 });
      const local = signals.find((s) => s.id === "pat-local");
      expect(local).toBeDefined();
      expect(local!.detail).toBe("2 lokal verfügbar");
      expect(local!.lamp).toBe("green");
    });

    it("omits local signal when localExecutableCount is 0", () => {
      const signals = derivePatInspectorSignals({ hasMemory: true, patternCount: 5, localExecutableCount: 0 });
      expect(signals.find((s) => s.id === "pat-local")).toBeUndefined();
    });

    it("emits frequently-used signal when frequentlyUsedCount > 0", () => {
      const signals = derivePatInspectorSignals({ hasMemory: true, patternCount: 5, frequentlyUsedCount: 4 });
      const frequent = signals.find((s) => s.id === "pat-frequent");
      expect(frequent).toBeDefined();
      expect(frequent!.detail).toBe("4 wiederkehrende Workflows");
    });

    it("emits all four signals when all fields are populated", () => {
      const signals = derivePatInspectorSignals({
        hasMemory: true,
        patternCount: 10,
        verifiedCount: 7,
        localExecutableCount: 5,
        frequentlyUsedCount: 3,
      });
      expect(signals.find((s) => s.id === "pat-count")).toBeDefined();
      expect(signals.find((s) => s.id === "pat-verified")).toBeDefined();
      expect(signals.find((s) => s.id === "pat-local")).toBeDefined();
      expect(signals.find((s) => s.id === "pat-frequent")).toBeDefined();
      signals.forEach((s) => expect(s.lamp).toBe("green"));
    });

    it("all signals target the memory tab", () => {
      const signals = derivePatInspectorSignals({
        hasMemory: true,
        patternCount: 5,
        verifiedCount: 2,
        localExecutableCount: 1,
        frequentlyUsedCount: 1,
      });
      signals.forEach((s) => expect(s.targetTab).toBe("memory"));
    });
  });

  /* ───────────── buildPatInspectorStateFromStore ───────────── */
  describe("buildPatInspectorStateFromStore", () => {
    it("returns hasMemory=false for empty store", () => {
      const store = createPatternMemoryStore(1000);
      const state = buildPatInspectorStateFromStore(store);
      expect(state.hasMemory).toBe(false);
      expect(state.patternCount).toBe(0);
      expect(state.verifiedCount).toBe(0);
      expect(state.localExecutableCount).toBe(0);
    });

    it("reflects actual store counts", () => {
      let store = createPatternMemoryStore(1000);
      store = addPatternEntry(store, {
        ownerScope: "local-user",
        sourceTraceId: "t1",
        title: "Fix imports",
        summary: "Remove unused TypeScript imports",
        now: 1000,
      });
      const entryId = store.entries[0].id;
      store = verifyPatternEntry(store, entryId, true, 2000);
      store = recordPatternReuse(store, entryId, 3000);
      store = recordPatternReuse(store, entryId, 4000);
      store = recordPatternReuse(store, entryId, 5000);

      const state = buildPatInspectorStateFromStore(store);
      expect(state.hasMemory).toBe(true);
      expect(state.patternCount).toBe(1);
      expect(state.verifiedCount).toBe(1);
      expect(state.localExecutableCount).toBe(1);
      expect(state.lastSuccessfulReuseAt).toBe(5000);
    });

    it("derives signals from store via the full pipeline", () => {
      let store = createPatternMemoryStore(1000);
      store = addPatternEntry(store, {
        ownerScope: "local-user",
        sourceTraceId: "t1",
        title: "Fix imports",
        summary: "Remove unused TypeScript imports",
        verified: true,
        localExecutable: true,
        now: 1000,
      });
      const state = buildPatInspectorStateFromStore(store);
      const signals = derivePatInspectorSignals(state);
      expect(signals.find((s) => s.id === "pat-count")).toBeDefined();
      expect(signals.find((s) => s.id === "pat-verified")).toBeDefined();
      expect(signals.find((s) => s.id === "pat-local")).toBeDefined();
    });
  });

  /* ───────────── ORC signals ───────────── */
  describe("deriveOrcInspectorSignals", () => {
    it("returns honest empty state when no decisions", () => {
      const signals = deriveOrcInspectorSignals({
        palDecisions: 0,
        fastTierCount: 0,
        smartTierCount: 0,
        powerTierCount: 0,
      });
      expect(signals).toHaveLength(1);
      expect(signals[0].detail).toBe("Noch keine Routing-Entscheidungen.");
      expect(signals[0].lamp).toBe("yellow");
    });

    it("shows counts by tier without percentage text", () => {
      const signals = deriveOrcInspectorSignals({
        palDecisions: 10,
        fastTierCount: 4,
        smartTierCount: 3,
        powerTierCount: 3,
      });
      expect(signals).toHaveLength(3);
      signals.forEach((s) => {
        expect(s.detail).not.toMatch(/%/);
      });
      expect(signals.find((s) => s.id === "orc-fast")?.detail).toBe("4 Entscheidungen");
      signals.forEach((s) => expect(s.lamp).toBe("green"));
    });

    it("only shows tiers with counts > 0", () => {
      const signals = deriveOrcInspectorSignals({
        palDecisions: 5,
        fastTierCount: 5,
        smartTierCount: 0,
        powerTierCount: 0,
      });
      expect(signals).toHaveLength(1);
      expect(signals[0].id).toBe("orc-fast");
    });
  });

  /* ───────────── INT signals ───────────── */
  describe("deriveIntInspectorSignals", () => {
    it("returns honest empty state when no snapshot", () => {
      const signals = deriveIntInspectorSignals({ chatRepoSnapshot: null });
      expect(signals).toHaveLength(1);
      expect(signals[0].detail).toBe("Kein Repo geladen.");
      expect(signals[0].lamp).toBe("yellow");
    });

    it("derives deterministic signals from snapshot files", () => {
      const snapshot = {
        owner: "test",
        repo: "test-repo",
        branch: "main",
        name: "test-repo",
        repoUrl: "local",
        fileCount: 42,
        files: [],
        dirs: ["src", "docs", "tests"],
        truncated: false,
      };
      const signals = deriveIntInspectorSignals({ chatRepoSnapshot: snapshot });
      expect(signals.length).toBeGreaterThanOrEqual(2);
      const folderSignal = signals.find((s) => s.id === "int-folders");
      expect(folderSignal?.detail).toContain("src · docs · tests");
      expect(folderSignal?.lamp).toBe("green");
    });

    it("shows truncated flag when snapshot is truncated", () => {
      const snapshot = {
        owner: "test",
        repo: "test-repo",
        branch: "main",
        name: "test-repo",
        repoUrl: "local",
        fileCount: 5000,
        files: [],
        dirs: [],
        truncated: true,
      };
      const signals = deriveIntInspectorSignals({ chatRepoSnapshot: snapshot });
      const fileSignal = signals.find((s) => s.id === "int-files");
      expect(fileSignal?.detail).toContain("(gekürzt)");
      expect(fileSignal?.lamp).toBe("yellow");
    });

    it("signal click fills prompt without auto-send", () => {
      const snapshot = {
        owner: "test",
        repo: "test-repo",
        branch: "main",
        name: "test-repo",
        repoUrl: "local",
        fileCount: 10,
        files: [],
        dirs: [],
        truncated: false,
      };
      const signals = deriveIntInspectorSignals({ chatRepoSnapshot: snapshot });
      signals.forEach((s) => {
        expect(s.prompt).toBeTruthy();
        expect(s.prompt).not.toMatch(/submit|send|enter/i);
      });
    });
  });

  /* ───────────── BUD signals ───────────── */
  describe("deriveBudInspectorSignals", () => {
    it("returns honest empty state when no selection result", () => {
      const state: BudInspectorState = { selectionResult: null, budgetSummary: "" };
      const signals = deriveBudInspectorSignals(state);
      expect(signals).toHaveLength(1);
      expect(signals[0].id).toBe("bud-empty");
      expect(signals[0].lamp).toBe("yellow");
      expect(signals[0].targetTab).toBe("runtime");
      expect(signals[0].prompt).toBeTruthy();
    });

    it("returns red blocked signal when all routes are exhausted", () => {
      const result: LlmRouteSelectionResult = {
        status: "blocked",
        selectedRoute: null,
        reason: "All routes exhausted.",
        exhaustedRouteIds: ["fast", "smart"],
      };
      const signals = deriveBudInspectorSignals({ selectionResult: result, budgetSummary: "Fast: 10/10 · Smart: 3/3" });
      expect(signals).toHaveLength(1);
      expect(signals[0].id).toBe("bud-blocked");
      expect(signals[0].lamp).toBe("red");
      expect(signals[0].detail).toContain("2 Route(n) erschöpft");
    });

    it("returns green signals when primary route is available", () => {
      const result: LlmRouteSelectionResult = {
        status: "available",
        selectedRoute: { id: "fast", label: "Fast Model", budgetByPlan: { free: 10 }, priority: 1 },
        reason: 'Route "Fast Model" selected.',
        exhaustedRouteIds: [],
      };
      const signals = deriveBudInspectorSignals({ selectionResult: result, budgetSummary: "Fast: 4/10" });
      expect(signals).toHaveLength(2);
      expect(signals[0].id).toBe("bud-route");
      expect(signals[0].lamp).toBe("green");
      expect(signals[0].detail).toContain("Aktiv");
      expect(signals[0].detail).toContain("Fast Model");
      expect(signals[1].id).toBe("bud-summary");
      expect(signals[1].detail).toBe("Fast: 4/10");
    });

    it("returns yellow signals when on fallback route", () => {
      const result: LlmRouteSelectionResult = {
        status: "fallback",
        selectedRoute: { id: "smart", label: "Smart Model", budgetByPlan: { free: 3 }, priority: 2 },
        reason: 'Fallback to "Smart Model" (1 route(s) exhausted).',
        exhaustedRouteIds: ["fast"],
      };
      const signals = deriveBudInspectorSignals({ selectionResult: result, budgetSummary: "Fast: 10/10 · Smart: 1/3" });
      expect(signals).toHaveLength(2);
      expect(signals[0].lamp).toBe("yellow");
      expect(signals[0].detail).toContain("Fallback");
      expect(signals[0].detail).toContain("Smart Model");
    });

    it("signals never contain percentage text", () => {
      const result: LlmRouteSelectionResult = {
        status: "available",
        selectedRoute: { id: "fast", label: "Fast Model", budgetByPlan: { free: 10 }, priority: 1 },
        reason: 'Route "Fast Model" selected.',
        exhaustedRouteIds: [],
      };
      const signals = deriveBudInspectorSignals({ selectionResult: result, budgetSummary: "Fast: 4/10" });
      signals.forEach((s) => {
        expect(s.detail).not.toMatch(/%/);
      });
    });

    it("all signals have non-empty prompts", () => {
      const result: LlmRouteSelectionResult = {
        status: "blocked",
        selectedRoute: null,
        reason: "Blocked.",
        exhaustedRouteIds: ["fast"],
      };
      const signals = deriveBudInspectorSignals({ selectionResult: result, budgetSummary: "" });
      signals.forEach((s) => {
        expect(s.prompt).toBeTruthy();
        expect(s.prompt).not.toMatch(/submit|send|enter/i);
      });
    });
  });

  /* ───────────── Combined factory ───────────── */
  describe("deriveRuntimeInspectorSignals", () => {
    it("routes to correct derivation function by panel id", () => {
      const patSignals = deriveRuntimeInspectorSignals("PAT", { hasMemory: false, patternCount: 0 }, { palDecisions: 0, fastTierCount: 0, smartTierCount: 0, powerTierCount: 0 }, { chatRepoSnapshot: null });
      expect(patSignals[0].label).toBe("Pattern Memory");

      const orcSignals = deriveRuntimeInspectorSignals("ORC", { hasMemory: false, patternCount: 0 }, { palDecisions: 0, fastTierCount: 0, smartTierCount: 0, powerTierCount: 0 }, { chatRepoSnapshot: null });
      expect(orcSignals[0].label).toBe("PAL Router");

      const intSignals = deriveRuntimeInspectorSignals("INT", { hasMemory: false, patternCount: 0 }, { palDecisions: 0, fastTierCount: 0, smartTierCount: 0, powerTierCount: 0 }, { chatRepoSnapshot: null });
      expect(intSignals[0].label).toBe("Repo Kontext");
    });

    it("routes BUD panel to budget signals", () => {
      const budState: BudInspectorState = { selectionResult: null, budgetSummary: "" };
      const budSignals = deriveRuntimeInspectorSignals("BUD", { hasMemory: false, patternCount: 0 }, { palDecisions: 0, fastTierCount: 0, smartTierCount: 0, powerTierCount: 0 }, { chatRepoSnapshot: null }, budState);
      expect(budSignals[0].label).toBe("LLM Budget");
    });

    it("uses empty budget state when budState is omitted for BUD panel", () => {
      const budSignals = deriveRuntimeInspectorSignals("BUD", { hasMemory: false, patternCount: 0 }, { palDecisions: 0, fastTierCount: 0, smartTierCount: 0, powerTierCount: 0 }, { chatRepoSnapshot: null });
      expect(budSignals[0].id).toBe("bud-empty");
    });
  });

  /* ───────────── Integration with quietInspectorHintPolicy ───────────── */
  describe("toQuietInspectorSignal", () => {
    it("converts RuntimeInspectorSignal to QuietInspectorSignal format", () => {
      const signal = derivePatInspectorSignals({ hasMemory: true, patternCount: 5 })[0];
      const quiet = toQuietInspectorSignal(signal, "builder-container");
      
      expect(quiet.id).toBe(signal.id);
      expect(quiet.source).toBe("builder-container");
      expect(quiet.lamp).toBe(signal.lamp);
      expect(quiet.message).toBe(`${signal.label}: ${signal.detail}`);
      expect(quiet.targetTab).toBe(signal.targetTab);
      expect(quiet.visible).toBe(true);
      expect(quiet.updatedAt).toBeGreaterThan(0);
    });
  });
});
