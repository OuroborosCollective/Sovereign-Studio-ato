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

const ARCH_KW = [
  "architektur", "architecture", "refactor", "redesign",
  "migration", "pattern", "dependency", "abstraction",
  "interface", "contract",
];
const PLAN_KW = [
  "plan", "planung", "roadmap", "strategie", "feature",
  "implement", "konzept", "vorschlag", "analyse", "überblick",
];
const QUICK_KW = [
  "kurz", "quick", "schnell", "simple", "einfach",
  "was ist", "what is", "define", "erkläre", "explain", "tipp",
];
const THINK_KW = [
  "denk nach", "think", "tiefgründig", "trade-off",
  "kompromiss", "komplexität", "algorithmus", "optimiere",
];

export function palRoute(
  message: string,
  histDepth: number,
  fileCount: number,
  prior: PALDecision[],
): PALDecision {
  const lower = message.toLowerCase();
  let score = 0;
  const len = message.length;
  if (len >= 300) score += 15;
  else if (len >= 150) score += 10;
  else if (len >= 60) score += 5;
  score += Math.min(((message.match(/```/g) ?? []).length / 2) * 5, 15);
  if (fileCount > 0) score += 10;
  if (ARCH_KW.some((k) => lower.includes(k))) score += 20;
  if (THINK_KW.some((k) => lower.includes(k))) score += 18;
  if (PLAN_KW.some((k) => lower.includes(k))) score += 12;
  if (QUICK_KW.some((k) => lower.includes(k))) score -= 15;
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
  // Models verified live 2026-07-02: deepseek-r1, mistral-7b, llama-3.1-8b only.
  // llama-3-8b deprecated; qwen-14b and gemma-7b have no Worker route.
  const tierModelMap: Record<string, string[]> = {
    fast:  ["llama-3.1-8b", "mistral-7b"],
    smart: ["mistral-7b",   "llama-3.1-8b"],
    power: ["deepseek-r1",  "mistral-7b"],
  };
  const matched =
    DEV_CHAT_WORKER_MODELS.find((m) => tierModelMap[tier].includes(m.id)) ??
    DEV_CHAT_WORKER_MODELS[0];
  const costMap = { fast: 1, smart: 10, power: 30 };
  return {
    tier,
    modelId: matched?.id ?? "llama-3-8b",
    modelLabel: matched?.label ?? "Llama 3 8B",
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
