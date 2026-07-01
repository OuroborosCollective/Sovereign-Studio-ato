import { describe, expect, it } from "vitest";
import {
  deriveIntInspectorSignals,
  deriveOrcInspectorSignals,
  derivePatInspectorSignals,
  deriveBudInspectorSignals,
  deriveRuntimeInspectorSignals,
  toQuietInspectorSignal,
  type BudInspectorState,
} from "./runtimeInspectorPanelRuntime";
import type { LlmRouteSelectionResult } from "./llmRouteBudgetRuntime";

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
