export type AgentMode = 'single' | 'swarm';

export type JobPhase =
  | 'IDLE'
  | 'AWAKENING'
  | 'DISPATCHING'
  | 'PROVISIONING'
  | 'EXECUTING'
  | 'AWAITING_OWNER_INPUT'
  | 'FINALIZING'
  | 'BLOCKED'
  | 'READY_TO_PUBLISH'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface WorkspaceState {
  modifiedFiles: string[];
  /** Empty until an evidence anchor supplies an exact repository revision. */
  currentRevision: string;
  diffStats?: { additions: number; deletions: number; filesChanged: number };
  fileDetails?: Array<{ path: string; status: 'modified' | 'added' | 'deleted'; diff: string }>;
}

export interface OwnerInteraction {
  id: string;
  prompt: string;
  options?: string[];
  requiresText: boolean;
  timestamp?: string;
  context?: string;
}

export interface OwnerInteractionResponse { interactionId: string; response: string; }

/** A Draft PR exists here only after the backend returned complete GitHub readback evidence. */
export interface DraftPR {
  url: string;
  revision: string;
  signature?: string;
  pullRequestNumber: number;
  title?: string;
  branch: string;
  baseBranch: string;
  verifiedRevisionHash: string;
  publishedHeadSha: string;
  readbackHeadSha: string;
  ciState: 'none' | 'pending' | 'success' | 'failure';
  draftVerified: true;
  readbackVerified: true;
  checksReadbackVerified: true;
  checkRunCount: number;
  checksPendingCount: number;
  checksSuccessCount: number;
  checksFailureCount: number;
  statusContextCount: number;
  timestamp?: string;
}

export interface PublicationState {
  draftPR?: DraftPR;
  verificationLedgerHash?: string;
  signatureVerified?: boolean;
}

export interface DraftPrPreparation {
  allowed: boolean;
  decision: string;
  summary?: string;
  headBranch?: string;
  baseBranch?: string;
  nextAction?: string;
  blockers: string[];
}

export interface SovereignJob {
  /** vNext mission handle = persisted Agents SDK runId. */
  id: string;
  runId: string;
  backendJobId?: string;
  phase: JobPhase;
  createdAt: string;
  updatedAt: string;
  logs: string[];
  workspaceState: WorkspaceState;
  workspace?: WorkspaceState;
  pendingInteraction?: OwnerInteraction;
  draftPR?: DraftPR;
  publication?: PublicationState;
  draftPrPreparation?: DraftPrPreparation;
  sourceStatus?: string;
  nextAction?: string;
  error?: { message: string; code?: string };
}

export interface Toolchain {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'inactive';
  driver?: string;
  latencyMs?: number;
  badge?: string;
}
export type ToolchainAttachment = Toolchain;

export interface Skill {
  id: string;
  name: string;
  source: 'core' | 'learned';
  description: string;
  efficiency?: number;
  runsApplied?: number;
  tier?: 'Alpha' | 'Beta' | 'Neural' | 'Sovereign';
}
export type SkillNode = Skill;

export interface IntegrationAttachment {
  id: string;
  type: 'webhook' | 'artifact_store' | 'audit_ledger' | 'event_stream';
  name: string;
  status: 'connected' | 'disconnected';
  enabled?: boolean;
  endpoint?: string;
  eventsProcessed?: number;
}
export type IntegrationArchitectureAttachment = IntegrationAttachment;

export interface ChatMessage {
  id: string;
  role?: 'human' | 'system' | 'agent' | 'assistant';
  sender?: 'HUMAN' | 'SOVEREIGN_SWARM' | 'SYSTEM' | 'RUNTIME_MONITOR';
  content: string;
  timestamp: string;
  evidenceBadge?: string;
  metadata?: { jobId?: string; phase?: JobPhase; executionTimeMs?: number };
}
