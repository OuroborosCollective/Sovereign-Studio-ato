/**
 * Shared local types for BuilderContainer and its extracted runtime helpers.
 * Extracted from BuilderContainer.tsx (Audit P2, 2026-07-02).
 */
import type {
  DevChatWorkerDiagnostic,
  DevChatWorkerHealthResult,
} from "./devChatWorkerBridge";

export type ChatRole = "system" | "thought" | "user" | "assistant";
export type RuntimeTier = "ready" | "active" | "blocked";
export type ModuleId =
  | "chat"
  | "init"
  | "router"
  | "pattern"
  | "sync"
  | "orchestr"
  | "logger"
  | "budget";
export type SignalType = "idle" | "active" | "processing" | "warning" | "error";
export type AnimPhase = "idle" | "spinup" | "working" | "completing" | "done" | "error";
export type CondStatus = "pass" | "fail" | "wait";

export interface ChatLine {
  readonly id: string;
  readonly role: ChatRole;
  readonly text: string;
  readonly file?: string;
  readonly path?: string;
  readonly createdAt?: number;
}

export interface RuntimeSource {
  readonly id: string;
  readonly label: string;
  readonly tier: RuntimeTier;
  readonly description: string;
  readonly available: boolean;
}

export interface ModuleCfg {
  id: ModuleId;
  short: string;
  icon: string;
  color: string;
}

export interface ModuleCond {
  label: string;
  status: CondStatus;
}

export interface WorkerRuntimeBlocker {
  readonly message: string;
  readonly diagnostic: DevChatWorkerDiagnostic;
  readonly health?: DevChatWorkerHealthResult;
  readonly createdAt: number;
}

/**
 * Builder Workbench status slots — the user-facing primary status vocabulary
 * (Actions, Files, Logs, Errors, Draft PR) that fronts the technical runtime
 * modules (ModuleId). Technical module abbreviations stay available internally
 * via the Inspector view, but must never be the primary navigation surface.
 */
export type WorkbenchStatusSlotId = "actions" | "files" | "logs" | "errors" | "draftPr";
