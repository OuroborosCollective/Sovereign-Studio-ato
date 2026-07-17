/**
 * PAL (Prompt Adaptive LLM) routing runtime for BuilderContainer.
 * Extracted from BuilderContainer.tsx (Audit P2, 2026-07-02).
 *
 * Decides which model tier (fast / smart / power) to use based on
 * message complexity, history depth, and file context.
 * Pure function: no React imports, no side effects.
 */
import {
  DEV_CHAT_WORKER_MODELS,
} from "./devChatWorkerBridge";
import {
  createRouteRegistry,
  createUserPlanState,
  selectLlmRoute,
  summarizeLlmBudgetState,
  type LlmBudgetLedger,
} from "./llmRouteBudgetRuntime";
import type { BudInspectorState } from "./runtimeInspectorPanelRuntime";

export interface PALDecision {
  tier: "fast" | "smart" | "power";
  modelId: string;
  modelLabel: string;
  score: number;
  costFactor: number;
}

export function palRoute(
  message: string,
  histDepth: number,
  fileCount: number,
  prior: PALDecision[],
): PALDecision {
  // Structural scoring only — no keyword/semantic analysis here.
  // The LLM (Brain) handles semantic complexity; this module handles
  // structural signals: message length, code blocks, context depth.
  // Keyword-based scoring (ARCH_KW, PLAN_KW, THINK_KW, QUICK_KW) has been removed.
  let score = 0;
  const len = message.length;
  if (len >= 300) score += 15;
  else if (len >= 150) score += 10;
  else if (len >= 60) score += 5;
  score += Math.min(((message.match(/```/g) ?? []).length / 2) * 5, 15);
  if (fileCount > 0) score += 10;
  if (histDepth > 10) score += 5;
  score = Math.max(0, Math.min(100, score));
  const powerCount = prior.filter((d) => d.tier === "power").length;
  const tier: "fast" | "smart" | "power" =
    score <= 33
      ? "fast"
      : score <= 66
        ? "smart"
        : powerCount >= 10
          ? "smart"
          : "power";
  // PAL chooses only abstract LiteLLM aliases. The backend resolves the actual
  // provider/model deployment from its active route catalog.
  const tierAliasMap: Record<string, string> = {
    fast: "sovereign-fast",
    smart: "sovereign-balanced",
    power: "sovereign-balanced",
  };
  const matched =
    DEV_CHAT_WORKER_MODELS.find((model) => model.id === tierAliasMap[tier]) ??
    DEV_CHAT_WORKER_MODELS[0];
  const costMap = { fast: 1, smart: 10, power: 30 };
  return {
    tier,
    modelId: matched?.id ?? "sovereign-fast",
    modelLabel: matched?.label ?? "Sovereign Fast",
    score,
    costFactor: costMap[tier],
  };
}

// ─────────────────────────────────────────────────────────────
// Budget ledger wiring (session-scoped, mirrors PAL tiers)
// ── Issue #446: Real LlmBudgetLedger wiring — routes mirror PAL tiers.
// Budget is unbounded (Infinity) in this session plan, but actual used
// counts come from the real Ledger state.
// ─────────────────────────────────────────────────────────────

export const BUD_REGISTRY = createRouteRegistry([
  { id: "fast",  label: "Fast",  budgetByPlan: { session: Infinity }, priority: 1 },
  { id: "smart", label: "Smart", budgetByPlan: { session: Infinity }, priority: 2 },
  { id: "power", label: "Power", budgetByPlan: { session: Infinity }, priority: 3 },
]);
export const BUD_PLAN = createUserPlanState("session", ["fast", "smart", "power"]);

export function deriveBudFromLedger(ledger: LlmBudgetLedger): BudInspectorState {
  const selectionResult = selectLlmRoute(BUD_REGISTRY, BUD_PLAN, ledger);
  const budgetSummary   = summarizeLlmBudgetState(BUD_REGISTRY, BUD_PLAN, ledger);
  return { selectionResult, budgetSummary };
}
