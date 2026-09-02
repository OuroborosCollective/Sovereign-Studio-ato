/**
 * Shared local types for BuilderContainer and its extracted runtime helpers.
 * Extracted from BuilderContainer.tsx (Audit P2, 2026-07-02).
 */
import type {
  DevChatWorkerDiagnostic,
  DevChatWorkerHealthResult,
} from "./devChatWorkerBridge";

export type ChatRole = "system" | "thought" | "user" | "assistant";
export type SituationalBubbleKind =
  | "MISSION_INPUT"
  | "REQUIRED_QUESTION"
  | "OWNER_CONSENT_REQUEST"
  | "MATERIAL_BLOCKER"
  | "FINAL_RESULT";
export type SituationalBubbleSourceKind =
  | "USER_INPUT"
  | "CANONICAL_WORKFLOW"
  | "CONSENT_CONTRACT"
  | "EFFECT_READBACK";

export type ConversationProjectionSourceKind = "LLM_RESPONSE" | "RUNTIME_NOTICE";

export interface ConversationProjection {
  readonly schemaVersion: "sovereign.conversation-projection.v1";
  readonly sourceKind: ConversationProjectionSourceKind;
  readonly authority: "CONVERSATION_ONLY";
  readonly authoritative: false;
}

export interface SituationalBubbleBinding {
  readonly schemaVersion: "sovereign.live-workspace-chat-bubble.v1";
  readonly persistenceSchemaVersion?: string;
  readonly sessionId: string;
  readonly clientMessageId: string;
  readonly bubbleKind: SituationalBubbleKind;
  readonly sourceKind: SituationalBubbleSourceKind;
  readonly text: string;
  readonly canonicalReferenceHashes: readonly string[];
  readonly sessionBindingHash?: string;
  readonly runId?: string;
  readonly attemptId?: string;
  readonly workflowState: string;
  readonly boundRevision?: string;
  readonly effectKind?: string;
  readonly targetHash?: string;
  readonly consentBindingHash?: string;
  readonly bubbleHash: string;
  readonly recordedAt?: string;
  readonly authoritative: false;
}
export type RuntimeTier = "ready" | "active" | "blocked" | "unknown";
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
  readonly bubble?: SituationalBubbleBinding;
  readonly conversationProjection?: ConversationProjection;
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
