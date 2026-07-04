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
// Write intent detection (Aufgabe 1)
// ─────────────────────────────────────────────────────────────

// Keywords that mark a message as a WRITE INTENT: the user wants Sovereign
// to change a real file/repo state (README, docs, code, commit, PR, ...).
// Kept deliberately broad (German-first) — false positives are safer than
// silently treating a write request as free chat/advice.
const WRITE_INTENT_TOKENS = [
  "readme ändern",
  "readme anpassen",
  "dokumentation ändern",
  "dokumentation anpassen",
  "datei ändern",
  "titel ändern",
  "füge hinzu",
  "fuege hinzu",
  "ergänze",
  "ergaenze",
  "ersetze",
  "patch",
  "diff",
  "commit",
  "push",
  "draft pr",
  "draft-pr",
  "pull request",
  "mach das ins repo",
  "ändere im repo",
  "aendere im repo",
  "bau das ein",
  "setze das um",
  "setz das um",
  "implementiere",
  "passe an",
  "passe die",
  "passe das",
];

// Regex covers the "passe ... an" pattern (separable German verb) explicitly,
// since the token list alone cannot match arbitrary infixes.
const PASSE_AN_PATTERN = /\bpasse\b.*\ban\b/i;

/**
 * Detects if a message is a WRITE INTENT: the user wants a real file/repo
 * change (README, docs, code, patch, commit, push, draft PR, ...).
 * Write intents must never be treated as normal advisory chat — they require
 * a loaded repo and verified GitHub write access before any executor route.
 */
export function isWriteIntent(text: string): boolean {
  const lower = text.toLowerCase();
  if (WRITE_INTENT_TOKENS.some((token) => lower.includes(token))) return true;
  return PASSE_AN_PATTERN.test(lower);
}

// ─────────────────────────────────────────────────────────────
// Local completion status questions (Aufgabe 2)
// ─────────────────────────────────────────────────────────────

const LOCAL_STATUS_QUESTION_TOKENS = [
  "bist du fertig",
  "schon fertig",
  "ist das erledigt",
  "hast du es geändert",
  "hast du es geaendert",
  "wurde es gepusht",
  "gibt es einen draft pr",
  "wo ist der patch",
  "warum passiert nichts",
  "was ist der status",
];

/**
 * Detects local completion-status questions ("bist du fertig?", "wo ist der
 * patch?", ...). These must be answered locally from runtime state and must
 * NEVER be forwarded to the Worker as a new request.
 */
export function isLocalCompletionStatusQuestion(text: string): boolean {
  const lower = text.toLowerCase();
  return LOCAL_STATUS_QUESTION_TOKENS.some((token) => lower.includes(token));
}

export interface LocalStatusAnswerArgs {
  readonly githubWriteAllowed: boolean;
  readonly writeIntentBlockedByRepo: boolean;
  readonly openhandsRunning: boolean;
  readonly draftPrUrl?: string | null;
  readonly hasPatch: boolean;
  readonly hasWorkerResponse: boolean;
  readonly workerBlocker?: WorkerRuntimeBlocker | null;
  readonly buildWorkerBlockerAnswer?: () => string;
}

/**
 * Builds a truthful, German, local answer for a completion-status question
 * from real runtime state. Never fabricates success. Priority order:
 * draft PR ready > patch generated > OpenHands running > worker blocked >
 * GitHub access missing > worker-answer-only > nothing happened yet.
 */
export function buildLocalStatusAnswer(args: LocalStatusAnswerArgs): string {
  if (args.draftPrUrl) {
    return `Ja, Draft PR ist bereit: ${args.draftPrUrl}`;
  }
  if (args.hasPatch) {
    return "Ja, ein Patch/Diff wurde erzeugt. Draft PR steht noch aus.";
  }
  if (args.openhandsRunning) {
    return "Noch nicht. OpenHands arbeitet noch.";
  }
  if (args.workerBlocker) {
    return args.buildWorkerBlockerAnswer
      ? args.buildWorkerBlockerAnswer()
      : "Nein. Der Worker ist blockiert. Es gibt noch keine Änderung.";
  }
  if (args.writeIntentBlockedByRepo) {
    return "Nein. Der Schreibauftrag ist blockiert, weil zuerst ein GitHub-Repo geladen werden muss.";
  }
  if (!args.githubWriteAllowed) {
    return "Nein. Der Schreibauftrag ist blockiert, weil sicherer GitHub-Zugang fehlt.";
  }
  if (args.hasWorkerResponse) {
    return "Nein. Es wurde bisher nur eine Worker-Antwort erzeugt. Es gibt noch keinen Patch, keinen Diff und keinen Draft PR.";
  }
  return "Nein. Es wurde bisher noch kein Auftrag gestartet.";
}

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
  readonly userLanguage?: string;
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
    "Du bist Sovereign Studio Runtime Coach — kein generischer Chatbot.",
    "Antworte in der Sprache des Users. Bei deutschen Eingaben deutsch antworten.",
    "Antworte kurz, freundlich, konkret und ohne erfundene Erfolge.",
    "Keine Mock-, Stub- oder Facade-Live-Pfade behaupten.",
    "Wenn nach UI/UX gefragt wird: konkrete Beobachtungen und nächste Schritte — keine Figma-Floskeln.",
    "Sage nicht 'I don’t have the ability', wenn du sinnvoll beraten kannst.",
    "Wenn der User eine Datei-, Repo-, README-, Code-, Patch-, Commit- oder Draft-PR-Änderung will:",
    "  1. Sage klar, dass OpenHands/Draft-PR der Executor ist.",
    "  2. Bereite einen kompakten Ausführungsbrief vor (Mission, Ziel, Scope).",
    "  3. Biete NICHT an, das direkt selbst zu machen — das ist nicht dein Job.",
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
