/**
 * Runtime Inspector Panel Runtime — Issue #433 / #446
 * Derives real runtime signals for PAT, ORC, INT, BUD modules from live state.
 * Integrates with quietInspectorHintPolicy.ts for unified signal format.
 * No fake state, no percentages, no dashboard.
 */

import type { DevChatRepoSnapshot } from "./devChatWorkerBridge";
import { type QuietInspectorSignal, type QuietInspectorLamp, type QuietInspectorTarget } from "./quietInspectorHintPolicy";
import type { LlmRouteSelectionResult } from "./llmRouteBudgetRuntime";

export type RuntimeInspectorPanelId = "PAT" | "ORC" | "INT" | "BUD";

export interface RuntimeInspectorSignal {
  readonly id: string;
  readonly label: string;
  readonly detail: string;
  readonly prompt: string;
  readonly lamp: QuietInspectorLamp;
  readonly targetTab: QuietInspectorTarget;
}

// Helper to convert RuntimeInspectorSignal to QuietInspectorSignal
export function toQuietInspectorSignal(
  signal: RuntimeInspectorSignal,
  source: string,
): QuietInspectorSignal {
  return {
    id: signal.id,
    source,
    lamp: signal.lamp,
    message: `${signal.label}: ${signal.detail}`,
    targetTab: signal.targetTab,
    visible: true,
    updatedAt: Date.now(),
  };
}

// ─────────────────────────────────────────────────────────────
// PAT — Pattern Memory signals
// ─────────────────────────────────────────────────────────────

export interface PatInspectorState {
  readonly hasMemory: boolean;
  readonly patternCount: number;
}

export function derivePatInspectorSignals(state: PatInspectorState): RuntimeInspectorSignal[] {
  if (!state.hasMemory) {
    return [
      {
        id: "pat-empty",
        label: "Pattern Memory",
        detail: "Keine Pattern-Memory sichtbar.",
        prompt: "Zeige mir die aktuellen Pattern-Memory-Einträge.",
        lamp: "yellow" as const,
        targetTab: "memory" as const,
      },
    ];
  }

  return [
    {
      id: "pat-count",
      label: "Pattern Memory",
      detail: `${state.patternCount} Einträge gespeichert`,
      prompt: `Analysiere die ${state.patternCount} gespeicherten Patterns.`,
      lamp: "green" as const,
      targetTab: "memory" as const,
    },
  ];
}

// ─────────────────────────────────────────────────────────────
// ORC — PAL Router signals by tier
// ─────────────────────────────────────────────────────────────

export interface OrcInspectorState {
  readonly palDecisions: number;
  readonly fastTierCount: number;
  readonly smartTierCount: number;
  readonly powerTierCount: number;
}

export function deriveOrcInspectorSignals(state: OrcInspectorState): RuntimeInspectorSignal[] {
  const signals: RuntimeInspectorSignal[] = [];

  if (state.palDecisions === 0) {
    return [
      {
        id: "orc-empty",
        label: "PAL Router",
        detail: "Noch keine Routing-Entscheidungen.",
        prompt: "Zeige mir die PAL Router Statistiken.",
        lamp: "yellow" as const,
        targetTab: "runtime" as const,
      },
    ];
  }

  if (state.fastTierCount > 0) {
    signals.push({
      id: "orc-fast",
      label: "Fast Tier",
      detail: `${state.fastTierCount} Entscheidungen`,
      prompt: `Erkläre die ${state.fastTierCount} Fast-Tier-Routings.`,
      lamp: "green" as const,
      targetTab: "runtime" as const,
    });
  }

  if (state.smartTierCount > 0) {
    signals.push({
      id: "orc-smart",
      label: "Smart Tier",
      detail: `${state.smartTierCount} Entscheidungen`,
      prompt: `Analysiere die ${state.smartTierCount} Smart-Tier-Routings.`,
      lamp: "green" as const,
      targetTab: "runtime" as const,
    });
  }

  if (state.powerTierCount > 0) {
    signals.push({
      id: "orc-power",
      label: "Power Tier",
      detail: `${state.powerTierCount} Entscheidungen`,
      prompt: `Review die ${state.powerTierCount} Power-Tier-Routings.`,
      lamp: "green" as const,
      targetTab: "runtime" as const,
    });
  }

  return signals;
}

// ─────────────────────────────────────────────────────────────
// INT — Repo Inspector signals from snapshot
// ─────────────────────────────────────────────────────────────

export interface IntInspectorState {
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
}

export function deriveIntInspectorSignals(state: IntInspectorState): RuntimeInspectorSignal[] {
  if (!state.chatRepoSnapshot) {
    return [
      {
        id: "int-empty",
        label: "Repo Kontext",
        detail: "Kein Repo geladen.",
        prompt: "Lade ein GitHub Repo mit /repo <URL>",
        lamp: "yellow" as const,
        targetTab: "repo" as const,
      },
    ];
  }

  const snapshot = state.chatRepoSnapshot;
  const signals: RuntimeInspectorSignal[] = [];

  // Top-level folder count
  if (snapshot.dirs.length > 0) {
    signals.push({
      id: "int-folders",
      label: "Top-Level Ordner",
      detail: snapshot.dirs.slice(0, 5).join(" · ") + (snapshot.dirs.length > 5 ? " · …" : ""),
      prompt: `Analysiere die ${snapshot.dirs.length} Top-Level Ordner.`,
      lamp: "green" as const,
      targetTab: "repo" as const,
    });
  }

  // File count
  signals.push({
    id: "int-files",
    label: "Dateien",
    detail: `${snapshot.fileCount} Dateien${snapshot.truncated ? " (gekürzt)" : ""}`,
    prompt: `Zeige mir die Dateistruktur von ${snapshot.name}.`,
    lamp: snapshot.truncated ? ("yellow" as const) : ("green" as const),
    targetTab: "repo" as const,
  });

  // Branch info
  signals.push({
    id: "int-branch",
    label: "Branch",
    detail: snapshot.branch,
    prompt: `Erkläre die Änderungen auf Branch ${snapshot.branch}.`,
    lamp: "green" as const,
    targetTab: "repo" as const,
  });

  return signals;
}

// ─────────────────────────────────────────────────────────────
// BUD — LLM Route Budget signals
// ─────────────────────────────────────────────────────────────

export interface BudInspectorState {
  readonly selectionResult: LlmRouteSelectionResult | null;
  /** Human-readable budget summary line (e.g. from summarizeLlmBudgetState). */
  readonly budgetSummary: string;
}

export function deriveBudInspectorSignals(state: BudInspectorState): RuntimeInspectorSignal[] {
  if (!state.selectionResult) {
    return [
      {
        id: "bud-empty",
        label: "LLM Budget",
        detail: "Kein Budget-Status verfügbar.",
        prompt: "Zeige mir den aktuellen LLM-Routen-Status.",
        lamp: "yellow" as const,
        targetTab: "runtime" as const,
      },
    ];
  }

  const { selectionResult: result, budgetSummary } = state;

  if (result.status === "blocked") {
    return [
      {
        id: "bud-blocked",
        label: "LLM Budget",
        detail: `Blockiert — ${result.exhaustedRouteIds.length} Route(n) erschöpft.`,
        prompt: "Zeige mir welche LLM-Routen erschöpft sind und wie ich weitermachen kann.",
        lamp: "red" as const,
        targetTab: "runtime" as const,
      },
    ];
  }

  const lamp: QuietInspectorLamp = result.status === "fallback" ? "yellow" : "green";
  const routeLabel = result.selectedRoute?.label ?? "—";
  const statusLabel = result.status === "fallback" ? "Fallback" : "Aktiv";

  return [
    {
      id: "bud-route",
      label: "LLM Budget",
      detail: `${statusLabel}: ${routeLabel}`,
      prompt: `Zeige mir den Budget-Status für Route "${routeLabel}".`,
      lamp,
      targetTab: "runtime" as const,
    },
    {
      id: "bud-summary",
      label: "Routen-Übersicht",
      detail: budgetSummary,
      prompt: "Erkläre mir den aktuellen Verbrauch aller LLM-Routen.",
      lamp,
      targetTab: "runtime" as const,
    },
  ];
}

// ─────────────────────────────────────────────────────────────
// Combined factory
// ─────────────────────────────────────────────────────────────

export function deriveRuntimeInspectorSignals(
  panelId: RuntimeInspectorPanelId,
  patState: PatInspectorState,
  orcState: OrcInspectorState,
  intState: IntInspectorState,
  budState?: BudInspectorState,
): RuntimeInspectorSignal[] {
  switch (panelId) {
    case "PAT":
      return derivePatInspectorSignals(patState);
    case "ORC":
      return deriveOrcInspectorSignals(orcState);
    case "INT":
      return deriveIntInspectorSignals(intState);
    case "BUD":
      return deriveBudInspectorSignals(budState ?? { selectionResult: null, budgetSummary: "" });
    default:
      return [];
  }
}
