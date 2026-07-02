/**
 * Chat message builder helpers for BuilderContainer.
 * Extracted from BuilderContainer.tsx (Audit P2, 2026-07-02).
 *
 * Pure functions: no React imports, no side effects.
 */
import {
  explainDevChatWorkerDiagnostic,
  summarizeDevChatRepoSnapshot,
  parseDevChatGithubUrl,
  type DevChatRepoSnapshot,
  type DevChatWorkerMessage,
} from "./devChatWorkerBridge";
import { splitFilePath } from "./builderContainerHelpers";
import {
  detectAndroidQuickRepoUrl,
} from "./androidQuickInteractionRuntime";
import {
  isOpenHandsExecutionIntent,
  isWorkerRetryIntent,
} from "./workerIntentDetector";
import type { OpenHandsJobSnapshot } from "./openhandsEnterpriseRuntime";
import type {
  AnimPhase,
  ChatLine,
  ChatRole,
  ModuleCond,
  SignalType,
  WorkerRuntimeBlocker,
} from "./builderContainerTypes";

// ─────────────────────────────────────────────────────────────
// Chat line builders
// ─────────────────────────────────────────────────────────────

export function buildChatLines(args: {
  readonly repoReady: boolean;
  readonly repoReason: string;
  readonly runtimeThinkingActive: boolean;
  readonly cuteThinkingLabel: string;
  readonly sovereignSummary: string;
  readonly disabledReason?: string;
  readonly openhandsJob?: OpenHandsJobSnapshot;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
  readonly chatRepoError: string | null;
  readonly chatHistory: readonly ChatLine[];
}): ChatLine[] {
  const lines: ChatLine[] = [];
  const firstFile = splitFilePath(
    args.openhandsJob?.changedFiles?.[0] ?? args.chatRepoSnapshot?.lastFile,
  );
  const effectiveRepoReady = args.repoReady || Boolean(args.chatRepoSnapshot);

  lines.push({
    id: "system:repo",
    role: "system",
    text: effectiveRepoReady
      ? `Repo verbunden · ${args.chatRepoSnapshot ? summarizeDevChatRepoSnapshot(args.chatRepoSnapshot) : "echte Runtime-Gates aktiv"}`
      : `Repo fehlt · ${args.repoReason}`,
  });

  if (args.chatRepoError)
    lines.push({
      id: "system:repo-error",
      role: "system",
      text: `Repo-Ladefehler: ${args.chatRepoError}`,
    });
  if (args.sovereignSummary.trim())
    lines.push({
      id: "assistant:summary",
      role: "assistant",
      text: args.sovereignSummary.trim(),
      ...firstFile,
    });

  lines.push(...args.chatHistory);

  if (
    args.cuteThinkingLabel.trim() &&
    (args.runtimeThinkingActive ||
      args.chatHistory.length > 0 ||
      args.chatRepoSnapshot ||
      args.disabledReason?.trim())
  ) {
    lines.push({
      id: "thought:runtime",
      role: "thought",
      text: args.cuteThinkingLabel,
    });
  }

  if (args.disabledReason?.trim())
    lines.push({
      id: "system:blocked",
      role: "system",
      text: args.disabledReason.trim(),
    });
  return lines;
}

export function createChatLineId(
  prefix: ChatRole | "repo" | "worker",
  index: number,
): string {
  return `${prefix}:${Date.now()}:${index}`;
}

// ─────────────────────────────────────────────────────────────
// Worker message builders
// ─────────────────────────────────────────────────────────────

export function buildWorkerSystemPrompt(args: {
  readonly repoReady: boolean;
  readonly repoReason: string;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
  readonly toolchainContext?: string;
}): string {
  const repoContext = args.chatRepoSnapshot
    ? [
        `Repo: ${args.chatRepoSnapshot.owner}/${args.chatRepoSnapshot.repo}`,
        `Branch: ${args.chatRepoSnapshot.branch}`,
        `Dateien: ${args.chatRepoSnapshot.fileCount}`,
        `Top-Level: ${args.chatRepoSnapshot.dirs.join(" · ") || "keine Top-Level-Ordner erkannt"}`,
        `Letzter relevanter Pfad: ${[args.chatRepoSnapshot.lastPath, args.chatRepoSnapshot.lastFile].filter(Boolean).join("") || "nicht erkannt"}`,
      ].join("\n")
    : args.repoReady
      ? `Repo-Kontext: ${args.repoReason}`
      : `Repo-Kontext fehlt: ${args.repoReason}`;

  return [
    "Du bist Sovereign Worker Chat, die Standard-LLM-Route des Sovereign Tools.",
    "Antworte kurz, freundlich, konkret und ohne erfundene Erfolge.",
    "Keine Mock-, Stub- oder Facade-Live-Pfade behaupten.",
    "Wenn Code-Ausführung oder Draft-PR nötig ist, erkläre klar, dass OpenHands der Executor ist.",
    repoContext,
    args.toolchainContext || "",
  ].filter(Boolean).join("\n");
}

export function buildWorkerMessages(args: {
  readonly submittedText: string;
  readonly chatHistory: readonly ChatLine[];
  readonly repoReady: boolean;
  readonly repoReason: string;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
  readonly toolchainContext?: string;
}): DevChatWorkerMessage[] {
  const recentMessages = args.chatHistory
    .filter((line) => line.role === "user" || line.role === "assistant")
    .slice(-8)
    .map((line): DevChatWorkerMessage => ({
      role: line.role === "user" ? "user" : "assistant",
      content: line.text,
    }));

  return [
    { role: "system", content: buildWorkerSystemPrompt(args) },
    ...recentMessages,
    { role: "user", content: args.submittedText },
  ];
}

export function buildWorkerBlockerAnswer(args: {
  readonly blocker: WorkerRuntimeBlocker;
  readonly repoReady: boolean;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
  readonly openhandsReady?: boolean;
}): string {
  const { diagnostic, health } = args.blocker;
  const repoLine = args.chatRepoSnapshot
    ? `Repo-Kontext bleibt geladen: ${args.chatRepoSnapshot.owner}/${args.chatRepoSnapshot.repo} · ${args.chatRepoSnapshot.branch} · ${args.chatRepoSnapshot.fileCount} files.`
    : args.repoReady
      ? "Repo-Kontext ist weiterhin bereit."
      : "Repo-Kontext fehlt noch.";
  const healthLine = health
    ? `Health: ${health.status ?? "n/a"} · secret=${health.secretConfigured === undefined ? "unbekannt" : health.secretConfigured ? "ok" : "fehlt"} · upstream=${health.upstreamConfigured === undefined ? "unbekannt" : health.upstreamConfigured ? "ok" : "fehlt"} · model=${health.model ?? diagnostic.model}.`
    : "Health: noch nicht geprüft.";
  const codeLine = diagnostic.canClientFix
    ? "Einschätzung: Der Fehler ist wahrscheinlich durch unseren App-Request oder die Route im Code korrigierbar."
    : "Einschätzung: Der letzte Fehler liegt wahrscheinlich in Worker-Konfiguration, Worker-Runtime oder Upstream-Provider und muss über Cloudflare/Bridge-Diagnose geprüft werden.";

  return [
    "Ich wiederhole den kaputten Worker-Call nicht blind.",
    explainDevChatWorkerDiagnostic(diagnostic),
    healthLine,
    repoLine,
    args.openhandsReady
      ? "OpenHands Executor ist nur für echte Code-/Draft-PR-Aufträge zuständig und wurde für diese Chatfrage nicht gestartet."
      : "OpenHands Executor ist nicht bereit; normale Chatfragen bleiben Worker-Route.",
    codeLine,
  ].join("\n");
}

// ─────────────────────────────────────────────────────────────
// UI hint helpers
// ─────────────────────────────────────────────────────────────

export function composerRouteHint(args: {
  readonly draft: string;
  readonly workerBlocked: boolean;
  readonly agentDisabled: boolean;
}): string {
  const clean = args.draft.trim();
  if (!clean)
    return "Worker Chat senden · Repo-URL laden · OpenHands nur bei Code-Auftrag";
  const quickRepo = detectAndroidQuickRepoUrl(clean);
  if (quickRepo.recognized) return quickRepo.hint;
  if (parseDevChatGithubUrl(clean)) return "Repo laden · Runtime Snapshot";
  if (isOpenHandsExecutionIntent(clean))
    return args.agentDisabled
      ? "OpenHands blockiert · Worker erklärt zuerst"
      : "OpenHands Executor starten";
  if (args.workerBlocked && !isWorkerRetryIntent(clean))
    return "Worker blockiert · lokale Diagnose statt blindem Retry";
  if (args.workerBlocked && isWorkerRetryIntent(clean))
    return "Worker Retry · Diagnose wird aktualisiert";
  return "Worker Chat senden · Enter senden · Shift+Enter Zeilenumbruch";
}

// ─────────────────────────────────────────────────────────────
// Pure scoring/phase helpers
// ─────────────────────────────────────────────────────────────

export function confidenceLabel(value: number): string {
  if (value >= 0.65) return "stable";
  if (value >= 0.35) return "watch";
  return "low";
}

export function phaseFromSignalAndConditions(
  signal: SignalType,
  conds: readonly ModuleCond[],
): AnimPhase {
  if (signal === "error" || conds.some((c) => c.status === "fail")) return "error";
  if (signal === "processing") return "working";
  if (conds.some((c) => c.status === "wait")) return signal === "idle" ? "idle" : "working";
  if (signal === "warning") return "working";
  if (signal === "active") return "done";
  return "idle";
}

export function sameRecord<T extends string>(
  a: Record<string, T>,
  b: Record<string, T>,
): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if (a[key] !== b[key]) return false;
  }
  return true;
}

export function sameConditions(
  a: Partial<Record<string, ModuleCond[]>>,
  b: Partial<Record<string, ModuleCond[]>>,
): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function buildRuntimeConfidence(args: {
  readonly effectiveRepoReady: boolean;
  readonly openhandsReady?: boolean;
  readonly runtimeThinkingActive: boolean;
  readonly blocked: boolean;
  readonly palDecisions: number;
  readonly outcomeHints: number;
}): number {
  let score = 0.12;
  if (args.effectiveRepoReady) score += 0.22;
  if (args.openhandsReady) score += 0.2;
  if (args.runtimeThinkingActive) score += 0.12;
  if (args.palDecisions > 0) score += 0.12;
  if (args.outcomeHints > 0) score += 0.1;
  if (args.blocked) score -= 0.18;
  return Math.max(0, Math.min(1, score));
}
