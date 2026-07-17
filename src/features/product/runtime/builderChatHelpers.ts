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
  isSovereignAgentExecutionIntent,
  isWorkerRetryIntent,
} from "./workerIntentDetector";
import type { SovereignAgentJobSnapshot } from "./sovereignAgentRuntime";
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

/**
 * Reports whether a user message is a WRITE INTENT: the user wants a real
 * file/repo change (README, docs, code, patch, commit, push, draft PR, ...).
 *
 * Architectural rule: semantic write-intent classification is the LLM's job.
 * Pass the LLM-declared result via `explicit`. When `explicit` is not provided,
 * this function returns `false` — the runtime must NOT pre-parse natural language.
 *
 * Write intents must never be treated as normal advisory chat — they require
 * a loaded repo and verified GitHub write access before any executor route.
 *
 * @param _text  Original message (reserved for future structural checks; unused).
 * @param explicit  LLM-declared classification: true = write intent, false = not.
 *                  Omit until the LLM layer provides an explicit value.
 */
export function isWriteIntent(_text: string, explicit?: boolean): boolean {
  if (explicit !== undefined) return explicit;
  // Keyword-based pre-classification has been removed. Default to false so that
  // no message is silently blocked before the LLM has a chance to classify it.
  return false;
}

// ─────────────────────────────────────────────────────────────
// Local completion status questions (Aufgabe 2)
// ─────────────────────────────────────────────────────────────

/**
 * Reports whether a message is a local completion-status question ("bist du fertig?",
 * "wo ist der patch?", ...). These should be answered from runtime state and must
 * NEVER be forwarded to the Worker as a new request.
 *
 * Architectural rule: semantic classification is the LLM's job.
 * Pass the LLM-declared result via `explicit`. When `explicit` is not provided,
 * this function returns `false` — the runtime must NOT pre-parse natural language.
 *
 * @param _text  Original message (reserved for future structural checks; unused).
 * @param explicit  LLM-declared classification: true = is a status question.
 */
export function isLocalCompletionStatusQuestion(_text: string, explicit?: boolean): boolean {
  if (explicit !== undefined) return explicit;
  // Keyword-based pre-classification has been removed. Return false so messages
  // are not intercepted before the LLM classifies them.
  return false;
}

/**
 * Reports whether the question asks if the Sovereign Agent has STARTED (not if it's done).
 * For these questions, "Ja, Sovereign Agent läuft" is the expected runtime answer.
 *
 * Architectural rule: semantic classification is the LLM's job.
 * Pass the LLM-declared result via `explicit`. Default is false.
 *
 * @param _text  Original message (reserved for future structural checks; unused).
 * @param explicit  LLM-declared classification: true = startup question.
 */
export function isStartupQuestion(_text: string, explicit?: boolean): boolean {
  if (explicit !== undefined) return explicit;
  return false;
}

export interface LocalStatusAnswerArgs {
  readonly githubWriteAllowed: boolean;
  readonly githubAccessState?: string;
  readonly writeIntentBlockedByRepo: boolean;
  readonly agentRunning: boolean;
  readonly draftPrUrl?: string | null;
  readonly hasPatch: boolean;
  /** True when a Direct GitHub Patch preview has been generated but not yet applied/committed */
  readonly patchPreviewReady?: boolean;
  /** True when the patch preview was applied and the draft PR was created */
  readonly patchConfirmed?: boolean;
  readonly hasWorkerResponse: boolean;
  readonly workerBlocker?: WorkerRuntimeBlocker | null;
  readonly buildWorkerBlockerAnswer?: () => string;
  /** Optional question text to determine if this is a startup question */
  readonly questionText?: string;
}

/**
 * Builds a truthful, German, local answer for a completion-status question
 * from real runtime state. Never fabricates success. Priority order:
 * - For startup questions ("arbeitet er schon?", ...): Sovereign Agent running status first
 * - For completion questions: draft PR ready > patch generated > Sovereign Agent running
 * - Then: worker blocked > GitHub access missing > worker-answer-only > nothing happened yet
 *
 * For startup questions ("arbeitet er schon?", "läuft er?", ...), returns
 * "Ja, Sovereign Agent läuft" when the Sovereign Agent is running. For completion questions
 * ("ist er fertig?", "bist du fertig?", ...), returns "Noch nicht..." when
 * the Sovereign Agent is still running.
 */
export function buildLocalStatusAnswer(args: LocalStatusAnswerArgs): string {
  // Startup questions get priority: "Is the Sovereign Agent running?" must answer that directly
  if (args.questionText && isStartupQuestion(args.questionText) && args.agentRunning) {
    return "Ja, Sovereign Agent läuft.";
  }

  if (args.draftPrUrl) {
    return `Ja, Draft PR ist bereit: ${args.draftPrUrl}`;
  }
  // Patch was previewed AND then confirmed/applied → draft PR was created
  // Priority: patchConfirmed is terminal state, must be checked before hasPatch
  if (args.patchConfirmed) {
    return "Ja, der Patch wurde bestätigt und angewendet. Der Draft PR wurde erstellt.";
  }
  if (args.hasPatch) {
    return "Ja, ein Patch/Diff wurde erzeugt und angewendet. Draft PR steht noch aus.";
  }
  // Fix: Direct GitHub Patch preview generated but not yet applied/committed
  if (args.patchPreviewReady) {
    return "Patch-Vorschau wurde erzeugt. Noch nicht angewendet. Noch kein geprüfter Diff, kein Commit, kein Draft PR.\nNächster Schritt: Diff prüfen oder Patch bestätigen.";
  }
  if (args.agentRunning) {
    return "Noch nicht. Sovereign Agent arbeitet noch.";
  }
  if (args.workerBlocker) {
    return args.buildWorkerBlockerAnswer
      ? args.buildWorkerBlockerAnswer()
      : "Nein. Der Worker ist blockiert. Es gibt noch keine Änderung.";
  }
  if (args.writeIntentBlockedByRepo) {
    return "Nein. Der Schreibauftrag ist blockiert, weil zuerst ein GitHub-Repo geladen werden muss.";
  }
  if (args.githubAccessState === 'validating') {
    return "Nein. Der GitHub-Zugang wird gerade geprüft. Es gibt noch keinen Patch, keinen Diff und keinen Draft PR.";
  }
  if (args.githubAccessState === 'requested') {
    return "Nein. Der GitHub-Zugang wurde nur im Format akzeptiert. Die echte GitHub-API-Prüfung steht noch aus.";
  }
  if (args.githubAccessState === 'invalid') {
    return "Nein. Der Schreibauftrag ist blockiert, weil die GitHub-Zugangsprüfung fehlgeschlagen ist.";
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
  readonly agentJob?: SovereignAgentJobSnapshot;
  readonly chatRepoSnapshot: DevChatRepoSnapshot | null;
  readonly chatRepoError: string | null;
  readonly chatHistory: readonly ChatLine[];
}): ChatLine[] {
  const lines: ChatLine[] = [];
  const firstFile = splitFilePath(
    args.agentJob?.changedFiles?.[0] ?? args.chatRepoSnapshot?.lastFile,
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
    "  1. Sage klar, dass Sovereign Agent/Draft-PR Runtime der Executor ist.",
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
  readonly agentReady?: boolean;
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
    args.agentReady
      ? "Sovereign Agent Runtime ist nur für echte Code-/Draft-PR-Aufträge zuständig und wurde für diese Chatfrage nicht gestartet."
      : "Sovereign Agent Runtime ist nicht bereit; normale Chatfragen bleiben Worker-Route.",
    codeLine,
  ].join("\n");
}

// ─────────────────────────────────────────────────────────────
// UI hint helpers
// ─────────────────────────────────────────────────────────────

/**
 * Detects a short follow-up "why" question after a local runtime status answer or blocker.
 * These must be answered locally from runtime state — no worker call.
 * Matches: "warum?", "wieso?", "weshalb?", "why?", "warum nicht?", "warum passiert nichts?"
 * Max 6 words to avoid catching complex questions like "warum macht der Agent das so?"
 */
export function isFollowUpWhyQuestion(text: string): boolean {
  const clean = text.trim().toLowerCase();
  const wordCount = clean.split(/\s+/).length;
  if (wordCount > 6) return false;
  return (
    clean === 'warum' ||
    clean === 'warum?' ||
    clean === 'wieso' ||
    clean === 'wieso?' ||
    clean === 'weshalb' ||
    clean === 'weshalb?' ||
    clean === 'why' ||
    clean === 'why?' ||
    /^warum\b/.test(clean) ||
    /^wieso\b/.test(clean) ||
    /^weshalb\b/.test(clean)
  );
}

export function composerRouteHint(args: {
  readonly draft: string;
  readonly workerBlocked: boolean;
  readonly agentDisabled: boolean;
}): string {
  const clean = args.draft.trim();
  if (!clean)
    return "Worker Chat · Repo laden · interne Runtime zuerst · Sovereign Agent nur explizit";
  const quickRepo = detectAndroidQuickRepoUrl(clean);
  if (quickRepo.recognized) return quickRepo.hint;
  if (parseDevChatGithubUrl(clean)) return "Repo laden · Runtime Snapshot";
  if (isSovereignAgentExecutionIntent(clean))
    return args.agentDisabled
      ? "Sovereign Agent blockiert · Worker erklärt zuerst"
      : "Sovereign Agent starten";
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
  readonly agentReady?: boolean;
  readonly runtimeThinkingActive: boolean;
  readonly blocked: boolean;
  readonly palDecisions: number;
  readonly outcomeHints: number;
}): number {
  let score = 0.12;
  if (args.effectiveRepoReady) score += 0.22;
  if (args.agentReady) score += 0.2;
  if (args.runtimeThinkingActive) score += 0.12;
  if (args.palDecisions > 0) score += 0.12;
  if (args.outcomeHints > 0) score += 0.1;
  if (args.blocked) score -= 0.18;
  return Math.max(0, Math.min(1, score));
}
